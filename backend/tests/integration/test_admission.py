"""Admission (C.2 stage 6), the flood limit (stage 1) and login limits on a real Postgres
(Plan C.12, C.13, P4.3, Part E #25). Replaces tests/test_rate_limit.py."""

import asyncio
import io
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import limits
from app.config.settings import Settings, get_settings
from app.data.engine import make_async_engine
from app.data.state_store import StateStore
from app.dependencies import get_db_sessions, get_principal, get_state_store
from app.middleware.flood import FloodLimit, flood_key
from app.middleware.headers import SecurityHeaders
from app.orchestration import admission, passwords
from app.orchestration.admission import admit
from app.orchestration.budget import (
    Budget,
    CallMeter,
    call_usd,
    ip_spend_key,
    max_call_usd,
    spend_keys,
)
from app.orchestration.principal import Principal, csrf_token, ip_key, ip_requests_key
from app.providers.base import GenerateOptions, Usage
from app.providers.resilient import Breakers
from app.routers import auth
from app.routers.errors import ApiError, api_error_handler
from app.routers.intake import clean_image, read_chat_request

from .conftest import TEST_URL

pytestmark = pytest.mark.asyncio

APP = "http://localhost:3000"
PASSWORD = "Correct-Horse-1"


def settings() -> Settings:
    return Settings(session_secret=b"s" * 40, ip_salt_secret=b"i" * 40, app_origin=APP,
                    api_origin="http://localhost:8000", trusted_proxy="none",
                    turnstile_secret="1x0000000000000000000000000000000AA",
                    turnstile_interactive_secret="1x0000000000000000000000000000000AA",
                    environment="test")


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


async def sql(engine, statement: str, **params):
    async with engine.begin() as conn:
        result = await conn.execute(text(statement), params)
        return result.all() if result.returns_rows else []


async def make_user(engine, email="ved@example.com", password_hash="x") -> int:
    rows = await sql(engine, "INSERT INTO users (email, username, password_hash, is_active) "
                     "VALUES (:e, :e, :h, true) RETURNING id", e=email, h=password_hash)
    return rows[0][0]


async def guest(store, ipk="ipk-a") -> Principal:
    raw, session = await store.create_session("guest", ipk)
    return Principal(session, raw, ipk)


async def account(store, engine, email="ved@example.com", ipk="ipk-a") -> Principal:
    user_id = await make_user(engine, email)
    raw, session = await store.create_session("account", ipk, user_id=user_id)
    return Principal(session, raw, ipk)


async def refused(principal, store, rid=None) -> ApiError:
    with pytest.raises(ApiError) as caught:
        await admit(principal, rid or uuid.uuid4(), store)
    return caught.value


async def seed_counter(engine, key: str, window: timedelta, count: int, start=None):
    """A counter already at `count` in the current window (as admission computes it)."""
    s = int(window.total_seconds())
    await sql(engine, "INSERT INTO rate_counters (key, window_start, count) VALUES (:k, "
              "COALESCE(CAST(:start AS timestamptz), "
              "to_timestamp(floor(extract(epoch FROM now()) / :s) * :s)), :c)",
              k=key, s=s, c=count, start=start)


async def seed_spend(engine, spend_key, cost="0", reserved="0"):
    await sql(engine, "INSERT INTO spend (key, period, period_start, cost_usd, reserved_usd) "
              "VALUES (:k, :p, :s, :c, :r)", k=spend_key.key, p=spend_key.period,
              s=spend_key.period_start, c=Decimal(cost), r=Decimal(reserved))


async def counts(engine) -> dict[str, int]:
    return dict(await sql(engine, "SELECT key, count FROM rate_counters"))


async def leases(engine) -> set[str]:
    return {r[0] for r in await sql(engine, "SELECT principal_key FROM inflight_leases")}


async def not_near_window_end(seconds: int, margin: float = 3.0) -> None:
    """Fixed windows: keep a burst of hits inside one window."""
    left = seconds - time.time() % seconds
    if left < margin:
        await asyncio.sleep(left + 0.1)


# --- Leases ---


async def test_a_second_request_while_one_is_in_flight_is_429_with_retry_after(store):
    me = await guest(store)
    first = await admit(me, uuid.uuid4(), store)
    error = await refused(me, store)
    assert (error.status, error.code) == (429, "busy")
    assert 1 <= error.retry_after <= 60
    await first.release()
    second = await admit(me, uuid.uuid4(), store)
    await second.release()


async def test_two_tabs_of_one_account_share_the_lease(store, async_engine):
    me = await account(store, async_engine)
    raw, other_tab = await store.create_session("account", "ipk-b", user_id=me.user_id)
    held = await admit(me, uuid.uuid4(), store)
    error = await refused(Principal(other_tab, raw, "ipk-b"), store)
    assert error.code == "busy"
    await held.release()


async def test_a_fourth_guest_request_from_one_ip_key_is_429(store):
    held = [await admit(await guest(store), uuid.uuid4(), store) for _ in range(3)]
    error = await refused(await guest(store), store)
    assert (error.status, error.code) == (429, "network_busy")
    assert error.retry_after >= 1
    # Another network is not affected
    other = await admit(await guest(store, "ipk-b"), uuid.uuid4(), store)
    for a in held + [other]:
        await a.release()


async def test_accounts_take_no_ip_slot(store, async_engine):
    held = [await admit(await guest(store), uuid.uuid4(), store) for _ in range(3)]
    mine = await admit(await account(store, async_engine), uuid.uuid4(), store)
    for a in held + [mine]:
        await a.release()


