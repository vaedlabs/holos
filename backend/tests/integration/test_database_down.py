"""The database down, or its connection pool full (failure library, Part E #55): the
person gets 503 `server_busy` with Retry-After, readable by the browser (CORS and the
security headers), never a bare 500."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.data.engine import make_async_engine, make_sync_engine, psycopg_url
from app.data.state_store import StateStore
from app.dependencies import get_database, get_db_sessions, get_state_store
from app.middleware.error_handler import register_error_handlers
from app.middleware.headers import SecurityHeaders
from app.routers import account
from app.routers.crud import conversation, logs, medical, preferences
from app.routers.errors import ApiError, api_error_handler

from .accounts import call
from .conftest import TEST_URL
from .test_admission import APP, settings
from .test_admission import account as make_account

pytestmark = pytest.mark.asyncio


def _app(store) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(account.router)
    app.add_middleware(CORSMiddleware, allow_origins=[APP], allow_credentials=True,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.add_middleware(SecurityHeaders)
    cfg = settings()
    app.dependency_overrides.update({get_settings: lambda: cfg, get_state_store: lambda: store})
    return app


def _busy(response) -> None:
    assert response.status_code == 503
    assert response.json() == {"code": "server_busy", "message":
                               "Holos is busy right now. Please try again in a few seconds."}
    assert response.headers["retry-after"] == "5"
    assert response.headers["access-control-allow-origin"] == APP
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_a_database_that_refuses_connections(async_engine):
    store = StateStore(async_engine)
    me = await make_account(store, async_engine)
    down = make_async_engine("postgresql://holos:x@127.0.0.1:1/holos")  # nothing listens
    try:
        _busy(await call(_app(StateStore(down)), me, "GET", "/profile/check"))
    finally:
        await down.dispose()


async def test_a_full_connection_pool(async_engine):
    store = StateStore(async_engine)
    me = await make_account(store, async_engine)
    tiny = create_async_engine(psycopg_url(TEST_URL), pool_size=1, max_overflow=0,
                               pool_timeout=0.2)
    try:
        async with tiny.connect() as held:  # the only connection, in use
            await held.execute(text("SELECT 1"))
            _busy(await asyncio.wait_for(
                call(_app(StateStore(tiny)), me, "GET", "/profile/check"), 10))
    finally:
        await tiny.dispose()


# The CRUD routes on the sync pool (Part E #57): they used to catch the outage themselves
# and answer 500 or 400 with the driver's error text
CRUD_CALLS = [("GET", "/medical/history", None), ("POST", "/medical/history", {"notes": "x"}),
              ("GET", "/preferences", None), ("POST", "/preferences", {"goals": "x"}),
              ("GET", "/logs/workouts", None), ("DELETE", "/logs/nutrition/1", None),
              ("GET", "/conversation/messages", None)]


def _crud_app(store, async_engine, sync_engine) -> FastAPI:
    """The signed-in user is read on the async pool (working); the route's own work goes
    to `sync_engine`."""
    app = _app(store)
    for module in (medical, preferences, logs, conversation):
        app.include_router(module.router)
    db = async_sessionmaker(async_engine, expire_on_commit=False)
    sync = sessionmaker(sync_engine)

    def database():
        with sync() as session:
            yield session

    app.dependency_overrides.update({get_db_sessions: lambda: db, get_database: database})
    return app


@pytest.mark.parametrize(("method", "path", "body"), CRUD_CALLS)
async def test_a_crud_route_with_the_database_refusing(async_engine, method, path, body):
    store = StateStore(async_engine)
    me = await make_account(store, async_engine)
    down = make_sync_engine("postgresql://holos:x@127.0.0.1:1/holos")
    try:
        _busy(await call(_crud_app(store, async_engine, down), me, method, path, json=body))
    finally:
        down.dispose()


@pytest.mark.parametrize(("method", "path", "body"), CRUD_CALLS[:2])
async def test_a_crud_route_with_its_pool_full(async_engine, method, path, body):
    store = StateStore(async_engine)
    me = await make_account(store, async_engine)
    tiny = create_engine(psycopg_url(TEST_URL), pool_size=1, max_overflow=0, pool_timeout=0.2)
    try:
        with tiny.connect() as held:  # the only connection, in use
            held.execute(text("SELECT 1"))
            _busy(await asyncio.wait_for(
                call(_crud_app(store, async_engine, tiny), me, method, path, json=body), 10))
    finally:
        tiny.dispose()
