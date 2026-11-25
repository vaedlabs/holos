"""Migration chain, schema and constraints on a real Postgres (Plan P1.3)."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401  (registers every table)
from app.database import Base

from .conftest import OLD_HEAD, alembic, reset_schema

NEW_TABLES = {
    "sessions", "inflight_leases", "principal_flags", "rate_counters", "spend",
    "pending_writes", "chat_requests", "stream_events", "invites", "traces",
    "gate_decisions", "rule_hit_counts", "deletion_queue", "account_imports",
    "unresolved_terms",
}


@pytest.fixture
def fresh(engine):
    """An empty schema; afterwards the database is left at head for other tests."""
    reset_schema(engine)
    yield engine
    reset_schema(engine)
    alembic("upgrade", "head")


def _tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def _version(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _seed_old_schema(engine) -> None:
    """Rows in the tables that existed before P1.3."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, email, username, password_hash, is_active) VALUES "
            "(1, 'a@example.com', 'alice', 'h', true), (2, 'b@example.com', 'bob', 'h', true)"
        ))
        conn.execute(text(
            "INSERT INTO medical_history (user_id, conditions) VALUES (1, 'torn ACL')"
        ))
        conn.execute(text(
            "INSERT INTO user_preferences (user_id, goals, age) VALUES (1, 'run', 30)"
        ))
        conn.execute(text("INSERT INTO workout_logs (user_id, exercise_type) VALUES (1, 'walk')"))
        conn.execute(text("INSERT INTO nutrition_logs (user_id, meal_type) VALUES (1, 'lunch')"))
        conn.execute(text(
            "INSERT INTO mental_fitness_logs (user_id, activity_type) VALUES (2, 'x')"
        ))
        conn.execute(text(
            "INSERT INTO conversation_messages (user_id, role, content, agent_type) "
            "VALUES (1, 'user', 'hello', 'physical-fitness')"
        ))
        conn.execute(text(
            "INSERT INTO agent_execution_logs (trace_id, agent_type, user_id) VALUES ('t1', 'x', 2)"
        ))


def _counts(engine) -> dict[str, int]:
    # agent_execution_logs isn't kept: 293a4b5c6d74 drops it, its downgrade recreates it empty
    tables = ("users", "medical_history", "user_preferences", "workout_logs", "nutrition_logs",
              "mental_fitness_logs", "conversation_messages")
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in tables}


def test_up_down_up_on_empty_database(fresh):
    alembic("upgrade", "head")
    assert _tables(fresh) == set(Base.metadata.tables)
    alembic("downgrade", OLD_HEAD)
    assert _version(fresh) == OLD_HEAD
    assert not (_tables(fresh) & NEW_TABLES)
    alembic("upgrade", "head")
    assert _tables(fresh) == set(Base.metadata.tables)


def test_up_down_up_keeps_existing_data(fresh):
    alembic("upgrade", OLD_HEAD)
    _seed_old_schema(fresh)
    before = _counts(fresh)
    alembic("upgrade", "head")
    assert _counts(fresh) == before
    alembic("downgrade", OLD_HEAD)
    assert _counts(fresh) == before
    alembic("upgrade", "head")
    assert _counts(fresh) == before
    with fresh.connect() as conn:
        assert conn.execute(text("SELECT conditions FROM medical_history")).scalar() == "torn ACL"


def test_accounts_without_a_status_become_active(fresh):
    """Before 0718293a4b52 a row inserted without is_active had NULL, which locked the
    account out of the profile routes."""
    alembic("upgrade", "f60718293a41")
    with fresh.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, username, password_hash, is_active) "
                          "VALUES (1, 'a@x.io', 'a', 'h', NULL), (2, 'b@x.io', 'b', 'h', false)"))
    alembic("upgrade", "head")
    with fresh.connect() as conn:
        assert conn.execute(text("SELECT id, is_active FROM users ORDER BY id")).all() == [
            (1, True), (2, False)]

def test_held_entries_lose_their_time_limit(fresh):
    """18293a4b5c63 (Part E #50): a waiting entry has no expiry; one already past the old
    15 minutes couldn't be confirmed, so it goes; a decided one keeps its day."""
    alembic("upgrade", "0718293a4b52")
    with fresh.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, username, password_hash) "
                          "VALUES (1, 'a@x.io', 'a', 'h')"))
        for name, status, ends in (("live", "pending", "10 minutes"),
                                   ("late", "pending", "-1 minute"),
                                   ("done", "committed", "20 hours")):
            conn.execute(text(
                "INSERT INTO pending_writes (id, user_id, kind, payload, profile_hash, "
                "trace_id, status, expires_at) VALUES (gen_random_uuid(), 1, 'meal', '{}', "
                ":n, 't', :s, now() + CAST(:e AS interval))"), {"n": name, "s": status, "e": ends})
    alembic("upgrade", "head")
    with fresh.connect() as conn:
        assert conn.execute(text("SELECT profile_hash, expires_at IS NULL FROM pending_writes "
                                 "ORDER BY profile_hash")).all() == [("done", False),
                                                                     ("live", True)]


