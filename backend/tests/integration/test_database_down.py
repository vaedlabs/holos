"""The database down, or its connection pool full (failure library, Part E #55): the
person gets 503 `server_busy` with Retry-After, readable by the browser (CORS and the
security headers), never a bare 500."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import get_settings
from app.data.engine import make_async_engine, psycopg_url
from app.data.state_store import StateStore
from app.dependencies import get_state_store
from app.middleware.error_handler import register_error_handlers
from app.middleware.headers import SecurityHeaders
from app.routers import account
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