async def test_release_frees_the_lease_the_ip_slot_and_the_global_slot(store, async_engine):
    me = await guest(store)
    held = await admit(me, uuid.uuid4(), store)
    keys = await leases(async_engine)
    assert me.principal_key in keys
    assert sum(k.startswith("ip:ipk-a:") for k in keys) == 1
    assert sum(k.startswith("global:") for k in keys) == 1
    await held.release()
    assert await leases(async_engine) == set()


async def test_release_never_frees_another_requests_slots(store, async_engine):
    a, b = await guest(store), await guest(store)
    held_a = await admit(a, uuid.uuid4(), store)
    held_b = await admit(b, uuid.uuid4(), store)
    await held_a.release()
    left = await leases(async_engine)
    assert b.principal_key in left and len(left) == 3  # b's lease, IP slot and global slot
    await held_b.release()


async def test_over_the_global_in_flight_cap_is_503(store, async_engine):
    # Every global slot is held by a live request of someone else
    for n in range(limits.INFLIGHT_GLOBAL):
        await sql(async_engine, "INSERT INTO inflight_leases VALUES (:k, :t, now() + "
                  "interval '50 seconds')", k=f"global:{n}", t=f"other{n}")
    me = await guest(store)
    error = await refused(me, store)
    assert (error.status, error.code) == (503, "server_busy")
    assert error.retry_after == admission.SERVER_BUSY_RETRY_S
    # Nothing was taken: no lease, no IP slot, no count
    assert not any(k.startswith(("session:", "ip:")) for k in await leases(async_engine))
    assert await counts(async_engine) == {}
    await sql(async_engine, "DELETE FROM inflight_leases WHERE trace_id = 'other0'")
    held = await admit(me, uuid.uuid4(), store)
    await held.release()


async def test_an_open_provider_breaker_is_503_until_its_trial_call(store, async_engine):
    clock = [0.0]
    breaker = Breakers(lambda: clock[0])["openai"]
    for _ in range(5):
        breaker.record_failure()
    me = await guest(store)
    with pytest.raises(ApiError) as caught:
        await admit(me, uuid.uuid4(), store, breaker=breaker)
    error = caught.value
    assert (error.status, error.code, error.retry_after) == (503, "server_busy", 30)
    # Refused before anything was taken
    assert await leases(async_engine) == set() and await counts(async_engine) == {}
    clock[0] = 29.2
    with pytest.raises(ApiError) as caught:
        await admit(me, uuid.uuid4(), store, breaker=breaker)
    assert caught.value.retry_after == 1
    # Half-open: the request that makes the trial call is admitted
    clock[0] = 30
    breaker.allow()
    held = await admit(me, uuid.uuid4(), store, breaker=breaker)
    await held.release()


async def test_the_global_cap_holds_under_real_concurrency(store, async_engine):
    """More accounts than global slots, all at once: exactly INFLIGHT_GLOBAL get in."""
    people = [await account(store, async_engine, f"u{i}@example.com", f"ipk-{i}")
              for i in range(limits.INFLIGHT_GLOBAL + 8)]
    for _ in range(3):
        results = await asyncio.gather(*(admit(p, uuid.uuid4(), store) for p in people),
                                       return_exceptions=True)
        admitted = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]
        for e in errors:
            if not isinstance(e, ApiError):
                raise e
        assert len(admitted) == limits.INFLIGHT_GLOBAL
        assert {(e.status, e.code) for e in errors} == {(503, "server_busy")}
        for a in admitted:
            await a.release()
        await sql(async_engine, "DELETE FROM rate_counters")
        assert await leases(async_engine) == set()


async def test_one_principal_at_once_gets_exactly_one_lease(store):
    me = await guest(store)
    results = await asyncio.gather(*(admit(me, uuid.uuid4(), store) for _ in range(10)),
                                   return_exceptions=True)
    admitted = [r for r in results if not isinstance(r, Exception)]
    assert len(admitted) == 1
    assert all(r.code == "busy" for r in results if isinstance(r, Exception))
    await admitted[0].release()


async def test_a_crashed_request_frees_its_lease_after_60_seconds(store, async_engine):
    me = await guest(store)
    await admit(me, uuid.uuid4(), store)  # never released: the process died
    assert (await refused(me, store)).code == "busy"
    # Fake clock: 60 seconds later every lease of the dead request has expired
    await sql(async_engine, "UPDATE inflight_leases SET expires_at = now() - "
              "interval '1 second'")
    held = await admit(me, uuid.uuid4(), store)
    live = await sql(async_engine, "SELECT principal_key FROM inflight_leases "
                     "WHERE expires_at > now()")
    assert len(live) == 3  # the lease, an IP slot and a global slot, all this request's
    assert me.principal_key in {r[0] for r in live}
    await held.release()


async def test_slots_left_by_crashed_requests_are_taken_over(store, async_engine):
    """Every IP slot and every global slot held by expired leases: no wait for the job."""
    slots = [f"ip:ipk-a:{n}" for n in range(limits.INFLIGHT_PER_GUEST_IP)] + [
        f"global:{n}" for n in range(limits.INFLIGHT_GLOBAL)]
    for slot in slots:
        await sql(async_engine, "INSERT INTO inflight_leases VALUES (:k, 'dead', now() - "
                  "interval '1 second')", k=slot)
    held = await admit(await guest(store), uuid.uuid4(), store)
    mine = await sql(async_engine, "SELECT principal_key FROM inflight_leases "
                     "WHERE trace_id = :t", t=held.trace_id)
    assert len(mine) == 3
    await held.release()


async def test_a_lease_lasts_60_seconds(store, async_engine):
    held = await admit(await guest(store), uuid.uuid4(), store)
    left = await sql(async_engine, "SELECT max(extract(epoch FROM expires_at - now())) "
                     "FROM inflight_leases")
    assert 58 <= left[0][0] <= 60
    await held.release()


# --- Request caps ---


