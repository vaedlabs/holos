"""Every state-changing route checks the session and CSRF, or the Origin (Plan C.6)."""

from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.dependencies import get_principal
from app.main import app

pytestmark = pytest.mark.unit

# These create a session, so there's no CSRF token yet; they check the Origin instead
ORIGIN_CHECKED = {"/session/start", "/auth/login", "/invites/accept"}
ROUTERS = Path(__file__).parents[2] / "app" / "routers"


def _calls(dependant, found: set) -> set:
    for sub in dependant.dependencies:
        found.add(sub.call)
        _calls(sub, found)
    return found


def _state_changing():
    return [r for r in app.routes
            if isinstance(r, APIRoute) and r.methods - {"GET", "HEAD", "OPTIONS"}]


def test_every_state_changing_route_resolves_the_session():
    unchecked = [r.path for r in _state_changing() if r.path not in ORIGIN_CHECKED
                 and get_principal not in _calls(r.dependant, set())]
    assert unchecked == []


def test_the_session_creating_routes_exist_and_check_the_origin():
    paths = {r.path for r in _state_changing()}
    assert ORIGIN_CHECKED <= paths
    source = (ROUTERS / "auth.py").read_text() + (ROUTERS / "session.py").read_text()
    assert source.count("check_origin(request, settings)") == len(ORIGIN_CHECKED)


def test_cors_allows_only_the_app_origin_with_the_csrf_header():
    from fastapi.middleware.cors import CORSMiddleware

    from app.config.settings import get_settings

    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert cors.kwargs["allow_origins"] == [get_settings().app_origin]
    assert cors.kwargs["allow_credentials"] is True
    assert {"X-CSRF-Token", "X-Contract-Version"} <= set(cors.kwargs["allow_headers"])
    assert "Authorization" not in cors.kwargs["allow_headers"]


def test_no_route_takes_a_bearer_token():
    from fastapi.security import HTTPBearer

    bearer = [r.path for r in app.routes if isinstance(r, APIRoute)
              and any(isinstance(c, HTTPBearer) for c in _calls(r.dependant, set()))]
    assert bearer == []


def test_middleware_order_headers_then_cors_then_the_flood_limit():
    """Outermost first: every response gets the headers, and CORS wraps the flood limit
    so preflights never count and a flood 429 is readable by the app (C.2 stage 1)."""
    from fastapi.middleware.cors import CORSMiddleware

    from app.middleware.flood import FloodLimit
    from app.middleware.headers import SecurityHeaders

    # user_middleware lists the outermost first
    assert [m.cls for m in app.user_middleware] == [SecurityHeaders, CORSMiddleware,
                                                   FloodLimit]
