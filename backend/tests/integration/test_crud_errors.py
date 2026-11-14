"""The CRUD routes answer with the one error body, `{code, message}` (Part E #57): what
the person is missing, never the server's own error text."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.data.state_store import StateStore
from app.storage.context import load_context

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


async def test_an_edit_keeps_what_it_leaves_out_and_the_next_turn_sees_it(async_engine,
                                                                          clean):
    """The profile forms post again to edit; the gate checks the next turn against the
    edited profile, not the first one."""
    store = StateStore(async_engine)
    me = await account(store, async_engine)
    app = _crud_app(store, async_engine, clean)
    await call(app, me, "POST", "/medical/history",
               json={"conditions": "asthma", "medications": "inhaler"})
    await call(app, me, "POST", "/preferences",
               json={"goals": "run 5k", "dietary_restrictions": "vegetarian"})
    sessions = async_sessionmaker(async_engine)
    before = (await load_context(me, None, sessions)).profile
    assert (before.condition_ids, before.diet_tags) == (["asthma"], ["vegetarian"])

    medical = await call(app, me, "POST", "/medical/history",
                         json={"conditions": "torn ACL left knee"})
    preferences = await call(app, me, "POST", "/preferences",
                             json={"dietary_restrictions": "peanut allergy"})
    assert (medical.json()["conditions"], medical.json()["medications"]) == (
        "torn ACL left knee", "inhaler")
    assert (preferences.json()["goals"], preferences.json()["dietary_restrictions"]) == (
        "run 5k", "peanut allergy")
    after = (await load_context(me, None, sessions)).profile
    assert (after.condition_ids, after.allergen_tags, after.diet_tags) == (
        ["knee_ligament_injury"], ["peanut"], [])
