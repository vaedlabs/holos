"""Sessions, login, invites and CSRF on a real Postgres (Plan C.6, C.18, P4.2).

Turnstile is a fake transport that answers like Cloudflare's published test secrets
(Part D); the live check is in tests/paid/test_turnstile_live.py.
"""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import sessionmaker

from app.cli import create_invite
from app.config import limits
from app.config.settings import Settings, get_settings
from app.data.state_store import StateStore, hash_session_id
from app.dependencies import get_database, get_db_sessions, get_state_store, get_turnstile
from app.orchestration.passwords import get_password_hash
from app.orchestration.principal import csrf_token, ip_key, ip_new_sessions_key, ip_requests_key
from app.orchestration.sessions import SITEVERIFY_URL, Turnstile
from app.routers import auth, preferences, session
from app.routers.errors import ApiError, api_error_handler

pytestmark = pytest.mark.asyncio

PASS = "1x0000000000000000000000000000000AA"
FAIL = "2x0000000000000000000000000000000AA"
SPENT = "3x0000000000000000000000000000000AA"
INTERACTIVE = "1x-interactive-test-secret"  # passes in the fake, like PASS
TOKEN = "XXXX.DUMMY.TOKEN.XXXX"
APP = "http://localhost:3000"
PASSWORD = "Correct-Horse-1"


def settings(**overrides) -> Settings:
    values = dict(session_secret=b"s" * 40, ip_salt_secret=b"i" * 40, app_origin=APP,
                  api_origin="http://localhost:8000", trusted_proxy="none",
                  turnstile_secret=PASS, turnstile_interactive_secret=INTERACTIVE,
                  environment="test")
    return Settings(**{**values, **overrides})


class FakeCloudflare:
    """siteverify as Cloudflare's test secrets behave; records every call."""

    def __init__(self):
        self.calls: list[dict] = []
        self.mode = "normal"  # or "down", "500", "garbage", "list"

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == SITEVERIFY_URL
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        self.calls.append(form)
        if self.mode == "down":
            raise httpx.ConnectError("no route")
        if self.mode == "500":
            return httpx.Response(500)
        if self.mode == "garbage":
            return httpx.Response(200, content=b"<html>")
        if self.mode == "list":
            return httpx.Response(200, json=[True])
        secret = form["secret"]
        if secret in (PASS, INTERACTIVE):
            return httpx.Response(200, json={"success": True, "error-codes": []})
        if secret == SPENT:
            return httpx.Response(200, json={"success": False,
                                             "error-codes": ["timeout-or-duplicate"]})
        if secret == FAIL:
            return httpx.Response(200, json={"success": False,
                                             "error-codes": ["invalid-input-response"]})
        # Any other secret: Cloudflare answers HTTP 400 (live check, Part D)
        return httpx.Response(400, json={"success": False,
                                         "error-codes": ["invalid-input-secret"]})


@pytest_asyncio.fixture
async def world(async_engine, migrated):
    cloudflare = FakeCloudflare()
    cfg = {"settings": settings()}
    store = StateStore(async_engine)
    db_sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    sync_sessions = sessionmaker(bind=migrated)

    def sync_db():
        db = sync_sessions()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    for router in (session.router, auth.router, auth.invites_router, preferences.router):
        app.include_router(router)
    turnstile = Turnstile(httpx.AsyncClient(transport=httpx.MockTransport(cloudflare.handler)))
    app.dependency_overrides.update({
        get_settings: lambda: cfg["settings"], get_state_store: lambda: store,
        get_turnstile: lambda: turnstile, get_db_sessions: lambda: db_sessions,
        get_database: sync_db,
    })

    class World:
        pass

    w = World()
    w.app, w.store, w.cloudflare, w.cfg, w.engine = app, store, cloudflare, cfg, async_engine
    w.db_sessions = db_sessions

    def client(ip="203.0.113.7") -> httpx.AsyncClient:
        transport = httpx.ASGITransport(app=app, client=(ip, 50000))
        return httpx.AsyncClient(transport=transport, base_url="http://testserver",
                                 headers={"origin": APP})

    w.client = client
    yield w