async def test_six_requests_a_minute_then_429(store):
    me = await guest(store)
    await not_near_window_end(60)
    for _ in range(limits.REQUESTS_PER_MINUTE):
        await (await admit(me, uuid.uuid4(), store)).release()
    error = await refused(me, store)
    assert (error.status, error.code) == (429, "too_fast")
    assert 1 <= error.retry_after <= 60


async def test_a_refused_request_counts_nowhere(store, async_engine):
    me = await guest(store)
    held = await admit(me, uuid.uuid4(), store)
    before = await counts(async_engine)
    for _ in range(5):
        assert (await refused(me, store)).code == "busy"
    assert await counts(async_engine) == before
    await held.release()


async def test_a_counter_refusal_takes_no_lease(store, async_engine):
    me = await guest(store)
    await seed_counter(async_engine, f"{me.principal_key}:minute", timedelta(minutes=1), 6)
    assert (await refused(me, store)).code == "too_fast"
    assert await leases(async_engine) == set()


async def test_a_guest_session_allows_30_requests(store, async_engine):
    me = await guest(store)
    key = f"{me.principal_key}:requests"
    await seed_counter(async_engine, key, limits.GUEST_SESSION_TTL, 29,
                       start=me.session.created_at)
    await (await admit(me, uuid.uuid4(), store)).release()
    error = await refused(me, store)
    assert (error.status, error.code) == (429, "cap_reached")
    assert "session" in error.message
    # Retry when the session ends: about 240 minutes from its start
    assert 230 * 60 <= error.retry_after <= 240 * 60
    # The session's count is one row for its whole life, whatever the clock says
    rows = await sql(async_engine, "SELECT window_start FROM rate_counters WHERE key = :k",
                     k=key)
    assert [r[0] for r in rows] == [me.session.created_at]


async def test_an_account_allows_30_requests_a_day(store, async_engine):
    me = await account(store, async_engine)
    await seed_counter(async_engine, f"{me.principal_key}:requests", timedelta(days=1), 30)
    error = await refused(me, store)
    assert (error.status, error.code) == (429, "cap_reached")
    assert "midnight" in error.message
    assert 1 <= error.retry_after <= 86400


async def test_a_guest_ip_key_stops_at_3x_its_allowance(store, async_engine):
    window = limits.GUEST_IP_WINDOW
    hard_stop = limits.GUEST_IP_REQUESTS * limits.GUEST_IP_HARD_STOP_FACTOR
    # Past the allowance (60) requests still run; new sessions need the interactive check
    await seed_counter(async_engine, ip_requests_key("ipk-a"), window, hard_stop - 1)
    await (await admit(await guest(store), uuid.uuid4(), store)).release()
    error = await refused(await guest(store), store)
    assert (error.status, error.code) == (429, "cap_reached")
    assert "network" in error.message
    assert 1 <= error.retry_after <= window.total_seconds()
    # The same IP key's accounts are not guests: no IP cap
    await (await admit(await account(store, async_engine), uuid.uuid4(), store)).release()


# --- Spend caps ---


@pytest.mark.parametrize("cost, reserved", [("0.05", "0"), ("0.03", "0.02"), ("0.06", "0")])
async def test_a_guest_session_at_its_spend_cap_is_429(store, async_engine, cost, reserved):
    me = await guest(store)
    own = spend_keys(me)[0]
    assert own.cap_usd == limits.GUEST_SESSION_USD
    await seed_spend(async_engine, own, cost, reserved)
    error = await refused(me, store)
    assert (error.status, error.code) == (429, "cap_reached")
    assert 230 * 60 <= error.retry_after <= 240 * 60
    assert await leases(async_engine) == set() and await counts(async_engine) == {}


async def test_a_guest_session_just_under_its_cap_gets_in(store, async_engine):
    me = await guest(store)
    await seed_spend(async_engine, spend_keys(me)[0], "0.049999")
    await (await admit(me, uuid.uuid4(), store)).release()


async def test_an_account_at_its_daily_spend_cap_is_429(store, async_engine):
    me = await account(store, async_engine)
    await seed_spend(async_engine, spend_keys(me)[0], "0.05")
    error = await refused(me, store)
    assert (error.status, error.code) == (429, "cap_reached")
    assert "today" in error.message


async def test_a_guest_ip_key_at_3x_its_spend_is_429(store, async_engine):
    key = ip_spend_key("ipk-a")
    await seed_spend(async_engine, key, "0.29")
    await (await admit(await guest(store), uuid.uuid4(), store)).release()
    await sql(async_engine, "UPDATE spend SET cost_usd = 0.30 WHERE key = :k", k=key.key)
    error = await refused(await guest(store), store)
    assert (error.status, error.code) == (429, "cap_reached")
    assert "network" in error.message


async def test_call_meter_settles_keeps_or_releases_in_the_real_store(store, async_engine):
    me = await guest(store)
    keys = spend_keys(me)
    meter = CallMeter(Budget(store), keys, tokens_in=2000)
    options = GenerateOptions(model="gpt-6-luna", max_output_tokens=2200)
    full = max_call_usd("gpt-6-luna", 2000, 2200)

    async def spent() -> tuple[Decimal, Decimal]:
        row = await sql(async_engine, "SELECT cost_usd, reserved_usd FROM spend "
                        "WHERE key = :k", k=keys[0].key)
        return row[0][0], row[0][1]

    hold = await meter.reserve(options)
    assert await spent() == (0, full)
    await meter.keep(hold)  # timed out or cancelled: spent at the maximum
    assert await spent() == (full, 0)
    hold = await meter.reserve(options)
    await meter.release(hold)  # a 429 or 5xx: not billed
    assert await spent() == (full, 0)
    hold = await meter.reserve(options)
    await meter.settle(hold, options, Usage(tokens_in=2000, tokens_out=100))
    assert await spent() == (full + call_usd("gpt-6-luna", Usage(2000, 100)), 0)


