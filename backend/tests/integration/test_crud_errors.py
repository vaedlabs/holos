"""The CRUD routes answer with the one error body, `{code, message}` (Part E #57): what
the person is missing, never the server's own error text."""

import pytest

from app.data.state_store import StateStore

from .accounts import call
from .test_admission import account
from .test_database_down import _crud_app

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(("method", "path"), [
    ("GET", "/medical/history"),
    ("GET", "/preferences"),
    ("DELETE", "/logs/workouts/999"),
    ("DELETE", "/logs/mental-fitness/999"),
])
async def test_what_isnt_there_is_a_404_with_the_one_body(async_engine, clean, method, path):
    store = StateStore(async_engine)
    me = await account(store, async_engine)
    response = await call(_crud_app(store, async_engine, clean), me, method, path)
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"code", "message"} and body["code"] == "not_found"


async def test_a_bad_query_is_a_422_with_the_field(async_engine, clean):
    store = StateStore(async_engine)
    me = await account(store, async_engine)
    response = await call(_crud_app(store, async_engine, clean), me, "GET",
                          "/logs/workouts?limit=0")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "bad_request" and body["details"][0]["loc"] == ["query", "limit"]


async def test_a_save_and_a_read_still_work(async_engine, clean):
    store = StateStore(async_engine)
    me = await account(store, async_engine)
    app = _crud_app(store, async_engine, clean)
    saved = await call(app, me, "POST", "/medical/history", json={"conditions": "asthma"})
    assert saved.status_code == 201 and saved.json()["conditions"] == "asthma"
    read = await call(app, me, "GET", "/medical/history")
    assert read.json()["conditions"] == "asthma"
    assert (await call(app, me, "GET", "/logs/workouts")).json() == {"logs": [], "total": 0}