async def start(client, token=TOKEN) -> httpx.Response:
    return await client.post("/session/start", json={"turnstile_token": token})


async def sql(world, statement: str, **params):
    async with world.engine.begin() as conn:
        result = await conn.execute(text(statement), params)
        return result.all() if result.returns_rows else []


async def make_user(world, email="ved@example.com", password=PASSWORD, active=True,
                    password_hash=None) -> int:
    rows = await sql(world, "INSERT INTO users (email, username, password_hash, is_active) "
                     "VALUES (:e, :e, :h, :a) RETURNING id", e=email,
                     h=password_hash or get_password_hash(password), a=active)
    return rows[0][0]


async def login(client, email="ved@example.com", password=PASSWORD) -> httpx.Response:
    return await client.post("/auth/login", json={"email": email, "password": password})


def csrf(response: httpx.Response) -> dict:
    return {"x-csrf-token": response.json()["csrf_token"]}


# --- Guest sessions and Turnstile ---


async def test_guest_start_sets_the_cookie_and_returns_the_csrf_token(world):
    async with world.client() as client:
        response = await start(client)
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "guest"
    cookie = response.headers["set-cookie"]
    raw = client.cookies["holos_session"]
    assert body["csrf_token"] == csrf_token(raw, world.cfg["settings"])
    lowered = cookie.lower()
    assert "httponly" in lowered and "samesite=lax" in lowered and "path=/" in lowered
    assert "domain=" not in lowered and "secure" not in lowered  # http dev: no Secure
    assert f"max-age={int(limits.GUEST_SESSION_TTL.total_seconds())}" in lowered
    rows = await sql(world, "SELECT id_hash, mode, user_id, ip_key, expires_at - created_at "
                     "FROM sessions")
    assert len(rows) == 1
    id_hash, mode, user_id, key, lifetime = rows[0]
    assert id_hash == hash_session_id(raw) and raw not in id_hash  # only the hash is stored
    assert (mode, user_id) == ("guest", None)
    assert "203.0.113.7" not in key and key == ip_key("203.0.113.7", world.cfg["settings"])
    assert lifetime == limits.GUEST_SESSION_TTL
    assert world.cloudflare.calls == [{"secret": PASS, "response": TOKEN,
                                       "remoteip": "203.0.113.7"}]


@pytest.mark.parametrize("secret", [FAIL, SPENT])
async def test_a_failed_turnstile_check_starts_nothing(world, secret):
    world.cfg["settings"] = settings(turnstile_secret=secret)
    async with world.client() as client:
        response = await start(client)
    assert response.status_code == 403
    assert response.json()["code"] == "turnstile_failed"
    assert "set-cookie" not in response.headers
    assert await sql(world, "SELECT 1 FROM sessions") == []


@pytest.mark.parametrize("mode", ["down", "500", "garbage", "list"])
async def test_turnstile_unavailable_fails_closed_with_503(world, mode):
    world.cloudflare.mode = mode
    async with world.client() as client:
        response = await start(client)
    assert response.status_code == 503
    assert response.json()["code"] == "turnstile_unavailable"
    assert response.headers["retry-after"] == "5"
    assert await sql(world, "SELECT 1 FROM sessions") == []


async def test_a_rejected_secret_is_a_logged_deployment_error_not_a_403(world, caplog):
    world.cfg["settings"] = settings(turnstile_secret="wrong-secret-in-env")
    async with world.client() as client:
        response = await start(client)
    assert response.status_code == 503
    assert response.json()["code"] == "turnstile_unavailable"
    assert any(r.levelname == "ERROR" and "secret rejected" in r.getMessage()
               for r in caplog.records)
    assert "wrong-secret-in-env" not in caplog.text  # the secret itself is never logged