async def test_the_global_daily_budget_is_429(store, async_engine):
    me = await guest(store)
    await seed_spend(async_engine, spend_keys(me)[2], "0.75")
    error = await refused(me, store)
    assert (error.status, error.code) == (429, "cap_reached")
    assert "tomorrow" in error.message
    assert 1 <= error.retry_after <= 86400
    # Accounts too
    error = await refused(await account(store, async_engine), store)
    assert error.code == "cap_reached"


async def test_the_monthly_budget_says_so(store, async_engine):
    me = await guest(store)
    await seed_spend(async_engine, spend_keys(me)[3], "10")
    error = await refused(me, store)
    assert (error.status, error.code) == (429, "month_budget_used")
    assert "month" in error.message
    now = datetime.now(UTC)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)
    assert abs(error.retry_after - (next_month - now).total_seconds()) <= 3


# --- Restart and duplicates ---


async def test_counters_and_leases_survive_an_app_restart(store, async_engine):
    me = await guest(store)
    await not_near_window_end(60)
    for _ in range(limits.REQUESTS_PER_MINUTE - 1):
        await (await admit(me, uuid.uuid4(), store)).release()
    await admit(me, uuid.uuid4(), store)  # in flight when the app restarts
    fresh = make_async_engine(TEST_URL)  # a restart: new engine, new pool, new store
    try:
        restarted = StateStore(fresh)
        assert (await refused(me, restarted)).code == "busy"
        await sql(fresh, "DELETE FROM inflight_leases")
        assert (await refused(me, restarted)).code == "too_fast"
    finally:
        await fresh.dispose()


async def test_a_duplicate_client_request_id_is_409_before_any_stream(store, async_engine):
    me = await account(store, async_engine)
    rid = uuid.uuid4()
    await (await admit(me, rid, store)).release()
    error = await refused(me, store, rid)
    assert error.status == 409 and error.code == "duplicate_request"
    assert error.retry_after is None
    # The duplicate took nothing: no lease, no count
    assert await leases(async_engine) == set()
    assert (await counts(async_engine))[f"{me.principal_key}:minute"] == 1


async def test_a_refused_request_does_not_use_up_its_request_id(store, async_engine):
    me = await account(store, async_engine)
    held = await admit(me, uuid.uuid4(), store)
    rid = uuid.uuid4()
    assert (await refused(me, store, rid)).code == "busy"
    await held.release()
    await (await admit(me, rid, store)).release()  # the retry of the refused send works


async def test_a_duplicate_while_the_first_is_in_flight_is_409(store, async_engine):
    me = await account(store, async_engine)
    rid = uuid.uuid4()
    held = await admit(me, rid, store)
    assert (await refused(me, store, rid)).code == "duplicate_request"
    await held.release()


async def test_guests_have_no_request_claims(store, async_engine):
    me = await guest(store)
    rid = uuid.uuid4()
    await (await admit(me, rid, store)).release()
    await (await admit(me, rid, store)).release()
    assert await sql(async_engine, "SELECT * FROM request_claims") == []


async def test_admitted_carries_the_spend_and_search_keys(store, async_engine):
    me = await guest(store)
    held = await admit(me, uuid.uuid4(), store, billing_day=15)
    assert [k.name for k in held.spend_keys] == ["session", "ip", "global_day",
                                                 "global_month"]
    assert [k.cap_credits for k in held.search_keys] == [5, 10, 40, 800]
    assert held.search_keys[-1].period_start.day == 15
    assert held.trace_id and len(held.trace_id) <= 64
    await held.release()


async def test_admission_holds_no_connection(store, async_engine):
    held = await admit(await guest(store), uuid.uuid4(), store)
    assert async_engine.pool.checkedout() == 0
    await held.release()


# --- An image over a cap is refused before it is decoded ---


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), "red").save(out, "JPEG")
    return out.getvalue()


async def test_an_image_request_over_a_cap_is_refused_before_the_image_is_decoded(
    store, async_engine, monkeypatch
):
    """Stages 2, 4, 6, 7 in order. P4.7's test_chat repeats this on the real endpoint."""
    cfg = settings()
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.dependency_overrides.update({get_settings: lambda: cfg, get_state_store: lambda: store})

    @app.post("/chat")
    async def chat(request: Request, principal: Principal = Depends(get_principal)):
        intake = await read_chat_request(request)
        admitted = await admit(principal, uuid.UUID(intake.payload["client_request_id"]),
                               store)
        try:
            await clean_image(intake.image)
        finally:
            await admitted.release()
        return {"ok": True}

    me = await guest(store)
    await seed_spend(async_engine, spend_keys(me)[0], "0.05")
    opened = []
    monkeypatch.setattr(Image, "open", lambda *a, **k: opened.append(1) or 1 / 0)

    boundary = "b0undary"
    payload = json.dumps({"message": "what's in this?", "client_request_id": str(uuid.uuid4())})
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload\"\r\n\r\n"
            f"{payload}\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"m.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").encode() + _jpeg() + (
            f"\r\n--{boundary}--\r\n").encode()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://testserver") as client:
        response = await client.post(
            "/chat", content=body,
            headers={"content-type": f"multipart/form-data; boundary={boundary}",
                     "origin": APP, "x-csrf-token": csrf_token(me.raw_session_id, cfg)},
            cookies={cfg.session_cookie: me.raw_session_id})
    assert response.status_code == 429
    assert response.json()["code"] == "cap_reached"
    assert response.headers["retry-after"] == str(response.json()["retry_after"])
    assert opened == []


# --- Flood limit (stage 1) ---


