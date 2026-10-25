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
    "pending_writes", "request_claims", "invites", "traces", "gate_decisions",
    "rule_hit_counts", "deletion_queue",
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
    tables = ("users", "medical_history", "user_preferences", "workout_logs", "nutrition_logs",
              "mental_fitness_logs", "conversation_messages", "agent_execution_logs")
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
