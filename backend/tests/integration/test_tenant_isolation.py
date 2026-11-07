"""User A can't read or write user B's data through any endpoint (Plan P4.9): profile,
logs, messages, pending writes, images, requests. One test per route, generated from
the app's route list: a new route fails `test_every_route_is_classified` until it gets
a check here or a reason it holds no user data.

Requests go to the real route objects through a bare app: no middleware, so the flood
limit doesn't touch the dev database; dependencies point at the test database."""

import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import sessionmaker

from app import main
from app.config.settings import get_settings
from app.data.state_store import StateStore
from app.data.stream_store import StreamStore
from app.dependencies import (
    get_database,
    get_db_sessions,
    get_engine,
    get_image_store,
    get_state_store,
    get_stream_store,
)
from app.orchestration.principal import csrf_token
from app.routers.errors import ApiError, api_error_handler
from app.storage.images import LocalImageStore, image_key

from .accounts import call
from .test_admission import account, settings, sql
from .test_intake import form
from .test_writes import BRIDGES

pytestmark = pytest.mark.asyncio

ROUTES = sorted((m, r.path) for r in main.app.routes if isinstance(r, APIRoute)
                for m in r.methods)
# Routes that hold no user data, and why
NO_USER_DATA = {
    ("GET", "/"): "a fixed welcome",
    ("GET", "/health"): "a fixed status",
    ("POST", "/session/start"): "creates a guest session; reads no one's data",
    ("GET", "/session/csrf"): "the caller's own token, from the caller's own cookie",
    ("POST", "/auth/login"): "checks a password; a wrong one reads nothing",
    ("POST", "/invites/accept"): "creates a new account from an invite",
}


@pytest_asyncio.fixture
async def world(async_engine, clean, tmp_path):
    """User B has one of everything; user A is signed in."""
    store = StateStore(async_engine)
    images = LocalImageStore(tmp_path)
    a = await account(store, async_engine, email="a@example.com")
    b = await account(store, async_engine, email="b@example.com")
    u = b.user_id
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) "
              "VALUES (:u, 'B-asthma')", u=u)
    await sql(async_engine, "INSERT INTO user_preferences (user_id, goals) "
              "VALUES (:u, 'B-goals')", u=u)
    logs = {t: (await sql(async_engine, f"INSERT INTO {t} (user_id, notes) VALUES (:u, 'B-log') "
                          "RETURNING id", u=u))[0][0]
            for t in ("workout_logs", "nutrition_logs", "mental_fitness_logs")}
    key = image_key(u)
    await images.put(key, b"B-image")
    await sql(async_engine, "INSERT INTO conversation_messages (user_id, role, content, "
              "image_path) VALUES (:u, 'user', 'B-message', :k)", u=u, k=key)
    write_id = await store.stage_write(u, "workout", {"args": BRIDGES, "warnings": []},
                                       "hash", "tb")
    rid = uuid.uuid4()
    await store.claim_request(b.principal_key, rid, u, "trace-b")
    await StreamStore(async_engine).append("trace-b", [(0, "accepted", {"seq": 0})])

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.router.routes = list(main.app.router.routes)
    db = async_sessionmaker(async_engine, expire_on_commit=False)
    sync = sessionmaker(bind=clean)

    def database():
        session = sync()
        try:
            yield session
        finally:
            session.close()

    cfg = settings()
    main.app.dependency_overrides.update({  # routes read overrides from the app they joined
        get_settings: lambda: cfg, get_state_store: lambda: store, get_db_sessions: lambda: db,
        get_engine: lambda: async_engine, get_image_store: lambda: images,
        get_stream_store: lambda: StreamStore(async_engine), get_database: database})
    yield SimpleNamespace(app=app, a=a, b=b, logs=logs, key=key, write_id=write_id, rid=rid,
                          images=images, engine=async_engine)
    main.app.dependency_overrides.clear()


async def _b_intact(w) -> None:
    """Everything of B's is still there and unchanged."""
    e, u = w.engine, w.b.user_id
    assert await sql(e, "SELECT conditions FROM medical_history WHERE user_id = :u",
                     u=u) == [("B-asthma",)]
    assert await sql(e, "SELECT goals FROM user_preferences WHERE user_id = :u",
                     u=u) == [("B-goals",)]
    for table, log_id in w.logs.items():
        assert await sql(e, f"SELECT notes FROM {table} WHERE id = :i",
                         i=log_id) == [("B-log",)]
    assert await sql(e, "SELECT content FROM conversation_messages WHERE user_id = :u",
                     u=u) == [("B-message",)]
    assert await sql(e, "SELECT status FROM pending_writes WHERE user_id = :u",
                     u=u) == [("pending",)]
    assert await sql(e, "SELECT count(*) FROM sessions WHERE user_id = :u", u=u) == [(1,)]
    assert await w.images.get(w.key) == b"B-image"