def flood_app(store, cfg, broken=False) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    class Broken:
        async def hit_rate(self, *a, **k):
            raise ConnectionError("database down")

    app.add_middleware(FloodLimit, store=(lambda: Broken()) if broken else (lambda: store),
                       settings=lambda: cfg)
    app.add_middleware(CORSMiddleware, allow_origins=[APP], allow_credentials=True,
                       allow_methods=["GET", "POST"], allow_headers=["X-CSRF-Token"])
    app.add_middleware(SecurityHeaders)
    return app


def client_for(app, ip="203.0.113.7") -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(ip, 5000)),
                             base_url="http://testserver", headers={"origin": APP})


async def test_the_101st_request_in_a_minute_is_429_with_cors_headers(store):
    app = flood_app(store, settings())
    await not_near_window_end(60, margin=10)
    async with client_for(app) as c:
        codes = [(await c.get("/ping")).status_code
                 for _ in range(limits.FLOOD_REQUESTS_PER_MINUTE)]
        assert set(codes) == {200}
        response = await c.get("/ping")
    assert response.status_code == 429
    assert response.json()["code"] == "flood"
    assert 1 <= int(response.headers["retry-after"]) <= 60
    assert response.headers["access-control-allow-origin"] == APP
    assert response.headers["x-content-type-options"] == "nosniff"
    # Another IP key is not affected
    async with client_for(app, "198.51.100.9") as other:
        assert (await other.get("/ping")).status_code == 200


async def test_the_flood_count_is_per_ip_key_in_postgres(store, async_engine):
    cfg = settings()
    async with client_for(flood_app(store, cfg)) as c:
        await c.get("/ping")
        await c.get("/ping")
    key = flood_key(ip_key("203.0.113.7", cfg))
    assert (await counts(async_engine)) == {key: 2}


async def test_preflights_and_health_checks_do_not_count(store, async_engine):
    # CORS sits outside the flood limit and answers preflights itself (main.py order,
    # test_route_security)
    async with client_for(flood_app(store, settings())) as c:
        preflight = await c.options("/ping", headers={"access-control-request-method": "GET"})
        assert preflight.status_code == 200
        assert (await c.get("/health")).status_code == 200
    assert await counts(async_engine) == {}


async def test_a_database_outage_lets_requests_through(store, caplog):
    """The crisis stream needs no database; the flood limit must not take it down."""
    async with client_for(flood_app(store, settings(), broken=True)) as c:
        assert (await c.get("/ping")).status_code == 200
    assert "flood counter unavailable" in caplog.text


async def test_an_unreachable_database_costs_one_request_half_a_second_at_most(
    store, monkeypatch
):
    """An unreachable host (not a refused port) holds a connect for 75 s; the crisis
    stream must not wait for it."""
    from app.middleware import flood

    calls = []

    class Hanging:
        async def hit_rate(self, *a, **k):
            calls.append(1)
            await asyncio.sleep(3600)

    clock = [1000.0]
    monkeypatch.setattr(flood, "_clock", lambda: clock[0])
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    app.add_middleware(FloodLimit, store=lambda: Hanging(), settings=settings)
    async with client_for(app) as c:
        started = time.perf_counter()
        assert (await c.get("/ping")).status_code == 200
        assert time.perf_counter() - started < 1.0
        started = time.perf_counter()
        for _ in range(5):
            assert (await c.get("/ping")).status_code == 200
        assert time.perf_counter() - started < 0.2  # skipped: no wait at all
        assert len(calls) == 1
        clock[0] += flood.SKIP_AFTER_FAILURE_S + 0.1  # 5 s later the check runs again
        await c.get("/ping")
        assert len(calls) == 2


async def test_every_response_says_nosniff(store):
    async with client_for(flood_app(store, settings())) as c:
        response = await c.get("/ping")
    assert response.headers["x-content-type-options"] == "nosniff"


# --- Login limits (Part E #25) ---


@pytest_asyncio.fixture
async def login_world(store, async_engine, monkeypatch):
    cfg = settings()
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(auth.router)
    db_sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    app.dependency_overrides.update({get_settings: lambda: cfg, get_state_store: lambda: store,
                                     get_db_sessions: lambda: db_sessions})
    await make_user(async_engine, password_hash=passwords.get_password_hash(PASSWORD))
    checks = []
    real_verify, real_unknown = auth.verify_password, auth.verify_unknown_user
    monkeypatch.setattr(auth, "verify_password",
                        lambda *a: checks.append("known") or real_verify(*a))
    monkeypatch.setattr(auth, "verify_unknown_user",
                        lambda *a: checks.append("unknown") or real_unknown(*a))

    def client(ip="203.0.113.7"):
        return client_for(app, ip)

    return client, checks


async def login(c, password=PASSWORD, email="ved@example.com"):
    return await c.post("/auth/login", json={"email": email, "password": password})


async def test_the_11th_login_attempt_from_one_ip_key_is_429_without_bcrypt(login_world):
    client, checks = login_world
    await not_near_window_end(900)
    async with client() as c:
        for n in range(limits.LOGIN_ATTEMPTS_PER_IP):
            email = f"nobody{n}@example.com"  # unknown accounts: only the IP limit applies
            assert (await login(c, "wrong-password", email)).status_code == 401
        assert len(checks) == limits.LOGIN_ATTEMPTS_PER_IP
        response = await login(c)  # even the right password
    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "too_many_logins"
    assert "try again in" in body["message"]
    assert 1 <= int(response.headers["retry-after"]) <= 900
    assert len(checks) == limits.LOGIN_ATTEMPTS_PER_IP  # no bcrypt for the refused attempt


