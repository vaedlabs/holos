"""The CRUD routes run in FastAPI's threadpool (Plan C.1, Part E #57): an `async def`
route with a sync session blocks the event loop that streams every chat answer."""

import inspect

import pytest
from fastapi.routing import APIRoute

from app import main
from app.data.engine import (
    SYNC_POOL,
    get_sync_engine,
    get_sync_sessionmaker,
)
from app.dependencies import get_database
from app.routers.crud import conversation, logs, medical, preferences

pytestmark = pytest.mark.unit

CRUD = (conversation, logs, medical, preferences)
# Async on purpose: they wait on the image store and use the async pool, never get_database
ASYNC = {("GET", "/conversation/images/{name}"), ("DELETE", "/conversation/messages")}


def _routes():
    return [(method, route) for module in CRUD for route in module.router.routes
            if isinstance(route, APIRoute) for method in route.methods]


def _uses_sync_database(route: APIRoute) -> bool:
    return any(d.call is get_database for d in route.dependant.dependencies)


def test_the_crud_routes_are_all_served():
    served = {(m, r.path) for r in main.app.routes if isinstance(r, APIRoute)
              for m in r.methods}
    assert len(_routes()) == 13  # conversation 3, logs 6, medical 2, preferences 2
    assert {(m, r.path) for m, r in _routes()} <= served


@pytest.mark.parametrize(("method", "route"), _routes(),
                         ids=[f"{m} {r.path}" for m, r in _routes()])
def test_a_crud_route_never_runs_sync_database_work_on_the_event_loop(method, route):
    if (method, route.path) in ASYNC:
        assert inspect.iscoroutinefunction(route.endpoint)
        assert not _uses_sync_database(route)
    else:
        assert not inspect.iscoroutinefunction(route.endpoint)
        assert _uses_sync_database(route)


def test_the_crud_sessions_come_from_their_own_pool(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/x")
    get_sync_engine.cache_clear()
    get_sync_sessionmaker.cache_clear()
    try:
        sessions = get_database()
        session = next(sessions)  # makes no connection
        engine = session.get_bind()
        assert engine is get_sync_engine()
        assert engine.pool.size() == SYNC_POOL["pool_size"]
        assert engine.pool._max_overflow == SYNC_POOL["max_overflow"]
        assert engine.pool._timeout == SYNC_POOL["pool_timeout"]
        sessions.close()
    finally:
        get_sync_engine.cache_clear()
        get_sync_sessionmaker.cache_clear()