def _shape(engine, table: str) -> tuple:
    insp = inspect(engine)
    columns = [(c["name"], str(c["type"]), c["nullable"], c.get("default"))
               for c in insp.get_columns(table)]
    indexes = sorted((i["name"], tuple(i["column_names"]), i["unique"])
                     for i in insp.get_indexes(table))
    keys = [(k["constrained_columns"], k["referred_table"], k["options"].get("ondelete"))
            for k in insp.get_foreign_keys(table)]
    return columns, indexes, keys


def test_the_old_agent_log_is_dropped_and_comes_back_as_it_was(fresh):
    """293a4b5c6d74 (P4.12): the old agents' log goes with them; its rows held people's
    messages. The downgrade recreates the table as it was, empty."""
    alembic("upgrade", "18293a4b5c63")
    before = _shape(fresh, "agent_execution_logs")
    with fresh.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, username, password_hash) "
                          "VALUES (1, 'a@x.io', 'a', 'h')"))
        conn.execute(text("INSERT INTO agent_execution_logs (trace_id, agent_type, user_id, "
                          "query) VALUES ('t1', 'physical', 1, 'my knee hurts')"))
    alembic("upgrade", "head")
    assert "agent_execution_logs" not in _tables(fresh)
    alembic("downgrade", "18293a4b5c63")
    assert _shape(fresh, "agent_execution_logs") == before
    with fresh.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM agent_execution_logs")).scalar() == 0
        conn.execute(text("INSERT INTO agent_execution_logs (trace_id, agent_type, user_id) "
                          "VALUES ('t2', 'physical', 1)"))
        conn.execute(text("DELETE FROM users WHERE id = 1"))  # still cascades
        assert conn.execute(text("SELECT count(*) FROM agent_execution_logs")).scalar() == 0


# Every agent_type the old app and P4.7 saved, and what each answer's coaches become
AGENT_TYPES = [("user", "user", None), ("assistant", "holos", None),
               ("assistant", "coordinator", None), ("assistant", "physical", ["physical"]),
               ("assistant", "physical-fitness", ["physical"]),
               ("assistant", "mental-fitness", ["mental"]),
               ("assistant", "nutrition,mental", ["nutrition", "mental"]),
               ("assistant", "mental, physical", ["physical", "mental"]),
               ("assistant", "physical,nutrition,mental", ["physical", "nutrition", "mental"])]


def test_who_answered_becomes_a_list_and_comes_back(fresh):
    """4b5c6d7e8f96 (Part E #61): `agents` replaces the comma list, old names mapped; the
    downgrade writes the comma list back as P4.7 wrote it."""
    alembic("upgrade", "3a4b5c6d7e85")
    before = _shape(fresh, "conversation_messages")
    with fresh.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, username, password_hash) "
                          "VALUES (1, 'a@x.io', 'a', 'h')"))
        for role, agent_type, _ in AGENT_TYPES:
            conn.execute(text("INSERT INTO conversation_messages (user_id, role, content, "
                              "agent_type, warnings) VALUES (1, :r, 'x', :a, '[\"old\"]')"),
                         {"r": role, "a": agent_type})
    alembic("upgrade", "head")
    with fresh.connect() as conn:
        assert [r[0] for r in conn.execute(text(
            "SELECT agents FROM conversation_messages ORDER BY id"))] == [
            agents for _, _, agents in AGENT_TYPES]
    alembic("downgrade", "3a4b5c6d7e85")
    # The columns come back at the end of the table: Postgres can't place them
    after = _shape(fresh, "conversation_messages")
    assert (sorted(after[0]), after[1:]) == (sorted(before[0]), before[1:])
    with fresh.connect() as conn:
        assert [r[0] for r in conn.execute(text(
            "SELECT agent_type FROM conversation_messages ORDER BY id"))] == [
            "user", "holos", "holos", "physical", "physical", "mental", "nutrition,mental",
            "physical,mental", "physical,nutrition,mental"]


def test_the_mood_rating_goes_and_practice_logs_stay(fresh):
    """5c6d7e8f9a07 (Part E #73): the guessed mood rating's columns go; every practice log
    keeps the rest. The downgrade brings the columns back empty."""
    alembic("upgrade", "4b5c6d7e8f96")
    before = _shape(fresh, "mental_fitness_logs")
    with fresh.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, username, password_hash) "
                          "VALUES (1, 'a@x.io', 'a', 'h')"))
        conn.execute(text("INSERT INTO mental_fitness_logs (user_id, activity_type, "
                          "duration_minutes, mood_before, mood_after, notes) VALUES "
                          "(1, 'body_scan', 10, '2', '4', 'before bed'), "
                          "(1, 'box_breathing', 5, NULL, NULL, NULL)"))
    alembic("upgrade", "head")
    columns = {c["name"] for c in inspect(fresh).get_columns("mental_fitness_logs")}
    assert not columns & {"mood_before", "mood_after"}
    rows = "SELECT activity_type, duration_minutes, notes FROM mental_fitness_logs ORDER BY id"
    with fresh.connect() as conn:
        assert conn.execute(text(rows)).all() == [("body_scan", 10.0, "before bed"),
                                                  ("box_breathing", 5.0, None)]
    alembic("downgrade", "4b5c6d7e8f96")
    after = _shape(fresh, "mental_fitness_logs")  # the columns come back at the end
    assert (sorted(after[0]), after[1:]) == (sorted(before[0]), before[1:])
    with fresh.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM mental_fitness_logs WHERE "
                                 "mood_before IS NOT NULL OR mood_after IS NOT NULL")).scalar() == 0
        assert len(conn.execute(text(rows)).all()) == 2