async def test_five_failures_lock_the_account_from_every_ip(login_world):
    client, checks = login_world
    await not_near_window_end(900)
    for n in range(limits.LOGIN_FAILURES_PER_ACCOUNT):
        async with client(f"198.51.100.{n + 1}") as c:
            assert (await login(c, "wrong-password")).status_code == 401
    async with client("192.0.2.200") as c:
        response = await login(c)  # right password, fresh IP
        # Case and spaces don't make it another account
        shouted = await login(c, email="  VED@Example.com")
    assert response.status_code == 429
    assert response.json()["code"] == "too_many_logins"
    assert shouted.status_code == 429
    assert len(checks) == limits.LOGIN_FAILURES_PER_ACCOUNT


async def test_a_successful_login_does_not_count_as_a_failure(login_world):
    client, _ = login_world
    await not_near_window_end(900)
    async with client() as c:
        for _ in range(limits.LOGIN_FAILURES_PER_ACCOUNT - 1):
            assert (await login(c, "wrong-password")).status_code == 401
        assert (await login(c)).status_code == 200
    async with client("198.51.100.1") as c:
        assert (await login(c, "wrong-password")).status_code == 401  # 5th failure
        assert (await login(c)).status_code == 429


async def test_failures_at_the_same_moment_cannot_pass_the_account_limit(login_world):
    client, checks = login_world
    await not_near_window_end(900, margin=20)
    clients = [client(f"198.51.100.{n + 1}") for n in range(12)]
    results = await asyncio.gather(*(login(c, "wrong-password") for c in clients))
    for c in clients:
        await c.aclose()
    statuses = sorted(r.status_code for r in results)
    assert statuses.count(401) == limits.LOGIN_FAILURES_PER_ACCOUNT
    assert statuses.count(429) == 12 - limits.LOGIN_FAILURES_PER_ACCOUNT
    assert len(checks) == limits.LOGIN_FAILURES_PER_ACCOUNT


async def test_login_counters_never_store_the_email(login_world, async_engine):
    client, _ = login_world
    async with client() as c:
        await login(c, "wrong-password")
    keys = " ".join((await counts(async_engine)).keys())
    assert "ved" not in keys and "example" not in keys
    assert "login:account:" in keys and "login:ip:" in keys


# --- Budget: reserve before each call, settle after it (C.13) ---


async def spent(store, k):
    row = await store.spend(k.key, k.period, k.period_start)
    return (row["cost_usd"], row["reserved_usd"]) if row else None


async def test_a_reservation_holds_every_key_and_settles_to_the_reported_cost(store):
    me = await guest(store)
    keys = spend_keys(me)
    money = Budget(store)
    held = await money.reserve_call(keys, "gpt-6-luna", 3_000, 2_200)
    assert held is not None
    for k in keys:
        assert await spent(store, k) == (Decimal("0"), Decimal("0.0014"))
    await money.settle_call(held, "gpt-6-luna", Usage(3_000, 400))
    for k in keys:
        assert await spent(store, k) == (Decimal("0.0005"), Decimal("0"))
    row = await store.spend(keys[0].key, keys[0].period, keys[0].period_start)
    assert (row["tokens_in"], row["tokens_out"]) == (3_000, 400)


async def test_a_call_that_would_pass_a_cap_does_not_run(store, async_engine):
    me = await guest(store)
    keys = spend_keys(me)
    await seed_spend(async_engine, keys[0], "0.049")
    money = Budget(store)
    assert await money.reserve_call(keys, "gpt-6-luna", 3_000, 2_200) is None  # 0.0014
    for k in keys[1:]:
        assert await spent(store, k) is None  # nothing reserved anywhere
    held = await money.reserve_call(keys, "gpt-6-luna", 1_000, 1_000)  # 0.0006 fits
    assert held is not None
    await money.cancel(held)
    assert await spent(store, keys[0]) == (Decimal("0.049"), Decimal("0"))


async def test_calls_at_the_same_moment_cannot_pass_a_cap_together(store, async_engine):
    me = await guest(store)
    keys = spend_keys(me)
    money = Budget(store)
    # $0.0014 each: 35 fit under $0.05, never 36
    results = await asyncio.gather(*(money.reserve_call(keys, "gpt-6-luna", 3_000, 2_200)
                                     for _ in range(50)))
    assert sum(r is not None for r in results) == 35
    cost, reserved = await spent(store, keys[0])
    assert reserved == Decimal("0.049") and reserved <= limits.GUEST_SESSION_USD


# --- Locks: deterministic checks (a second connection holds the lock) ---


async def test_a_slot_passed_over_keeps_no_lock(store, async_engine):
    """The deadlock fix: scanning past a taken slot must not lock it until commit."""
    await sql(async_engine, "INSERT INTO inflight_leases VALUES ('global:0', 'other', "
              "now() + interval '50 seconds')")
    async with async_engine.connect() as scanner, async_engine.connect() as probe:
        await scanner.begin()
        await store._take_slot(scanner, ["global:0", "global:1"], "mine", "global_slot")
        # Still inside the scanner's transaction: global:0 must be free to lock
        await probe.begin()
        locked = await probe.execute(text(
            "SELECT trace_id FROM inflight_leases WHERE principal_key = 'global:0' "
            "FOR UPDATE NOWAIT"))
        assert locked.scalar() == "other"
        await probe.rollback()
        await scanner.rollback()


async def test_admit_waits_for_a_locked_counter_and_then_goes_on(store, async_engine):
    """Two guests on one network share the IP counter row: the second waits, never fails."""
    me = await guest(store)
    await seed_counter(async_engine, ip_requests_key("ipk-a"), limits.GUEST_IP_WINDOW, 1)
    async with async_engine.connect() as holder:
        await holder.begin()
        await holder.execute(text("SELECT 1 FROM rate_counters WHERE key = :k FOR UPDATE"),
                             {"k": ip_requests_key("ipk-a")})
        task = asyncio.create_task(admit(me, uuid.uuid4(), store))
        await asyncio.sleep(0.3)
        assert not task.done()  # waiting on the row, not refused
        await holder.rollback()
    held = await asyncio.wait_for(task, 5)
    assert (await counts(async_engine))[ip_requests_key("ipk-a")] == 2
    await held.release()


