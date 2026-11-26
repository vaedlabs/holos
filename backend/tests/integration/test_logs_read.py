"""GET /logs/* sends a workout's exercises, a meal's foods and its macros as lists and an
object (R9, Part E #74), whatever text the row holds: what reads is sent, the rest left
out, never raw JSON (D062 B1, B3). Each log sends its stored warnings (Part E #65 (4))."""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import WRITE_ARGS, StagedWrite
from app.data.state_store import StateStore
from app.storage.logs import insert_log

from .accounts import call
from .test_admission import account, sql
from .test_database_down import _crud_app

POHA = {"day": None, "name": "Poha", "ingredients": ["flattened rice"], "allergen_tags": [],
        "diet_tags": [], "portion": "1 plate", "calories": 300, "note": "", "protein_g": 8,
        "carbs_g": 50, "fat_g": 9}
SQUATS = {"catalogue_id": "back_squat", "activity": None, "sets": 3, "reps": 8,
          "duration_s": None, "note": "", "when": {"day": None, "time": None, "ampm": None,
                                                    "part": None}}


async def _app(async_engine, clean):
    store = StateStore(async_engine)
    me = await account(store, async_engine)
    return _crud_app(store, async_engine, clean), me


async def _logged(engine, user_id, kind, args, warnings=()):
    write = StagedWrite(kind=kind, args=WRITE_ARGS[kind].model_validate(args),
                        warnings=list(warnings))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await insert_log(session, user_id, write)
        await session.commit()


async def test_an_entry_the_coach_logged_comes_back_as_lists(async_engine, clean):
    app, me = await _app(async_engine, clean)
    await _logged(async_engine, me.user_id, "meal",
                  {"meal": "breakfast", "foods": [POHA], "when": SQUATS["when"]})
    await _logged(async_engine, me.user_id, "workout", SQUATS)
    [meal] = (await call(app, me, "GET", "/logs/nutrition")).json()["logs"]
    assert meal["foods"] == [{"name": "Poha", "portion": "1 plate", "calories": 300.0,
                              "protein_g": 8.0, "carbs_g": 50.0, "fat_g": 9.0}]
    assert meal["macros"] == {"protein_g": 8.0, "carbs_g": 50.0, "fat_g": 9.0,
                              "complete": True}
    [workout] = (await call(app, me, "GET", "/logs/workouts")).json()["logs"]
    assert workout["exercises"] == [{"name": "Back squat", "catalogue_id": "back_squat",
                                     "sets": 3, "reps": 8, "duration_s": None}]


@pytest.mark.parametrize(("foods", "macros", "sent_foods", "sent_macros"), [
    # The old app's shape
    (json.dumps({"foods": [{"name": "Dal", "quantity": "1 bowl", "calories": 200}]}), None,
     [{"name": "Dal", "portion": None, "calories": 200.0, "protein_g": None, "carbs_g": None,
       "fat_g": None}], None),
    # Not JSON, and macros that don't read
    ("dal and rice", "lots", [], None),
    # An item without a name is left out; a number where a name goes doesn't read
    (json.dumps([{"portion": "1"}, {"name": 5}, {"name": "Rice"}]),
     json.dumps({"protein_g": "much"}),
     [{"name": "Rice", "portion": None, "calories": None, "protein_g": None, "carbs_g": None,
       "fat_g": None}], None),
    (None, None, [], None),
], ids=["old-app", "not-json", "partly", "empty"])
async def test_stored_text_that_doesnt_read_is_left_out(async_engine, clean, foods, macros,
                                                       sent_foods, sent_macros):
    app, me = await _app(async_engine, clean)
    await sql(async_engine, "INSERT INTO nutrition_logs (user_id, meal_type, foods, macros) "
              "VALUES (:u, 'lunch', :f, :m)", u=me.user_id, f=foods, m=macros)
    response = await call(app, me, "GET", "/logs/nutrition")
    assert response.status_code == 200
    [meal] = response.json()["logs"]
    assert (meal["foods"], meal["macros"]) == (sent_foods, sent_macros)


async def test_an_old_workout_row_reads_too(async_engine, clean):
    app, me = await _app(async_engine, clean)
    await sql(async_engine, "INSERT INTO workout_logs (user_id, exercise_type, exercises) "
              "VALUES (:u, 'walk', :e)", u=me.user_id,
              e=json.dumps({"exercises": [{"name": "Push-ups", "sets": 3, "reps": 15}]}))
    [workout] = (await call(app, me, "GET", "/logs/workouts")).json()["logs"]
    assert workout["exercises"] == [{"name": "Push-ups", "catalogue_id": None, "sets": 3,
                                     "reps": 15, "duration_s": None}]


PEANUT = {"kind": "conflict", "item": "Poha", "rule_id": "DI-ALG-01", "attributes": ["peanut"],
          "reason": "Contains peanut: you have a peanut allergy", "left_out": True}
SESAME = {**PEANUT, "attributes": ["sesame"], "reason": "Contains sesame", "left_out": False}
UNCHECKED = {"kind": "unchecked", "item": "Poha", "rule_id": "DI-UNK-01",
             "attributes": ["masala"], "reason": "Not checked", "left_out": False}


async def test_each_log_sends_the_warnings_stored_with_it(async_engine, clean):
    app, me = await _app(async_engine, clean)
    await _logged(async_engine, me.user_id, "meal",
                  {"meal": "breakfast", "foods": [POHA], "when": SQUATS["when"]},
                  warnings=[PEANUT, SESAME, UNCHECKED])
    await _logged(async_engine, me.user_id, "workout", SQUATS)
    [meal] = (await call(app, me, "GET", "/logs/nutrition")).json()["logs"]
    assert meal["warnings"] == [PEANUT, SESAME, UNCHECKED]
    [workout] = (await call(app, me, "GET", "/logs/workouts")).json()["logs"]
    assert workout["warnings"] == []  # stored as NULL


@pytest.mark.parametrize("stored", [
    json.dumps([{"kind": "conflict"}, PEANUT]),  # one that doesn't read is left out
    json.dumps({"kind": "conflict"}),
    json.dumps("peanut"),
], ids=["partly", "not-a-list", "text"])
async def test_stored_warnings_that_dont_read_are_left_out(async_engine, clean, stored):
    app, me = await _app(async_engine, clean)
    await sql(async_engine, "INSERT INTO mental_fitness_logs (user_id, activity_type, warnings) "
              "VALUES (:u, 'breathing', CAST(:w AS json))", u=me.user_id, w=stored)
    response = await call(app, me, "GET", "/logs/mental-fitness")
    assert response.status_code == 200
    [practice] = response.json()["logs"]
    assert practice["warnings"] == ([PEANUT] if stored.startswith("[") else [])