def test_schema_matches_models(migrated):
    with migrated.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata
        )
    assert diff == []


def test_every_user_foreign_key_cascades(migrated):
    insp = inspect(migrated)
    found = 0
    for table in insp.get_table_names():
        for fk in insp.get_foreign_keys(table):
            if fk["referred_table"] == "users":
                found += 1
                assert fk["options"].get("ondelete") == "CASCADE", f"{table}.{fk['name']}"
    assert found >= 13


def test_duplicate_client_request_id_rejected(clean):
    request_id = uuid.uuid4()
    with clean.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, email, username, password_hash) VALUES (1, 'a@x.io', 'a', 'h')"
        ))
        insert = text(
            "INSERT INTO conversation_messages (user_id, role, content, client_request_id) "
            "VALUES (1, 'user', 'hi', :rid)"
        )
        conn.execute(insert, {"rid": request_id})
        conn.execute(insert, {"rid": None})
        conn.execute(insert, {"rid": None})  # old rows without an id are fine
    with pytest.raises(IntegrityError, match="uq_conversation_user_request"):
        with clean.begin() as conn:
            conn.execute(insert, {"rid": request_id})


# --- Deleting a user cascades to every table with a user_id ---

# Values that satisfy check constraints
CHECKED = {
    ("sessions", "mode"): "account",
    ("spend", "period"): "day",
    ("pending_writes", "kind"): "workout",
    ("pending_writes", "status"): "pending",
}


def _value(table: sa.Table, column: sa.Column, user_id: int):
    if (table.name, column.name) in CHECKED:
        return CHECKED[(table.name, column.name)]
    if any(fk.column.table.name == "users" for fk in column.foreign_keys):
        return user_id
    kind = column.type
    if isinstance(kind, sa.Uuid):
        return uuid.uuid4()
    if isinstance(kind, sa.DateTime):
        return datetime.now(UTC)
    if isinstance(kind, sa.Date):
        return date.today()
    if isinstance(kind, sa.Boolean):
        return True
    if isinstance(kind, sa.JSON):
        return {}
    if isinstance(kind, sa.ARRAY):
        return [f"{table.name}-{column.name}"]
    if isinstance(kind, sa.Numeric) and not isinstance(kind, sa.Float):
        return Decimal("0")
    if isinstance(kind, sa.Float):
        return 0.0
    if isinstance(kind, sa.Integer):
        return user_id
    if isinstance(kind, sa.String | sa.Text):
        value = f"{table.name}-{column.name}-{user_id}"
        return value[: kind.length] if getattr(kind, "length", None) else value
    raise AssertionError(f"no sample value for {table.name}.{column.name} ({kind})")


def _user_tables() -> list[sa.Table]:
    return [
        t for t in Base.metadata.sorted_tables
        if any(fk.column.table.name == "users" for fk in t.foreign_keys)
    ]


def _user_columns(table: sa.Table) -> list[sa.Column]:
    return [
        c for c in table.columns
        if any(fk.column.table.name == "users" for fk in c.foreign_keys)
    ]


def test_deleting_a_user_cascades_everywhere(clean):
    tables = _user_tables()
    assert len(tables) >= 13  # 7 existing tables + the C.11 tables with a user link
    with clean.begin() as conn:
        for uid in (1, 2):
            conn.execute(sa.insert(Base.metadata.tables["users"]).values(
                id=uid, email=f"u{uid}@x.io", username=f"u{uid}", password_hash="h"))
        for table in tables:
            for uid in (1, 2):
                row = {
                    c.name: _value(table, c, uid)
                    for c in table.columns
                    if not (c.autoincrement is True and c.primary_key)
                    and (c.server_default is None or c.foreign_keys)
                    and not (c.nullable and not c.foreign_keys and not c.primary_key)
                }
                conn.execute(sa.insert(table).values(**row))

    with clean.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = 1"))

    with clean.connect() as conn:
        for table in tables:
            for column in _user_columns(table):
                left = conn.execute(
                    sa.select(sa.func.count()).select_from(table).where(column == 1)
                ).scalar()
                other = conn.execute(
                    sa.select(sa.func.count()).select_from(table).where(column == 2)
                ).scalar()
                assert left == 0, f"{table.name}.{column.name}: rows left for the deleted user"
                assert other == 1, f"{table.name}.{column.name}: the other user's row was lost"
