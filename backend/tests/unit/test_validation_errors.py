"""Validation errors stay readable 422s; an empty gender means "not given" (Part E #16)."""

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
    assert "Gender must be one of" in body["detail"][0]["msg"]  # what the frontend shows
    assert body["details"] == body["detail"]


def test_valid_gender_still_works(client):
    assert client.post("/prefs", json={"gender": "XX"}).json() == {"gender": "XX"}