async def test_a_400_with_an_ordinary_refusal_is_a_failed_check(world):

    def bad_token(request):
        world.cloudflare.calls.append({})
        return httpx.Response(400, json={"success": False,
                                         "error-codes": ["invalid-input-response"]})

    transport = httpx.MockTransport(bad_token)
    world.app.dependency_overrides[get_turnstile] = lambda: Turnstile(
        httpx.AsyncClient(transport=transport))
    async with world.client() as client:
        response = await start(client)
    assert response.status_code == 403
    assert response.json()["code"] == "turnstile_failed"


@pytest.mark.parametrize("body", [{}, {"turnstile_token": ""}, {"turnstile_token": "x" * 2049},
                                  {"turnstile_token": TOKEN, "extra": 1}])
async def test_a_bad_start_body_is_refused_before_turnstile(world, body):
    async with world.client() as client:
        response = await client.post("/session/start", json=body)
    assert response.status_code == 422
    assert world.cloudflare.calls == []


@pytest.mark.parametrize("origin", [None, "https://evil.example", "http://localhost:3001"])
async def test_session_start_needs_the_app_origin(world, origin):
    async with world.client() as client:
        headers = {"origin": origin} if origin else {}
        if origin is None:
            del client.headers["origin"]
        response = await client.post("/session/start", json={"turnstile_token": TOKEN},
                                     headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "bad_origin"
    assert world.cloudflare.calls == []


async def test_an_11th_guest_session_from_one_ip_key_in_an_hour_is_refused(world):
    for _ in range(limits.NEW_GUEST_SESSIONS_PER_IP_HOUR):
        async with world.client() as client:
            assert (await start(client)).status_code == 200
    async with world.client() as client:
        response = await start(client)
    assert response.status_code == 429
    assert response.json()["code"] == "too_many_sessions"
    assert 0 < int(response.headers["retry-after"]) <= 3600
    async with world.client(ip="198.51.100.9") as other:  # another IP key is unaffected
        assert (await start(other)).status_code == 200


async def test_ipv6_addresses_in_one_slash_64_share_an_ip_key(world):
    for i in range(limits.NEW_GUEST_SESSIONS_PER_IP_HOUR):
        async with world.client(ip=f"2001:db8:1:2::{i + 1:x}") as client:
            assert (await start(client)).status_code == 200
    async with world.client(ip="2001:db8:1:2:ffff:ffff:ffff:fffe") as client:
        assert (await start(client)).status_code == 429
    async with world.client(ip="2001:db8:1:3::1") as client:  # the next /64
        assert (await start(client)).status_code == 200


async def set_ip_requests(world, ip: str, count: int) -> None:
    key = ip_requests_key(ip_key(ip, world.cfg["settings"]))
    for _ in range(count):
        await world.store.hit_rate(key, limits.GUEST_IP_WINDOW, 10**6)


async def test_the_ip_key_escalation_verifies_with_the_interactive_secret(world):
    ip = "203.0.113.7"
    await set_ip_requests(world, ip, limits.GUEST_IP_REQUESTS - 1)
    async with world.client(ip) as client:
        assert (await start(client)).status_code == 200
    assert world.cloudflare.calls[-1]["secret"] == PASS
    await set_ip_requests(world, ip, 1)  # now at 60 requests
    async with world.client(ip) as client:
        assert (await start(client)).status_code == 200
    assert world.cloudflare.calls[-1]["secret"] == INTERACTIVE


async def test_an_escalated_ip_key_needs_the_interactive_check_to_pass(world):
    world.cfg["settings"] = settings(turnstile_interactive_secret=FAIL)
    await set_ip_requests(world, "203.0.113.7", limits.GUEST_IP_REQUESTS)
    async with world.client() as client:
        response = await start(client)
    assert response.status_code == 403
    assert response.json()["code"] == "turnstile_interactive"


async def test_an_ip_key_at_3x_is_refused_without_a_turnstile_call(world):
    await set_ip_requests(world, "203.0.113.7",
                          limits.GUEST_IP_REQUESTS * limits.GUEST_IP_HARD_STOP_FACTOR)
    async with world.client() as client:
        response = await start(client)
    assert response.status_code == 429
    assert response.json()["code"] == "ip_limit"
    assert world.cloudflare.calls == []


async def test_a_guest_session_ends_after_240_minutes_even_with_activity(world):
    async with world.client() as client:
        started = await start(client)
        for _ in range(3):
            assert (await client.get("/session/csrf")).status_code == 200
        expires = (await sql(world, "SELECT expires_at FROM sessions"))[0][0]
        assert started.json()["expires_at"].endswith("+00:00")  # API times are UTC
        # Activity didn't extend it
        assert expires == datetime.fromisoformat(started.json()["expires_at"])
        # Fake clock: move the session 240 minutes into the past
        await sql(world, "UPDATE sessions SET created_at = created_at - :t, "
                  "expires_at = expires_at - :t", t=limits.GUEST_SESSION_TTL)
        response = await client.get("/session/csrf")
    assert response.status_code == 401
    assert response.json()["code"] == "no_session"


async def test_a_new_guest_session_replaces_the_old_one(world):
    async with world.client() as client:
        await start(client)
        old = client.cookies["holos_session"]
        await start(client)
        assert client.cookies["holos_session"] != old
    assert len(await sql(world, "SELECT 1 FROM sessions")) == 1


async def test_csrf_endpoint_returns_the_same_token(world):
    async with world.client() as client:
        started = await start(client)
        again = await client.get("/session/csrf")
    assert again.json()["csrf_token"] == started.json()["csrf_token"]
    async with world.client() as stranger:
        assert (await stranger.get("/session/csrf")).status_code == 401


@pytest.mark.parametrize("cookie", ["", "x", "a" * 500, "' OR 1=1 --"])
async def test_a_garbage_cookie_is_no_session(world, cookie):
    async with world.client() as client:
        client.cookies.set("holos_session", cookie)
        assert (await client.get("/session/csrf")).status_code == 401


# --- Login, logout ---


async def test_login_rotates_the_session_and_the_old_guest_cookie_stops_working(world):
    user_id = await make_user(world)
    async with world.client() as client:
        await start(client)
        guest_cookie = client.cookies["holos_session"]
        response = await login(client)
        assert response.status_code == 200
        assert response.json()["mode"] == "account"
        assert response.json()["user"] == {"id": user_id, "email": "ved@example.com"}
        assert client.cookies["holos_session"] != guest_cookie
    async with world.client() as old:
        old.cookies.set("holos_session", guest_cookie)
        assert (await old.get("/session/csrf")).status_code == 401
    rows = await sql(world, "SELECT mode, user_id FROM sessions")
    assert rows == [("account", user_id)]


@pytest.mark.parametrize(("email", "password"), [
    ("ved@example.com", "wrong-password"),
    ("nobody@example.com", PASSWORD),
])
async def test_wrong_email_or_password_is_one_generic_401(world, email, password):
    await make_user(world)
    async with world.client() as client:
        response = await login(client, email, password)
    assert response.status_code == 401
    assert response.json() == {"code": "bad_credentials",
                               "message": "Incorrect email or password."}
    assert "set-cookie" not in response.headers


async def test_login_email_is_case_insensitive(world):
    await make_user(world, email="Ved@Example.com")
    async with world.client() as client:
        assert (await login(client, "  VED@example.COM ")).status_code == 200


async def test_an_inactive_user_cannot_log_in(world):
    await make_user(world, active=False)
    async with world.client() as client:
        assert (await login(client)).status_code == 403


async def test_a_passlib_era_account_can_still_log_in(world):
    legacy = "$2b$12$Ka0azVEAmKEKhYSHFTN86eD0X9icSWRFrHJ1JnpCEoF08MVG5Sbm2"  # "LegacyPass123"
    await make_user(world, password_hash=legacy)
    async with world.client() as client:
        assert (await login(client, password="LegacyPass123")).status_code == 200


async def test_login_needs_the_app_origin(world):
    await make_user(world)
    async with world.client() as client:
        response = await client.post("/auth/login", headers={"origin": "https://evil.example"},
                                     json={"email": "ved@example.com", "password": PASSWORD})
    assert response.status_code == 403


async def test_logout_deletes_the_row_and_clears_the_cookie(world):
    await make_user(world)
    async with world.client() as client:
        signed_in = await login(client)
        response = await client.post("/auth/logout", headers=csrf(signed_in))
        assert response.status_code == 204
        assert 'holos_session=""' in response.headers["set-cookie"]
        assert "max-age=0" in response.headers["set-cookie"].lower()
    assert await sql(world, "SELECT 1 FROM sessions") == []


async def test_a_guest_can_log_out_too(world):
    async with world.client() as client:
        started = await start(client)
        assert (await client.post("/auth/logout", headers=csrf(started))).status_code == 204
    assert await sql(world, "SELECT 1 FROM sessions") == []


async def test_logout_all_deletes_every_session_of_the_user(world):
    user_id = await make_user(world)
    other = await make_user(world, email="other@example.com")
    async with world.client() as phone, world.client() as laptop, world.client() as third:
        await login(phone)
        signed_in = await login(laptop)
        await login(third, "other@example.com")
        assert (await laptop.post("/auth/logout-all", headers=csrf(signed_in))).status_code == 204
        assert (await phone.get("/session/csrf")).status_code == 401
        assert (await third.get("/session/csrf")).status_code == 200
    assert await sql(world, "SELECT user_id FROM sessions") == [(other,)]
    assert user_id != other


async def test_a_guest_cannot_log_out_all(world):
    async with world.client() as client:
        started = await start(client)
        response = await client.post("/auth/logout-all", headers=csrf(started))
    assert response.status_code == 401
    assert response.json()["code"] == "account_required"


async def test_registration_is_gone(world):
    async with world.client() as client:
        response = await client.post("/auth/register", json={
            "email": "a@b.co", "username": "a", "password": PASSWORD})
    assert response.status_code == 404


# --- CSRF and Origin on state-changing requests ---


PREFERENCES = {"goals": "Get stronger", "exercise_types": "strength",
               "activity_level": "moderate"}


@pytest.mark.parametrize(("headers", "code"), [
    ({}, "bad_csrf"),
    ({"x-csrf-token": "0" * 64}, "bad_csrf"),
    ({"x-csrf-token": "{token}", "origin": "https://evil.example"}, "bad_origin"),
    ({"x-csrf-token": "{token}", "origin": ""}, "bad_origin"),
])
async def test_state_changing_requests_need_the_csrf_token_and_origin(world, headers, code):
    await make_user(world)
    async with world.client() as client:
        token = (await login(client)).json()["csrf_token"]
        headers = {k: v.format(token=token) for k, v in headers.items()}
        response = await client.post("/preferences", json=PREFERENCES, headers=headers)
        assert response.status_code == 403
        assert response.json()["code"] == code
        assert (await client.post("/auth/logout", headers=headers)).status_code == 403
        # Reads need no token
        assert (await client.get("/preferences")).status_code in (200, 404)


async def test_a_valid_token_and_origin_pass(world):
    await make_user(world)
    async with world.client() as client:
        signed_in = await login(client)
        response = await client.post("/preferences", json=PREFERENCES, headers=csrf(signed_in))
    assert response.status_code in (200, 201), response.text


async def test_another_sessions_csrf_token_does_not_work(world):
    await make_user(world)
    await make_user(world, email="other@example.com")
    async with world.client() as mine, world.client() as theirs:
        await login(mine)
        their_token = (await login(theirs, "other@example.com")).json()["csrf_token"]
        response = await mine.post("/preferences", json=PREFERENCES,
                                   headers={"x-csrf-token": their_token})
    assert response.status_code == 403


async def test_a_guest_session_cannot_use_account_pages(world):
    async with world.client() as client:
        started = await start(client)
        response = await client.post("/preferences", json=PREFERENCES, headers=csrf(started))
        assert response.status_code == 401
        assert response.json()["code"] == "account_required"
        assert (await client.get("/preferences")).status_code == 401


# --- Invites (C.18) ---


async def invite(world, expires_in=limits.INVITE_TTL) -> str:
    token, _ = await create_invite("test", world.db_sessions)
    if expires_in != limits.INVITE_TTL:
        await sql(world, "UPDATE invites SET expires_at = now() + :t", t=expires_in)
    return token


async def accept(client, token, email="new@example.com", password=PASSWORD, consent=True):
    return await client.post("/invites/accept", json={
        "token": token, "email": email, "password": password, "consent": consent})


async def test_an_invite_creates_the_account_once(world):
    token = await invite(world)
    async with world.client() as client:
        await start(client)
        guest_cookie = client.cookies["holos_session"]
        response = await accept(client, token, email="New.Person@Example.com")
        assert response.status_code == 200, response.text
        assert response.json()["mode"] == "account"
        assert client.cookies["holos_session"] != guest_cookie
        assert (await client.get("/session/csrf")).json()["mode"] == "account"
    rows = await sql(world, "SELECT email, username, consent_at IS NOT NULL, consent_version "
                     "FROM users")
    assert rows == [("new.person@example.com", "new.person@example.com", True,
                     auth.CONSENT_VERSION)]
    used = await sql(world, "SELECT used_at IS NOT NULL, used_by FROM invites")
    assert used[0][0] is True and used[0][1] == response.json()["user"]["id"]
    async with world.client() as again:
        second = await accept(again, token, email="second@example.com")
    assert second.status_code == 410
    assert second.json()["code"] == "invite_used"


async def test_an_expired_invite_is_410(world):
    token = await invite(world, expires_in=timedelta(seconds=-1))
    async with world.client() as client:
        response = await accept(client, token)
    assert response.status_code == 410
    assert response.json()["code"] == "invite_expired"
    assert await sql(world, "SELECT 1 FROM users") == []


async def test_an_unknown_invite_is_404(world):
    async with world.client() as client:
        assert (await accept(client, "n" * 43)).status_code == 404


@pytest.mark.parametrize(("change", "status", "code"), [
    ({"consent": False}, 400, "consent_required"),
    ({"password": "short"}, 400, "weak_password"),
    ({"password": "a" * 73}, 400, "weak_password"),
])
async def test_an_invite_needs_consent_and_a_good_password(world, change, status, code):
    token = await invite(world)
    async with world.client() as client:
        response = await accept(client, token, **change)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert (await sql(world, "SELECT used_at FROM invites"))[0][0] is None  # still usable


async def test_an_invite_for_a_taken_email_stays_unused(world):
    await make_user(world, email="taken@example.com")
    token = await invite(world)
    async with world.client() as client:
        response = await accept(client, token, email="TAKEN@example.com")
    assert response.status_code == 409
    assert (await sql(world, "SELECT used_at FROM invites"))[0][0] is None


async def test_two_accepts_of_one_invite_at_once_make_one_account(world):
    token = await invite(world)
    async with world.client() as a, world.client() as b:
        results = await asyncio.gather(accept(a, token, email="a@example.com"),
                                       accept(b, token, email="b@example.com"))
    assert sorted(r.status_code for r in results) == [200, 410]
    assert len(await sql(world, "SELECT 1 FROM users")) == 1


async def test_two_invites_for_one_email_at_once_make_one_account(world):
    first, second = await invite(world), await invite(world)
    async with world.client() as a, world.client() as b:
        results = await asyncio.gather(accept(a, first, email="same@example.com"),
                                       accept(b, second, email="same@example.com"))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(await sql(world, "SELECT 1 FROM users")) == 1


async def test_create_invite_stores_only_the_hash(world):
    token, expires_at = await create_invite("cli", world.db_sessions)
    rows = await sql(world, "SELECT token_hash, created_by, expires_at FROM invites")
    assert rows[0][0] == hashlib.sha256(token.encode()).hexdigest() != token
    assert rows[0][1] == "cli"
    assert abs(rows[0][2] - (datetime.now(UTC) + limits.INVITE_TTL)) < timedelta(minutes=1)
    assert len(token) >= 43  # 256 bits


# --- Secure cookies in production ---


async def test_https_uses_a_secure_host_prefixed_cookie(world):
    world.cfg["settings"] = settings(api_origin="https://api.example.com")
    async with world.client() as client:
        response = await start(client)
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-holos_session=")
    assert "secure" in cookie.lower() and "domain=" not in cookie.lower()


async def test_error_bodies_never_leak_internals(world):
    world.cloudflare.mode = "down"
    async with world.client() as client:
        body = (await start(client)).json()
    assert set(body) == {"code", "message", "retry_after"}
    assert "ConnectError" not in json.dumps(body)


async def test_new_session_counter_key_is_per_ip_key(world):
    async with world.client() as client:
        await start(client)
    key = ip_new_sessions_key(ip_key("203.0.113.7", world.cfg["settings"]))
    assert await world.store.peek_rate(key, timedelta(hours=1)) == 1


# --- Found by planting bugs (P4.2) ---


async def test_a_user_deactivated_mid_session_is_refused(world):
    user_id = await make_user(world)
    async with world.client() as client:
        signed_in = await login(client)
        await sql(world, "UPDATE users SET is_active = false WHERE id = :id", id=user_id)
        response = await client.post("/preferences", json=PREFERENCES, headers=csrf(signed_in))
        assert response.status_code == 403
        assert (await client.get("/preferences")).status_code == 403


async def test_an_unknown_email_takes_as_long_as_a_wrong_password(world):
    import time

    await make_user(world)
    async with world.client() as client:
        timings = {}
        for label, email in (("known", "ved@example.com"), ("unknown", "nobody@example.com")):
            start_at = time.perf_counter()
            assert (await login(client, email, "wrong-password")).status_code == 401
            timings[label] = time.perf_counter() - start_at
    assert timings["unknown"] > timings["known"] * 0.5, timings


async def test_password_hashing_does_not_block_the_event_loop(world):
    import time

    await make_user(world)
    ticks, stop = [], asyncio.Event()

    async def ticker():
        while not stop.is_set():
            ticks.append(time.perf_counter())
            await asyncio.sleep(0.01)

    task = asyncio.create_task(ticker())
    async with world.client() as client:
        assert (await login(client)).status_code == 200
    stop.set()
    await task
    gaps = [b - a for a, b in zip(ticks, ticks[1:], strict=False)]
    assert max(gaps) < 0.1, max(gaps)  # one bcrypt check is ~0.25 s; the loop kept running


async def test_an_old_mixed_case_account_blocks_the_same_email(world):
    # The unique index is case-sensitive; accounts made before invites keep their case
    await sql(world, "INSERT INTO users (email, username, password_hash) "
              "VALUES ('Old@Example.com', 'old', 'h')")
    token = await invite(world)
    async with world.client() as client:
        response = await accept(client, token, email="old@example.com")
    assert response.status_code == 409
    assert len(await sql(world, "SELECT 1 FROM users")) == 1


async def test_accept_waits_for_a_competing_acceptor_and_then_sees_the_invite_used(world):
    """Deterministic version of the race: another acceptor holds the invite row (as
    its transaction would), marks it used and commits. Without SELECT ... FOR UPDATE
    the accept would read the invite as unused and create a second account."""
    token = await invite(world)
    async with world.engine.connect() as rival:
        tx = await rival.begin()
        await rival.execute(text("SELECT id FROM invites FOR UPDATE"))
        async with world.client() as client:
            pending = asyncio.create_task(accept(client, token))
            await asyncio.sleep(1.0)  # the accept has hashed its password and now waits
            assert not pending.done()
            await rival.execute(text("UPDATE invites SET used_at = now()"))
            await tx.commit()
            response = await pending
    assert response.status_code == 410
    assert await sql(world, "SELECT 1 FROM users") == []
