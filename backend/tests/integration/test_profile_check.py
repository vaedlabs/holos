"""GET and POST /profile/check (Part E #42): the profile screen sees what a chat turn
sees; only the caller's own profile; a guest's notes are checked and not stored."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.data.state_store import StateStore
from app.storage.context import load_context
from app.storage.images import LocalImageStore

from .accounts import account_app, call
from .test_admission import account, guest, sql

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


@pytest_asyncio.fixture
async def app(store, async_engine, tmp_path):
    return account_app(store, async_engine, LocalImageStore(tmp_path))


async def test_the_screen_and_a_chat_turn_agree(app, store, async_engine):
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions, medications, "
              "notes) VALUES (:u, 'torn ACL left knee, bad hip thing', 'metformin', "
              "'coeliac')", u=me.user_id)
    await sql(async_engine, "INSERT INTO user_preferences (user_id, dietary_restrictions) "
              "VALUES (:u, 'no dairy, pure veg')", u=me.user_id)
    screen = (await call(app, me, "GET", "/profile/check")).json()
    turn = await load_context(me, None, async_sessionmaker(async_engine))
    assert [c["id"] for c in screen["conditions"]] == turn.profile.condition_ids
    assert screen["allergens"] == [str(a) for a in turn.profile.allergen_tags]
    assert screen["diets"] == [str(d) for d in turn.profile.diet_tags]
    assert screen["unchecked"] == list(turn.unchecked)
    assert screen["conditions"] == [{"id": "knee_ligament_injury",
                                     "name": "Knee ligament injury"}]
    assert set(screen["allergens"]) == {"gluten", "milk"}  # "coeliac" in the notes counts
    assert screen["unchecked"] == ["bad hip thing", "medications: metformin"]


async def test_each_account_sees_only_its_own(app, store, async_engine):
    me = await account(store, async_engine)
    other = await account(store, async_engine, email="other@example.com")
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) "
              "VALUES (:u, 'asthma')", u=other.user_id)
    assert (await call(app, me, "GET", "/profile/check")).json()["conditions"] == []


async def test_a_guests_notes_are_checked_and_not_stored(app, store, async_engine):
    me = await guest(store)
    response = await call(app, me, "POST", "/profile/check",
                          json={"notes": "coeliac, very little free time"})
    assert response.json() == {"conditions": [], "allergens": ["gluten"], "diets": [],
                               "unchecked": []}
    assert (await call(app, me, "GET", "/profile/check")).status_code == 401
    assert await sql(async_engine, "SELECT count(*) FROM medical_history") == [(0,)]


async def test_the_check_needs_a_session_and_csrf(app, store, async_engine):
    assert (await call(app, None, "POST", "/profile/check",
                       json={"notes": "x"})).status_code == 401
