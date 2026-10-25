"""State store on a real Postgres: leases, caps, counters, writes and claims (Plan P1.4).

Concurrency tests really run at the same time (asyncio.gather on separate
connections), so they exercise the database's locking, not Python's.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import limits
from app.data.engine import make_async_engine
from app.data.state_store import SpendKey, StateStore, hash_session_id
from app.models import NutritionLog

from .conftest import TEST_URL

pytestmark = pytest.mark.asyncio

DAY = datetime(2026, 10, 25, tzinfo=UTC)


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


@pytest_asyncio.fixture
async def user_id(async_engine):
    async with async_engine.begin() as conn:
        return await conn.scalar(text(
            "INSERT INTO users (email, username, password_hash) "
            "VALUES ('s@x.io', 's', 'h') RETURNING id"
        ))


async def _sql(engine, sql: str, **params):
    async with engine.begin() as conn:
        return await conn.execute(text(sql), params)


# --- Sessions ---


async def test_session_lifecycle(store, user_id, async_engine):
    raw, info = await store.create_session("account", "ipk", user_id)
    assert info.id_hash == hash_session_id(raw) and raw not in info.id_hash
    stored = (await _sql(async_engine, "SELECT id_hash FROM sessions")).scalar()
    assert stored == hash_session_id(raw)  # only the hash is stored
    touched = await store.touch_session(raw)
    assert touched and touched.user_id == user_id
    assert await store.end_session(raw) is True
    assert await store.touch_session(raw) is None


async def test_expired_session_is_not_touched(store, async_engine):
    raw, _ = await store.create_session("guest", "ipk")
    await _sql(async_engine, "UPDATE sessions SET expires_at = now() - interval '1 second'")
    assert await store.touch_session(raw) is None
    assert await store.purge_expired_sessions() == 1


async def test_account_session_slides_but_caps_at_30_days(store, user_id, async_engine):
    raw, _ = await store.create_session("account", "ipk", user_id)
    await _sql(async_engine, "UPDATE sessions SET created_at = now() - interval '29 days'")
    touched = await store.touch_session(raw)
    left = touched.expires_at - datetime.now(UTC)
    assert timedelta(hours=23) < left <= timedelta(days=1, seconds=5)  # 30-day cap, not +7 d


async def test_guest_session_keeps_absolute_lifetime(store, async_engine):
    raw, created = await store.create_session("guest", "ipk")
    touched = await store.touch_session(raw)
    assert touched.expires_at == created.expires_at


async def test_logout_everywhere(store, user_id):
    for _ in range(3):
        await store.create_session("account", "ipk", user_id)
    assert await store.end_user_sessions(user_id) == 3


async def test_session_mode_must_match_user(store, user_id):
    with pytest.raises(ValueError):
        await store.create_session("guest", "ipk", user_id)
    with pytest.raises(ValueError):
        await store.create_session("account", "ipk")


# --- Leases ---


async def test_two_concurrent_acquires_one_wins(store):
    results = await asyncio.gather(*(store.acquire_lease("user:1", f"t{i}") for i in range(2)))
    assert sorted(r.acquired for r in results) == [False, True]
    loser = next(r for r in results if not r.acquired)
    assert 1 <= loser.retry_after <= 60


async def test_many_concurrent_acquires_one_wins(store):
    results = await asyncio.gather(*(store.acquire_lease("user:1", f"t{i}") for i in range(10)))
    assert sum(r.acquired for r in results) == 1


async def test_expired_lease_is_taken_over(store, async_engine):
    assert (await store.acquire_lease("user:1", "old")).acquired
    await _sql(async_engine, "UPDATE inflight_leases SET expires_at = now() - interval '1 second'")
    assert (await store.acquire_lease("user:1", "new")).acquired
    holder = (await _sql(async_engine, "SELECT trace_id FROM inflight_leases")).scalar()
    assert holder == "new"


async def test_release_deletes_only_its_own_trace(store, async_engine):
    assert (await store.acquire_lease("user:1", "mine")).acquired
    await store.release_lease("user:1", "someone-else")
    assert not (await store.acquire_lease("user:1", "other")).acquired
    await store.release_lease("user:1", "mine")
    assert (await store.acquire_lease("user:1", "other")).acquired


async def test_three_ip_slots_allow_three_and_fourth_fails(store):
    results = [await store.acquire_lease(f"guest:{i}", f"t{i}", ip_key="ipk") for i in range(4)]
    assert [r.acquired for r in results] == [True, True, True, False]
    # The refused guest left no principal lease behind (both or neither)
    await store.release_lease("guest:0", "t0", ip_key="ipk")
    assert (await store.acquire_lease("guest:3", "t3b", ip_key="ipk")).acquired


async def test_ip_slots_under_concurrency(store):
    results = await asyncio.gather(
        *(store.acquire_lease(f"guest:{i}", f"t{i}", ip_key="ipk") for i in range(8))
    )
    assert sum(r.acquired for r in results) == limits.INFLIGHT_PER_GUEST_IP


async def test_lease_does_not_hold_a_connection(store, async_engine):
    assert (await store.acquire_lease("user:1", "t")).acquired
    assert async_engine.pool.checkedout() == 0


# --- Principal flags ---


async def test_crisis_flag_lasts_30_minutes(store, async_engine):
    assert await store.crisis_active("guest:1") is False
    await store.set_crisis("guest:1")
    assert await store.crisis_active("guest:1") is True
    await _sql(async_engine, "UPDATE principal_flags SET crisis_at = now() - interval '31 minutes'")
    assert await store.crisis_active("guest:1") is False
    assert await store.purge_expired_flags() == 1


# --- Rate counters ---


async def test_rate_counter_per_window(store):
    results = [await store.hit_rate("rpm:user:1", timedelta(minutes=1), 6) for _ in range(7)]
    assert [r.allowed for r in results] == [True] * 6 + [False]
    assert 1 <= results[-1].retry_after <= 60
    other = await store.hit_rate("rpm:user:2", timedelta(minutes=1), 6)
    assert other.allowed and other.count == 1


async def test_rate_counter_concurrent_hits_are_all_counted(store):
    await asyncio.gather(*(store.hit_rate("k", timedelta(minutes=1), 100) for _ in range(20)))
    assert (await store.hit_rate("k", timedelta(minutes=1), 100)).count == 21


async def test_rate_counter_survives_a_new_engine(store):
    for _ in range(3):
        await store.hit_rate("k", timedelta(hours=1), 10)
    fresh = make_async_engine(TEST_URL)  # a restart: new engine, new pool
    try:
        result = await StateStore(fresh).hit_rate("k", timedelta(hours=1), 10)
    finally:
        await fresh.dispose()
    assert result.count == 4


# --- Spend and credits ---


async def test_reservation_over_cap_fails(store):
    key = SpendKey("session:a", "day", DAY, cap_usd=Decimal("0.05"))
    assert await store.reserve([key], usd=Decimal("0.06")) is None
    assert await store.reserve([key], usd=Decimal("0.05")) is not None


async def test_concurrent_reservations_cannot_pass_the_cap(store):
    key = SpendKey("global", "day", DAY, cap_usd=Decimal("3"))
    results = await asyncio.gather(*(store.reserve([key], usd=Decimal("1")) for _ in range(10)))
    assert sum(r is not None for r in results) == 3
    assert (await store.spend("global", "day", DAY))["reserved_usd"] == Decimal("3")


async def test_reservation_is_all_or_nothing_across_keys(store):
    roomy = SpendKey("session:a", "day", DAY, cap_usd=Decimal("1"))
    full = SpendKey("ip:k", "day", DAY, cap_usd=Decimal("0.01"))
    assert await store.reserve([roomy, full], usd=Decimal("0.02")) is None
    # The whole transaction rolled back: nothing was reserved against either key
    row = await store.spend("session:a", "day", DAY)
    assert row is None or row["reserved_usd"] == 0


async def test_settlement_replaces_reservation_with_actual_cost(store):
    key = SpendKey("session:a", "day", DAY, cap_usd=Decimal("0.05"))
    res = await store.reserve([key], usd=Decimal("0.04"))
    await store.settle(res, Decimal("0.012"), tokens_in=900, tokens_out=300)
    row = await store.spend("session:a", "day", DAY)
    assert row["reserved_usd"] == 0 and row["cost_usd"] == Decimal("0.012")
    assert (row["tokens_in"], row["tokens_out"]) == (900, 300)
    # Room freed by settlement can be reserved again
    assert await store.reserve([key], usd=Decimal("0.038")) is not None


async def test_cancel_returns_the_reservation(store):
    key = SpendKey("session:a", "day", DAY, cap_usd=Decimal("0.05"))
    res = await store.reserve([key], usd=Decimal("0.05"))
    await store.cancel(res)
    assert await store.reserve([key], usd=Decimal("0.05")) is not None


async def test_search_credits_cap(store):
    key = SpendKey("session:a", "day", DAY, cap_credits=limits.SEARCHES_PER_GUEST_SESSION)
    results = await asyncio.gather(*(store.reserve([key], credits=1) for _ in range(8)))
    assert sum(r is not None for r in results) == limits.SEARCHES_PER_GUEST_SESSION


async def test_mixed_key_order_does_not_deadlock(store):
    a = SpendKey("a", "day", DAY, cap_usd=Decimal("100"))
    b = SpendKey("b", "day", DAY, cap_usd=Decimal("100"))
    orders = [[a, b] if i % 2 else [b, a] for i in range(20)]
    results = await asyncio.wait_for(
        asyncio.gather(*(store.reserve(keys, usd=Decimal("1")) for keys in orders)), timeout=20
    )
    assert all(r is not None for r in results)


# --- Pending writes ---


async def _allow(payload):
    return None


def _committer(calls: list, delay: float = 0.0, fail: bool = False):
    async def commit(session, payload):
        calls.append(payload)
        if delay:
            await asyncio.sleep(delay)
        if fail:
            raise RuntimeError("insert failed")
        row = NutritionLog(user_id=payload["user_id"], meal_type=payload["meal"], notes="x")
        session.add(row)
        await session.flush()
        return {"logged": "meal", "log_id": row.id}
    return commit


async def _stage(store, user_id):
    return await store.stage_write(user_id, "meal", {"user_id": user_id, "meal": "lunch"},
                                   "hash", "t1")


async def test_two_concurrent_confirms_commit_once(store, user_id, async_engine):
    write_id = await _stage(store, user_id)
    calls: list = []
    commit = _committer(calls, delay=0.2)  # hold the row lock while the other waits
    first, second = await asyncio.gather(
        store.confirm_write(write_id, user_id, _allow, commit),
        store.confirm_write(write_id, user_id, _allow, commit),
    )
    assert len(calls) == 1
    assert first == second and first.status_code == 200
    logs = (await _sql(async_engine, "SELECT count(*) FROM nutrition_logs")).scalar()
    assert logs == 1


async def test_failed_commit_leaves_write_pending(store, user_id, async_engine):
    write_id = await _stage(store, user_id)
    with pytest.raises(RuntimeError):
        await store.confirm_write(write_id, user_id, _allow, _committer([], fail=True))
    status = (await _sql(async_engine, "SELECT status FROM pending_writes")).scalar()
    assert status == "pending"
    assert (await _sql(async_engine, "SELECT count(*) FROM nutrition_logs")).scalar() == 0
    result = await store.confirm_write(write_id, user_id, _allow, _committer([]))
    assert result.status_code == 200


async def test_regate_block_discards_and_repeats_409(store, user_id):
    write_id = await _stage(store, user_id)

    async def block(payload):
        return "Contains an allergen in your profile"

    first = await store.confirm_write(write_id, user_id, block, _committer([]))
    assert first.status_code == 409 and first.body["reason"].startswith("Contains")
    again = await store.confirm_write(write_id, user_id, _allow, _committer([]))
    assert again == first  # stored result, original status code


async def test_expired_write_is_410(store, user_id, async_engine):
    write_id = await _stage(store, user_id)
    await _sql(async_engine, "UPDATE pending_writes SET expires_at = now() - interval '1 second'")
    result = await store.confirm_write(write_id, user_id, _allow, _committer([]))
    assert result.status_code == 410


async def test_other_users_write_is_404(store, user_id, async_engine):
    write_id = await _stage(store, user_id)
    other = (await _sql(async_engine, "INSERT INTO users (email, username, password_hash) "
                                      "VALUES ('o@x.io', 'o', 'h') RETURNING id")).scalar()
    assert (await store.confirm_write(write_id, other, _allow, _committer([]))).status_code == 404
    assert (await store.confirm_write(uuid.uuid4(), user_id, _allow,
                                      _committer([]))).status_code == 404


# --- Request claims ---


async def test_two_concurrent_claims_one_succeeds(store, user_id):
    request_id = uuid.uuid4()
    results = await asyncio.gather(
        *(store.claim_request(user_id, request_id, f"t{i}") for i in range(2))
    )
    assert sorted(results) == [False, True]
    assert await store.claim_request(user_id, uuid.uuid4(), "t3") is True


# --- Amounts must not be negative (a negative reservation would free budget) ---


@pytest.mark.parametrize(
    "kwargs", [{"usd": Decimal("-1")}, {"credits": -1}], ids=["usd", "credits"]
)
async def test_negative_reservation_rejected(store, kwargs):
    key = SpendKey("session:a", "day", DAY, cap_usd=Decimal("0.05"), cap_credits=5)
    held = await store.reserve([key], usd=Decimal("0.05"), credits=5)
    with pytest.raises(ValueError, match="negative"):
        await store.reserve([key], **kwargs)
    assert await store.reserve([key], usd=Decimal("0.01")) is None  # still full
    assert held is not None


@pytest.mark.parametrize(
    "kwargs",
    [{"usd": Decimal("-0.01")}, {"tokens_in": -1}, {"tokens_out": -1}, {"credits": -1}],
    ids=["usd", "tokens_in", "tokens_out", "credits"],
)
async def test_negative_settlement_rejected(store, kwargs):
    key = SpendKey("session:a", "day", DAY, cap_usd=Decimal("0.05"))
    res = await store.reserve([key], usd=Decimal("0.01"))
    settle = {"usd": Decimal("0"), **kwargs}
    with pytest.raises(ValueError, match="negative"):
        await store.settle(res, **settle)
    row = await store.spend("session:a", "day", DAY)
    assert row["cost_usd"] == 0 and row["reserved_usd"] == Decimal("0.01")  # untouched


@pytest.mark.parametrize(
    ("window", "limit"), [(timedelta(0), 5), (timedelta(seconds=-1), 5), (timedelta(minutes=1), -1)]
)
async def test_rate_counter_rejects_bad_window_or_limit(store, window, limit):
    with pytest.raises(ValueError):
        await store.hit_rate("k", window, limit)
