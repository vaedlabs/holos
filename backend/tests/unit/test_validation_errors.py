"""Validation errors stay readable 422s; an empty gender means "not given" (Part E #16).
Every error has the `{code, message}` body and no exception text (Part E #57)."""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.middleware.error_handler import register_error_handlers
from app.schemas.preferences import UserPreferencesCreate

pytestmark = pytest.mark.unit

ORIGIN = "http://localhost:3000"


@pytest.fixture
def client():
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.post("/prefs")
    async def prefs(body: UserPreferencesCreate):
        return {"gender": body.gender}

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("gender", ["", "   ", None])
def test_blank_gender_means_not_given(client, gender):
    resp = client.post("/prefs", json={"gender": gender})
    assert resp.status_code == 200 and resp.json() == {"gender": None}


def test_custom_validator_error_is_a_readable_422_with_cors(client):
    # Used to be a 500 without CORS headers ("Cannot connect to backend server")
    resp = client.post("/prefs", json={"gender": "zzz"}, headers={"Origin": ORIGIN})
    assert resp.status_code == 422
    assert resp.headers.get("access-control-allow-origin") == ORIGIN
    body = resp.json()
    assert body["code"] == "bad_request" and body["message"]  # one error body (Part E #57)
    assert "Gender must be one of" in body["details"][0]["msg"]  # the field the form shows
    assert set(body) == {"code", "message", "details"}


def test_valid_gender_still_works(client):
    assert client.post("/prefs", json={"gender": "XX"}).json() == {"gender": "XX"}


def test_an_unhandled_error_is_a_500_with_nosniff_and_cors_for_the_app(monkeypatch):
    """Starlette runs the 500 handler outside every middleware, CORS included."""
    from types import SimpleNamespace

    from app.config import settings as settings_module

    monkeypatch.setattr(settings_module, "get_settings",
                        lambda: SimpleNamespace(app_origin=ORIGIN))
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_credentials=True)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom", headers={"Origin": ORIGIN})
    assert resp.status_code == 500
    assert resp.json() == {"code": "server_error",
                           "message": "Something went wrong. Please try again."}
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    other = client.get("/boom", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
    assert other.headers["x-content-type-options"] == "nosniff"


def test_starlettes_own_404_and_405_have_the_one_body(client):
    missing = client.get("/no-such-route")
    assert missing.status_code == 404
    assert missing.json() == {"code": "not_found", "message": "Not Found"}
    wrong = client.get("/prefs")
    assert wrong.status_code == 405
    assert wrong.json()["code"] == "method_not_allowed"
    assert "allow" in wrong.headers  # the handler keeps the exception's headers


def test_an_http_exception_keeps_its_status_and_message():
    from fastapi import HTTPException

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/gone")
    async def gone():
        raise HTTPException(410, detail="That link has expired.")

    resp = TestClient(app).get("/gone")
    assert resp.status_code == 410
    assert resp.json() == {"code": "expired", "message": "That link has expired."}