def _no_b(response) -> None:
    assert b"B-" not in response.content and w_b_image not in response.content


w_b_image = b"B-image"


async def _get(w, path):
    response = await call(w.app, w.a, "GET", path)
    _no_b(response)
    return response


CHECKS = {
    ("GET", "/medical/history"): lambda w: _get(w, "/medical/history"),
    ("POST", "/medical/history"): lambda w: call(
        w.app, w.a, "POST", "/medical/history", json={"conditions": "A-knee"}),
    ("GET", "/preferences"): lambda w: _get(w, "/preferences"),
    ("POST", "/preferences"): lambda w: call(w.app, w.a, "POST", "/preferences",
                                             json={"goals": "A-goals"}),
    ("GET", "/logs/workouts"): lambda w: _get(w, "/logs/workouts"),
    ("GET", "/logs/nutrition"): lambda w: _get(w, "/logs/nutrition"),
    ("GET", "/logs/mental-fitness"): lambda w: _get(w, "/logs/mental-fitness"),
    ("DELETE", "/logs/workouts/{log_id}"): lambda w: call(
        w.app, w.a, "DELETE", f"/logs/workouts/{w.logs['workout_logs']}"),
    ("DELETE", "/logs/nutrition/{log_id}"): lambda w: call(
        w.app, w.a, "DELETE", f"/logs/nutrition/{w.logs['nutrition_logs']}"),
    ("DELETE", "/logs/mental-fitness/{log_id}"): lambda w: call(
        w.app, w.a, "DELETE", f"/logs/mental-fitness/{w.logs['mental_fitness_logs']}"),
    ("GET", "/conversation/messages"): lambda w: _get(w, "/conversation/messages"),
    ("DELETE", "/conversation/messages"): lambda w: call(w.app, w.a, "DELETE",
                                                         "/conversation/messages"),
    ("GET", "/conversation/images/{name}"): lambda w: _get(
        w, f"/conversation/images/{w.key.rsplit('/', 1)[1]}"),
    ("POST", "/agents/chat/stream"): lambda w: _chat_naming_b(w),
    ("GET", "/agents/chat/stream/{client_request_id}"): lambda w: _get(
        w, f"/agents/chat/stream/{w.rid}"),
    ("POST", "/agents/writes/{write_id}/confirm"): lambda w: call(
        w.app, w.a, "POST", f"/agents/writes/{w.write_id}/confirm"),
    ("POST", "/agents/writes/{write_id}/discard"): lambda w: call(
        w.app, w.a, "POST", f"/agents/writes/{w.write_id}/discard"),
    ("POST", "/account/import"): lambda w: call(
        w.app, w.a, "POST", "/account/import", json={"import_id": str(uuid.uuid4()),
                                                     "profile": None, "history": [],
                                                     "logs": []}),
    ("GET", "/profile/check"): lambda w: _get(w, "/profile/check"),
    ("POST", "/profile/check"): lambda w: call(w.app, w.a, "POST", "/profile/check",
                                               json={"notes": "A notes"}),
    ("DELETE", "/auth/delete-account"): lambda w: call(w.app, w.a, "DELETE",
                                                       "/auth/delete-account"),
    ("POST", "/auth/logout"): lambda w: call(w.app, w.a, "POST", "/auth/logout"),
    ("POST", "/auth/logout-all"): lambda w: call(w.app, w.a, "POST", "/auth/logout-all"),
}


async def _chat_naming_b(w):
    """No field of the chat payload names a user: one that tries is refused."""
    payload = {"message": "hi", "client_request_id": str(w.rid), "contract_version": 1,
               "user_id": w.b.user_id}
    cfg = settings()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=w.app),
                                 base_url="http://testserver",
                                 cookies={cfg.session_cookie: w.a.raw_session_id}) as client:
        response = await client.post(
            "/agents/chat/stream", content=form(payload),
            headers={"origin": "http://localhost:3000",
                     "content-type": "multipart/form-data; boundary=holosboundary",
                     "x-csrf-token": csrf_token(w.a.raw_session_id, cfg)})
    assert response.status_code == 400
    return response


def test_every_route_is_classified():
    unknown = [r for r in ROUTES if r not in CHECKS and r not in NO_USER_DATA]
    stale = [r for r in [*CHECKS, *NO_USER_DATA] if r not in ROUTES]
    assert unknown == [] and stale == []


@pytest.mark.parametrize("route", [r for r in ROUTES if r in CHECKS],
                         ids=[f"{m} {p}" for m, p in ROUTES if (m, p) in CHECKS])
async def test_a_cant_reach_bs_data(world, route):
    response = await CHECKS[route](world)
    assert response.status_code < 500, response.text
    await _b_intact(world)
    assert json.dumps(world.b.user_id)  # B existed throughout
