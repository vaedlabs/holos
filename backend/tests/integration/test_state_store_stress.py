"""Randomized concurrent stress on the state store (Plan P1.4).

Many workers run random operations at the same time; the tests then check the
invariants that must hold however the operations interleave. Seeds are fixed so
a failure can be replayed.
"""

import asyncio
import random
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import limits
from app.data.state_store import SpendKey, StateStore
from app.models import WorkoutLog

pytestmark = pytest.mark.asyncio

DAY = datetime(2026, 10, 25, tzinfo=UTC)
WORKERS = 12  # below the async pool's 15 connections
CENT = Decimal("0.01")


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


async def _rows(engine, sql: str):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).mappings().all()


@pytest.mark.parametrize("seed", [1, 2, 3])
async def test_spend_never_passes_a_cap_and_settles_exactly(store, async_engine, seed):
    rng = random.Random(seed)
    keys = [
        SpendKey("session:a", "day", DAY, cap_usd=Decimal("4"), cap_credits=6),
        SpendKey("ip:k", "day", DAY, cap_usd=Decimal("6"), cap_credits=9),
        SpendKey("global", "day", DAY, cap_usd=Decimal("8"), cap_credits=12),
    ]
    caps = {k.key: k for k in keys}
    settled = Counter()  # key -> dollars actually charged
    credited = Counter()
    violations = []
    outcomes = Counter()
    running = True

    async def monitor():
        while running:
            for row in await _rows(async_engine, "SELECT * FROM spend"):
                k = caps[row["key"]]
                if row["cost_usd"] + row["reserved_usd"] > k.cap_usd:
                    violations.append(("usd", dict(row)))
                if row["search_credits"] + row["reserved_credits"] > k.cap_credits:
                    violations.append(("credits", dict(row)))
            await asyncio.sleep(0)

    async def worker(n: int):
        r = random.Random(seed * 100 + n)
        for _ in range(25):
            subset = r.sample(keys, r.randint(1, 3))
            usd = CENT * r.randint(1, 120)
            credits = r.randint(0, 2)
            res = await store.reserve(subset, usd=usd, credits=credits)
            outcomes[res is not None] += 1
            if res is None:
                continue
            await asyncio.sleep(r.random() / 200)
            if r.random() < 0.3:
                await store.cancel(res)
                continue
            actual = CENT * r.randint(0, int(usd / CENT))  # never more than reserved
            used = r.randint(0, credits)
            await store.settle(res, actual, tokens_in=10, tokens_out=5, credits=used)
            for k in res.keys:
                settled[k.key] += actual
                credited[k.key] += used

    watcher = asyncio.create_task(monitor())
    await asyncio.wait_for(asyncio.gather(*(worker(n) for n in range(WORKERS))), timeout=60)
    running = False
    await watcher

    assert violations == [], f"seed {seed}: cap passed: {violations[:3]}"
    # The run must really press on the caps: some reservations refused, many granted
    assert outcomes[False] > 10 and outcomes[True] > 50, outcomes
    for row in await _rows(async_engine, "SELECT * FROM spend"):
        assert row["reserved_usd"] == 0 and row["reserved_credits"] == 0, row
        assert row["cost_usd"] == settled[row["key"]], row
        assert row["search_credits"] == credited[row["key"]], row
        assert row["cost_usd"] <= caps[row["key"]].cap_usd
    assert rng  # seed kept for replay


@pytest.mark.parametrize("seed", [1, 2, 3])
async def test_leases_never_double_held(store, async_engine, seed):
    principals = ["guest:a", "guest:b", "guest:c", "guest:d", "guest:e"]
    holders: dict[str, str] = {}
    ip_holders: set[str] = set()
    problems = []
    acquired = 0

    async def worker(n: int):
        nonlocal acquired
        r = random.Random(seed * 100 + n)
        for i in range(20):
            principal = r.choice(principals)
            trace = f"w{n}-{i}"
            result = await store.acquire_lease(principal, trace, ip_key="ipk")
            if not result.acquired:
                assert result.retry_after >= 1
                continue
            acquired += 1
            if principal in holders:
                problems.append(f"{principal} held by {holders[principal]} and {trace}")
            holders[principal] = trace
            ip_holders.add(trace)
            if len(ip_holders) > limits.INFLIGHT_PER_GUEST_IP:
                problems.append(f"{len(ip_holders)} requests on one IP key")
            await asyncio.sleep(r.random() / 100)
            del holders[principal]
            ip_holders.discard(trace)
            await store.release_lease(principal, trace, ip_key="ipk")

    await asyncio.wait_for(asyncio.gather(*(worker(n) for n in range(WORKERS))), timeout=60)
    assert problems == [], f"seed {seed}: {problems[:3]}"
    assert acquired > 20  # the run really exercised the leases
    assert await _rows(async_engine, "SELECT * FROM inflight_leases") == []


async def test_each_write_commits_once_under_racing_confirms(store, async_engine):
    async with async_engine.begin() as conn:
        user_id = await conn.scalar(text(
            "INSERT INTO users (email, username, password_hash) "
            "VALUES ('w@x.io', 'w', 'h') RETURNING id"
        ))
    writes = [
        await store.stage_write(user_id, "workout", {"n": i}, "hash", f"t{i}") for i in range(10)
    ]
    commits = Counter()

    async def allow(payload):
        await asyncio.sleep(0)
        return None

    async def commit(session, payload):
        commits[payload["n"]] += 1
        await asyncio.sleep(0.01)
        session.add(WorkoutLog(user_id=user_id, notes=str(payload["n"])))
        await session.flush()
        return {"logged": payload["n"]}

    results = await asyncio.wait_for(asyncio.gather(*(
        store.confirm_write(w, user_id, allow, commit) for w in writes for _ in range(3)
    )), timeout=60)
    assert all(r.status_code == 200 for r in results)
    assert commits == Counter(range(10)), "each write committed exactly once"
    logs = await _rows(async_engine, "SELECT notes FROM workout_logs")
    assert sorted(int(r["notes"]) for r in logs) == list(range(10))