# --- Randomized stress with invariant monitors ---


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
async def test_admission_invariants_under_random_load(store, async_engine, monkeypatch, seed):
    """Guests on 3 networks and accounts, random hold times. At no moment: two requests
    of one principal, more than 3 per network, more than the global cap; and every
    admitted request is counted exactly once."""
    import random

    rng = random.Random(seed)
    cap = 8  # above 3 per network, so the network slots are what binds a busy network
    monkeypatch.setattr(limits, "INFLIGHT_GLOBAL", cap)
    monkeypatch.setattr(limits, "REQUESTS_PER_MINUTE", 10**6)
    monkeypatch.setattr(limits, "GUEST_SESSION_REQUESTS", 10**6)
    monkeypatch.setattr(limits, "ACCOUNT_DAY_REQUESTS", 10**6)
    monkeypatch.setattr(limits, "GUEST_IP_REQUESTS", 10**6)
    people = [await guest(store, f"net{n % 2}") for n in range(14)]
    people += [await account(store, async_engine, f"s{n}@example.com", f"net{n % 2}")
               for n in range(6)]
    active: dict[str, int] = {}
    admitted_by: dict[str, int] = {}
    violations: list[str] = []
    peak = {"net": 0, "global": 0}
    stop = asyncio.Event()

    def check() -> None:
        nets: dict[str, int] = {}
        for p in people:
            if active.get(p.principal_key) and p.user_id is None:
                nets[p.ip_key] = nets.get(p.ip_key, 0) + 1
        if any(n > limits.INFLIGHT_PER_GUEST_IP for n in nets.values()):
            violations.append(f"network over 3: {nets}")
        if sum(active.values()) > cap:
            violations.append(f"global over {cap}: {sum(active.values())}")
        peak["net"] = max([peak["net"], *nets.values()])
        peak["global"] = max(peak["global"], sum(active.values()))

    async def monitor() -> None:
        while not stop.is_set():
            rows = await sql(async_engine, "SELECT count(*) FILTER (WHERE principal_key "
                             "LIKE 'global:%'), count(*) FILTER (WHERE principal_key LIKE "
                             "'ip:net0:%') FROM inflight_leases WHERE expires_at > now()")
            if rows[0][0] > cap or rows[0][1] > 3:
                violations.append(f"db rows {rows[0]}")
            await asyncio.sleep(0.005)

    async def person(p: Principal) -> None:
        for _ in range(8):
            await asyncio.sleep(rng.random() * 0.02)
            try:
                held = await admit(p, uuid.uuid4(), store)
            except ApiError as error:
                assert error.code in ("busy", "network_busy", "server_busy"), error.code
                continue
            if active.get(p.principal_key):
                violations.append(f"two at once: {p.principal_key}")
            active[p.principal_key] = 1
            admitted_by[p.principal_key] = admitted_by.get(p.principal_key, 0) + 1
            check()
            await asyncio.sleep(0.02 + rng.random() * 0.05)
            active[p.principal_key] = 0
            await held.release()

    watcher = asyncio.create_task(monitor())
    await asyncio.gather(*(person(p) for p in people))
    stop.set()
    await watcher
    assert violations == []
    assert sum(admitted_by.values()) > 20  # the load really ran
    assert peak["net"] == 3  # a network was really full at some moment
    assert await leases(async_engine) == set()
    # Every counter counted each admitted request exactly once (summed over windows)
    totals = dict(await sql(async_engine, "SELECT key, sum(count) FROM rate_counters "
                            "GROUP BY key"))
    for net in ("net0", "net1"):
        admitted_here = sum(n for k, n in admitted_by.items()
                            if any(p.principal_key == k and p.user_id is None
                                   and p.ip_key == net for p in people))
        assert totals.get(ip_requests_key(net), 0) == admitted_here
    for p in people:
        mine = admitted_by.get(p.principal_key, 0)
        assert totals.get(f"{p.principal_key}:requests", 0) == mine
        assert totals.get(f"{p.principal_key}:minute", 0) == mine


# --- Time zones: a database session in another zone hits the same rows ---


async def test_a_connection_in_another_time_zone_counts_against_the_same_rows(store,
                                                                            async_engine):
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.data.engine import psycopg_url

    me = await guest(store)
    await (await admit(me, uuid.uuid4(), store)).release()
    ist = create_async_engine(psycopg_url(TEST_URL),
                              connect_args={"options": "-c timezone=Asia/Kolkata"})
    try:
        other = StateStore(ist)
        _, again = await other.create_session("guest", "ipk-a")
        assert again.created_at.utcoffset() == timedelta(hours=5, minutes=30)
        await (await admit(me, uuid.uuid4(), other)).release()
        keys = spend_keys(me)
        held = await Budget(other).reserve_call(keys, "gpt-6-luna", 100, 100)
        await Budget(store).settle_call(held, "gpt-6-luna", Usage(100, 100))
    finally:
        await ist.dispose()
    c = await counts(async_engine)
    assert c[f"{me.principal_key}:requests"] == 2  # one row, not one per zone
    assert c[ip_requests_key("ipk-a")] == 2
    rows = await sql(async_engine, "SELECT key, period, reserved_usd FROM spend")
    assert len(rows) == 4 and all(r[2] == 0 for r in rows)  # settled on the same rows


# --- Consistency between admission and session start ---


