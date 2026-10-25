"""Tools against a real Postgres: reads, writes that never commit, search credits (P2.2)."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.tools import AGENT_TOOLS, ToolContext, WebSearch
from app.data.engine import make_async_engine
from app.data.state_store import SpendKey, StateStore
from app.models import NutritionLog, User, WorkoutLog

from ..unit.tools.conftest import Clock, FakeSearchClient
from ..unit.tools.test_write_and_read_tools import WRITES
from .conftest import TEST_URL

pytestmark = pytest.mark.asyncio

TOOLS = {t.name: t for tools in AGENT_TOOLS.values() for t in tools}
DAY = datetime(2026, 10, 25, tzinfo=UTC)


@pytest_asyncio.fixture
async def sessions(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def two_users(sessions):
    """Alice has two recent workouts and one old one; Bob has one workout and a meal."""
    now = datetime.now(UTC)
    async with sessions() as s:
        alice = User(email="a@x.io", username="alice", password_hash="h")
        bob = User(email="b@x.io", username="bob", password_hash="h")
        s.add_all([alice, bob])
        await s.flush()
        s.add_all([
            WorkoutLog(user_id=alice.id, workout_date=now - timedelta(days=1), notes="yesterday"),
            WorkoutLog(user_id=alice.id, workout_date=now, notes="today"),
            WorkoutLog(user_id=alice.id, workout_date=now - timedelta(days=20), notes="old"),
            WorkoutLog(user_id=bob.id, workout_date=now, notes="bob's"),
            NutritionLog(user_id=bob.id, meal_type="lunch", notes="bob's meal"),
        ])
        await s.commit()
        return alice.id, bob.id


async def test_recent_logs_own_newest_first_within_days(sessions, two_users):
    alice, _ = two_users
    ctx = ToolContext(mode="account", trace_id="t", user_id=alice, sessions=sessions)
    out = await TOOLS["get_recent_logs"].run({"kind": "workout", "days": 14}, ctx)
    assert [e["notes"] for e in out["entries"]] == ["today", "yesterday"]
    assert set(out["entries"][0]) == {"date", "exercise_type", "exercises", "duration_minutes",
                                      "notes"}
    meals = await TOOLS["get_recent_logs"].run({"kind": "meal", "days": 14}, ctx)
    assert meals == {"entries": []}  # Bob's meal is not Alice's


async def test_writes_never_commit(sessions, two_users, async_engine):
    alice, _ = two_users
    ctx = ToolContext(mode="account", trace_id="t", user_id=alice, sessions=sessions)
    async with async_engine.connect() as conn:
        before = {t: await conn.scalar(text(f"SELECT count(*) FROM {t}"))
                  for t in ("workout_logs", "nutrition_logs", "mental_fitness_logs")}
    for name, (_, args, _) in WRITES.items():
        assert (await TOOLS[name].run(args, ctx))["status"] == "staged"
    async with async_engine.connect() as conn:
        after = {t: await conn.scalar(text(f"SELECT count(*) FROM {t}")) for t in before}
    assert after == before
    assert len(ctx.staged_writes) == 3


async def test_search_credits_use_the_state_store(async_engine):
    client = FakeSearchClient()
    store = StateStore(async_engine)
    service = WebSearch(client, store, Clock())
    key = SpendKey("session:a", "day", DAY, cap_credits=1)

    def ctx():
        return ToolContext(mode="guest", trace_id="t", search=service, search_keys=[key])

    assert (await TOOLS["web_search"].run({"query": "first"}, ctx()))["status"] == "ok"
    capped = ctx()
    out = await TOOLS["web_search"].run({"query": "second"}, capped)
    assert out == {"status": "search_unavailable"} and capped.untrusted is False
    cached = await TOOLS["web_search"].run({"query": "FIRST"}, ctx())
    assert cached["status"] == "ok"  # a cache hit needs no credit
    assert len(client.calls) == 1
    row = await store.spend("session:a", "day", DAY)
    assert row["search_credits"] == 1 and row["reserved_credits"] == 0


def test_db_read_does_not_block_the_loop(caplog, two_users_sync):
    alice = two_users_sync

    async def run():
        engine = make_async_engine(TEST_URL)
        try:
            ctx = ToolContext(mode="account", trace_id="t", user_id=alice,
                              sessions=async_sessionmaker(engine, expire_on_commit=False))
            await TOOLS["get_recent_logs"].run({"kind": "workout", "days": 7}, ctx)  # warm up
            caplog.clear()
            for _ in range(3):
                await TOOLS["get_recent_logs"].run({"kind": "workout", "days": 7}, ctx)
        finally:
            await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.set_debug(True)
    loop.slow_callback_duration = 0.05
    try:
        with caplog.at_level(logging.WARNING, logger="asyncio"):
            loop.run_until_complete(run())
    finally:
        loop.close()
    slow = [r.getMessage() for r in caplog.records if "took" in r.getMessage()]
    assert slow == []


@pytest.fixture
def two_users_sync(clean):
    with clean.begin() as conn:
        uid = conn.execute(text(
            "INSERT INTO users (email, username, password_hash) VALUES ('s@x.io', 's', 'h') "
            "RETURNING id"
        )).scalar()
        conn.execute(text("INSERT INTO workout_logs (user_id, notes) VALUES (:u, 'w')"),
                     {"u": uid})
    return uid


async def test_concurrent_tool_round_on_one_context(sessions, two_users, async_engine):
    """C.10 runs one round's tool calls at the same time on one request context."""
    alice, _ = two_users
    service = WebSearch(FakeSearchClient(delay=0.02), StateStore(async_engine), Clock())
    key = SpendKey("session:r", "day", DAY, cap_credits=10)
    ctx = ToolContext(mode="account", trace_id="t", user_id=alice, sessions=sessions,
                      search=service, search_keys=[key])
    calls = [TOOLS["get_recent_logs"].run({"kind": k, "days": 14}, ctx)
             for k in ("workout", "meal", "practice")]
    calls += [TOOLS["web_search"].run({"query": f"query {i}"}, ctx) for i in range(2)]
    calls += [TOOLS[name].run(args, ctx) for name, (_, args, _) in WRITES.items()]
    results = await asyncio.wait_for(asyncio.gather(*calls), timeout=20)

    assert [len(r["entries"]) for r in results[:3]] == [2, 0, 0]
    assert all(r["status"] == "ok" for r in results[3:5])
    assert all(r["status"] == "staged" for r in results[5:])
    assert len(ctx.staged_writes) == 3 and ctx.untrusted is True
    ids = [s.id for s in ctx.sources]
    assert len(ids) == len(set(ids)) == 2  # unique source ids under concurrency
    for result in results:
        json.dumps(result)  # JSON-safe, including dates and floats from the DB
    async with async_engine.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM nutrition_logs")) == 1  # Bob's only
