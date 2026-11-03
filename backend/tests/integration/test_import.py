"""POST /account/import (Plan C.18): limits; entries that can't be read are skipped and
listed; conflicts are imported with their warnings, new ones listed for review (Part E
#46); one import per import_id; the guest session is gone once the person signs in."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from app.config import limits
from app.data.state_store import StateStore
from app.dependencies import get_db_sessions
from app.orchestration.passwords import get_password_hash
from app.storage.context import load_context
from app.storage.images import LocalImageStore

from .accounts import account_app, call
from .test_admission import PASSWORD, account, guest, sql
from .test_writes import BRIDGES, DAL, POHA, SQUATS

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 11, 2, 8, 30, tzinfo=UTC)
GUEST = {"condition_ids": ["knee_ligament_injury"], "allergen_tags": ["peanut"],
         "diet_tags": ["vegetarian"], "notes": "desk job"}


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


@pytest_asyncio.fixture
async def app(store, async_engine, tmp_path):
    return account_app(store, async_engine, LocalImageStore(tmp_path))


def _log(kind, args, at=NOW, warnings=()):
    return {"entry": {"kind": kind, "args": args, "warnings": list(warnings)},
            "at": at.isoformat()}


def _body(**kw):
    return {"import_id": str(kw.pop("import_id", uuid.uuid4())), "profile": GUEST,
            "history": [{"role": "user", "content": "a leg workout", "ts": NOW.isoformat()},
                        {"role": "assistant", "content": "Here is your plan.",
                         "agents": ["physical"], "ts": (NOW + timedelta(seconds=5)).isoformat()}],
            "logs": [_log("workout", BRIDGES)], **kw}


async def _import(app, me, body):
    return await call(app, me, "POST", "/account/import", json=body)


async def test_a_guests_data_becomes_the_accounts(app, store, async_engine):
    me = await account(store, async_engine)
    response = await _import(app, me, _body())
    assert response.status_code == 200
    assert response.json() == {"imported": {"history": 2, "logs": 1}, "skipped": [],
                               "review": []}
    # The profile as text the account's resolution reads back to the same tags
    context = await load_context(me, None, app.dependency_overrides[get_db_sessions]())
    assert context.profile.condition_ids == ["knee_ligament_injury"]
    assert [str(a) for a in context.profile.allergen_tags] == ["peanut"]
    assert [str(d) for d in context.profile.diet_tags] == ["vegetarian"]
    assert "desk job" in context.profile.notes
    assert [t.role for t in context.history] == ["user", "assistant"]
    assert context.history[1].agents == ["physical"]
    [(when,)] = await sql(async_engine, "SELECT workout_date FROM workout_logs")
    assert when == NOW


async def test_the_account_keeps_what_it_says(app, store, async_engine):
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions, notes) "
              "VALUES (:u, 'torn ACL left knee, asthma', 'night shifts')", u=me.user_id)
    await _import(app, me, _body())
    [(conditions, notes)] = await sql(async_engine,
                                      "SELECT conditions, notes FROM medical_history")
    assert conditions == "torn ACL left knee, asthma"  # the knee was already there
    assert notes == "night shifts; desk job"


async def test_the_same_import_id_imports_once(app, store, async_engine):
    me = await account(store, async_engine)
    body = _body()
    first, again = await asyncio.gather(_import(app, me, body), _import(app, me, body))
    assert first.json() == again.json()
    assert await sql(async_engine, "SELECT count(*) FROM conversation_messages") == [(2,)]
    assert await sql(async_engine, "SELECT count(*) FROM workout_logs") == [(1,)]
    # A different import_id is a new import
    await _import(app, me, _body())
    assert await sql(async_engine, "SELECT count(*) FROM workout_logs") == [(2,)]


async def test_entries_that_cant_be_read_are_skipped_and_listed(app, store, async_engine):
    me = await account(store, async_engine)
    bad = _log("workout", {**BRIDGES, "catalogue_id": "no_such_exercise"})
    future = _log("workout", BRIDGES, at=datetime.now(UTC) + timedelta(days=3))
    response = await _import(app, me, _body(logs=[bad, _log("meal", {"meal": "lunch",
                                                                      "foods": [DAL]}), future]))
    assert response.json()["skipped"] == [
        {"index": 0, "reason": "this entry can't be read"},
        {"index": 2, "reason": "this entry is dated in the future"}]
    assert response.json()["imported"]["logs"] == 1


async def test_conflicts_are_imported_with_warnings_and_new_ones_listed(app, store,
                                                                       async_engine):
    me = await account(store, async_engine)
    confirmed = [{"kind": "conflict", "item": "Poha with peanuts", "rule_id": "DI-ALG-01",
                  "attributes": ["peanut"], "reason": "Contains an allergen in your profile",
                  "left_out": True}]
    logs = [_log("meal", {"meal": "breakfast", "foods": [POHA]}, warnings=confirmed),
            _log("workout", SQUATS)]  # the guest's profile had no knee injury then
    response = await _import(app, me, _body(logs=logs))
    assert response.json()["skipped"] == []
    assert response.json()["review"] == [
        {"index": 1, "warnings": ["Back squat: high knee load with a knee ligament injury"]}]
    [(poha,)] = await sql(async_engine, "SELECT warnings FROM nutrition_logs")
    assert poha[0]["left_out"] is True  # the browser's mark is kept
    [(squats,)] = await sql(async_engine, "SELECT warnings FROM workout_logs")
    assert squats[0]["attributes"] == ["knee_load"] and squats[0]["left_out"] is False


async def test_limits(app, store, async_engine):
    me = await account(store, async_engine)
    turn = {"role": "user", "content": "x", "ts": NOW.isoformat()}
    too_many = await _import(app, me, _body(history=[turn] * (limits.IMPORT_TURNS + 1)))
    assert too_many.status_code == 400
    logs = await _import(app, me, _body(logs=[_log("workout", BRIDGES)]
                                         * (limits.IMPORT_LOG_ENTRIES + 1)))
    assert logs.status_code == 400
    # At every count limit a body is about 655 KB: only padding or oversized fields
    # pass 1 MB, and the size is checked before anything is parsed
    big = json.dumps(_body()) + " " * limits.IMPORT_BYTES
    response = await call(app, me, "POST", "/account/import", content=big,
                          headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert await sql(async_engine, "SELECT count(*) FROM account_imports") == [(0,)]


async def test_a_guest_cant_import_and_the_guest_session_ends_at_sign_in(app, store,
                                                                         async_engine):
    visitor = await guest(store)
    assert (await _import(app, visitor, _body())).status_code == 401
    # Signing in with the guest's cookie ends the guest session (P4.2)
    await sql(async_engine, "INSERT INTO users (email, username, password_hash, is_active) "
              "VALUES ('g@example.com', 'g@example.com', :h, true)",
              h=get_password_hash(PASSWORD))
    response = await call(app, visitor, "POST", "/auth/login",
                          json={"email": "g@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert await sql(async_engine, "SELECT mode FROM sessions") == [("account",)]
    assert (await _import(app, visitor, _body())).status_code == 401  # the old cookie


async def test_another_user_is_untouched(app, store, async_engine):
    me = await account(store, async_engine)
    other = await account(store, async_engine, email="other@example.com")
    await _import(app, me, _body())
    assert await sql(async_engine, "SELECT DISTINCT user_id FROM conversation_messages") == [
        (me.user_id,)]
    assert await sql(async_engine, "SELECT count(*) FROM medical_history WHERE user_id = :u",
                     u=other.user_id) == [(0,)]