async def test_admitted_requests_are_what_session_start_sees(store, async_engine):
    """60 real admissions on one network → the next session needs the interactive check."""
    from app.orchestration.sessions import start_guest

    cfg = settings()
    key = ip_key("203.0.113.7", cfg)
    for n in range(limits.GUEST_IP_REQUESTS):
        if n % limits.REQUESTS_PER_MINUTE == 0:
            me = await guest(store, key)
        await (await admit(me, uuid.uuid4(), store)).release()

    class Turnstile:
        secrets = []

        async def verify(self, token, secret, ip):
            self.secrets.append(secret)
            return True

    class FakeRequest:
        client = type("C", (), {"host": "203.0.113.7"})()
        headers: dict = {}
        cookies: dict = {}

    cfg = Settings(**{**cfg.__dict__, "turnstile_interactive_secret": "interactive"})
    turnstile = Turnstile()
    await start_guest(FakeRequest(), "token", store, turnstile, cfg)
    assert turnstile.secrets == ["interactive"]


async def test_reserved_spend_is_what_session_start_sees(store, async_engine):
    """Reservations (not only settled cost) on a network trigger the step-up at $0.10."""
    from app.orchestration.sessions import start_guest

    cfg = settings()
    key = ip_key("203.0.113.7", cfg)
    money = Budget(store)
    call = ("gemini-3.5-flash-lite", 10_000, 1_400)  # $0.0065 each

    class Turnstile:
        def __init__(self):
            self.secrets = []

        async def verify(self, token, secret, ip):
            self.secrets.append(secret)
            return True

    class FakeRequest:
        client = type("C", (), {"host": "203.0.113.7"})()
        headers: dict = {}
        cookies: dict = {}

    async def secret_used() -> str:
        turnstile = Turnstile()
        await start_guest(FakeRequest(), "t", store, turnstile, cfg)
        return turnstile.secrets[0]

    first = await guest(store, key)
    results = [await money.reserve_call(spend_keys(first), *call) for _ in range(8)]
    assert [r is not None for r in results] == [True] * 7 + [False]  # session cap $0.05
    second = await guest(store, key)
    for _ in range(7):
        assert await money.reserve_call(spend_keys(second), *call)
    assert await secret_used() == cfg.turnstile_secret  # $0.091 reserved: under $0.10
    third = await guest(store, key)
    for _ in range(2):
        assert await money.reserve_call(spend_keys(third), *call)
    assert await secret_used() == cfg.turnstile_interactive_secret  # $0.104


# --- Middleware: streaming, other scopes, existing headers ---


async def test_a_stream_passes_through_the_middleware_chunk_by_chunk(store):
    """Driven as raw ASGI: httpx's ASGITransport buffers the whole body, so it can't
    show that the first event leaves before the stream ends."""
    from fastapi.responses import StreamingResponse

    app = flood_app(store, settings())
    sent_second = asyncio.Event()

    @app.get("/stream")
    async def stream():
        async def body():
            yield b"event: accepted\n\n"
            await sent_second.wait()
            yield b"event: done\n\n"
        return StreamingResponse(body(), media_type="text/event-stream",
                                 headers={"X-Content-Type-Options": "nosniff"})

    out: asyncio.Queue = asyncio.Queue()
    disconnect = asyncio.Event()

    async def receive():
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        await out.put(message)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "GET", "scheme": "http", "path": "/stream", "raw_path": b"/stream",
             "query_string": b"", "root_path": "", "headers": [(b"host", b"testserver")],
             "client": ("203.0.113.7", 5000), "server": ("testserver", 80)}
    task = asyncio.create_task(app(scope, receive, send))
    start = await asyncio.wait_for(out.get(), 2)
    assert start["type"] == "http.response.start"
    names = [k for k, _ in start["headers"]]
    assert names.count(b"x-content-type-options") == 1  # the route's own, not twice
    first = await asyncio.wait_for(out.get(), 2)
    assert first["body"] == b"event: accepted\n\n"  # sent while the stream is still open
    assert not task.done()
    sent_second.set()
    second = await asyncio.wait_for(out.get(), 2)
    assert second["body"] == b"event: done\n\n"
    disconnect.set()
    await asyncio.wait_for(task, 2)


async def test_lifespan_and_other_scopes_pass_through(store):
    app = flood_app(store, settings())
    started = []
    app.router.on_startup.append(lambda: started.append(True))
    async with app.router.lifespan_context(app):
        pass
    # Raw ASGI lifespan through the middleware stack
    messages = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message["type"])

    await app({"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}, receive, send)
    assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


async def test_concurrent_requests_from_one_ip_get_exactly_100(store):
    app = flood_app(store, settings())
    await not_near_window_end(60, margin=10)
    async with client_for(app) as c:
        responses = await asyncio.gather(*(c.get("/ping") for _ in range(150)))
    codes = sorted(r.status_code for r in responses)
    assert codes.count(200) == limits.FLOOD_REQUESTS_PER_MINUTE
    assert codes.count(429) == 50


# --- Login edge cases ---


async def test_an_inactive_account_with_the_right_password_is_not_a_failure(login_world,
                                                                            async_engine):
    client, _ = login_world
    await sql(async_engine, "UPDATE users SET is_active = false")
    async with client() as c:
        assert (await login(c)).status_code == 403
    c = await counts(async_engine)
    assert [v for k, v in c.items() if k.startswith("login:account:")] == [0]


async def test_a_malformed_login_body_counts_nowhere(login_world, async_engine):
    client, checks = login_world
    async with client() as c:
        for body in ({}, {"email": "not-an-email", "password": "x"}, {"email": "a@b.co"}):
            assert (await c.post("/auth/login", json=body)).status_code == 422
    assert await counts(async_engine) == {} and checks == []
