"""A repeated entry waits on the repeat card (Plan C.17, P4.16, Part E #67), end to end
on a real Postgres with scripted models: an entry matching one already logged (a meal
with the same slot that day and a food in common, a workout or practice within 2 hours)
isn't saved; it waits for Log again, Replace or Don't log, and the coach is told what
it matches."""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import NOT_LOGGED
from app.agents.schemas import WRITE_ARGS, StagedWrite
from app.config.limits import GUEST_LOGS_SENT
from app.data.state_store import StateStore
from app.storage.logs import insert_log

from .test_admission import account, guest, sql
from .test_chat import (
    Models,
    _events,
    _mental,
    _names,
    _payload,
    _post,
    _route,
    _settled,
    requests_finish,  # noqa: F401  (autouse: requests end before the DB is emptied)
)
from .test_writes import (
    BRIDGES,
    BRIDGES_AS_SENT,
    DAL,
    RICE,
    _ack,
    _calls,
    _confirm,
    _count,
    _discard,
    _lunch,
    _writes_app,
)

LUNCH = {"meal": "lunch", "foods": [DAL]}


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


async def _logged(engine, user_id, kind, args, at) -> int:
    """An entry the person logged earlier, dated `at`."""
    write = StagedWrite(kind=kind, args=WRITE_ARGS[kind].model_validate(
        {"activity": None, **args} if kind == "workout" else args))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        log_id = await insert_log(session, user_id, write, at)
        await session.commit()
    return log_id


async def _turn(store, async_engine, me, coach, calls, reply, message="log it", **payload):
    models = Models(router=[_route(coach)], **{coach: [_calls(*calls), reply]})
    app = _writes_app(store, async_engine, models)
    events = _events(await _post(app, me, _payload(message, **payload)))
    await _settled()
    return app, models, events


def _pending(events) -> list[dict]:
    return [d for n, d in events if n == "pending_write"]


# --- What matches ---


async def test_the_same_lunch_twice_waits_with_the_earlier_entry_named(store, async_engine,
                                                                       lunchtime):
    me = await account(store, async_engine)
    earlier = lunchtime - timedelta(hours=1)
    log_id = await _logged(async_engine, me.user_id, "meal", LUNCH, earlier)
    _, models, events = await _turn(
        store, async_engine, me, "nutrition",
        [("log_meal", {"meal": "lunch", "foods": [RICE, DAL]})],
        _lunch("Your dal is logged. Rice and dal is a good lunch."), "is my lunch logged?")
    assert "committed" not in _names(events) and "logged_note" not in _names(events)
    [card] = _pending(events)
    repeat = card["repeat_of"]
    assert datetime.fromisoformat(repeat.pop("at")) == earlier
    assert repeat == {"summary": "Lunch: Dal", "log_id": str(log_id), "this_turn": False}
    assert await _count(async_engine, "nutrition_logs") == 1
    # The coach is told what it matches, and not to claim anything about it
    tool = models.fakes["nutrition"].calls[1].messages[-1].output
    assert tool["status"] == "held" and tool["code"] == "repeat"
    assert "Lunch: Dal, 11:30 am" in tool["next"]
    assert "tap Replace on the card below" in tool["next"]  # it can be replaced (#67)
    # "Is logged" is removed as ever; the card answers it, and nothing says "not saved"
    text = "".join(d["chunk"] for n, d in events if n == "text")
    assert text == "Rice and dal is a good lunch."
    [end] = [d for n, d in events if n == "section_end"]
    assert NOT_LOGGED not in end.get("warnings", [])


async def test_a_lunch_named_as_one_food_repeats_the_same_lunch_as_three(
        store, async_engine, lunchtime):
    """Live (Part E #67): the same message sent twice; the coach split the lunch into
    three foods, then named it as one."""
    me = await account(store, async_engine)
    salad = {**RICE, "name": "Cucumber salad", "ingredients": ["cucumber"]}
    await _logged(async_engine, me.user_id, "meal",
                  {"meal": "lunch", "foods": [DAL, RICE, salad]}, lunchtime)
    whole = {**DAL, "name": "Dal, rice and cucumber salad", "ingredients": ["lentils", "rice"]}
    _, _, events = await _turn(store, async_engine, me, "nutrition",
                               [("log_meal", {"meal": "lunch", "foods": [whole]})], _lunch())
    [card] = _pending(events)
    assert card["repeat_of"]["summary"] == "Lunch: Dal, Rice, Cucumber salad"
    assert "committed" not in _names(events)


@pytest.mark.parametrize("earlier, args", [
    (timedelta(days=1), LUNCH),  # yesterday's lunch
    (timedelta(hours=4), {"meal": "breakfast", "foods": [DAL]}),  # another meal
    (timedelta(hours=1), {"meal": "lunch", "foods": [RICE]}),  # no food in common
], ids=["another-day", "another-meal", "another-food"])
async def test_a_meal_that_isnt_a_repeat_saves(store, async_engine, lunchtime, earlier, args):
    me = await account(store, async_engine)
    await _logged(async_engine, me.user_id, "meal", args, lunchtime - earlier)
    _, _, events = await _turn(store, async_engine, me, "nutrition",
                               [("log_meal", LUNCH)], _lunch())
    assert "committed" in _names(events) and _pending(events) == []
    assert await _count(async_engine, "nutrition_logs") == 2


@pytest.mark.parametrize("hours, held", [(1, True), (2, True), (3, False), (-1.5, True)])
async def test_a_workout_repeats_only_within_2_hours(store, async_engine, lunchtime, hours,
                                                    held):
    me = await account(store, async_engine)
    await _logged(async_engine, me.user_id, "workout", BRIDGES, lunchtime - timedelta(hours=hours))
    _, _, events = await _turn(store, async_engine, me, "physical",
                               [("log_workout", BRIDGES)], _ack())
    assert bool(_pending(events)) is held
    assert ("committed" in _names(events)) is not held


async def test_another_exercise_or_activity_isnt_a_repeat(store, async_engine, lunchtime):
    me = await account(store, async_engine)
    hour_ago = lunchtime - timedelta(hours=1)
    await _logged(async_engine, me.user_id, "workout", BRIDGES, hour_ago)
    archery = {"catalogue_id": "other_activity", "activity": "Archery", "sets": None,
               "reps": None, "duration_s": 3600, "note": ""}
    await _logged(async_engine, me.user_id, "workout", archery, hour_ago)
    dance = {**archery, "activity": "Salsa class"}
    _, _, events = await _turn(store, async_engine, me, "physical",
                               [("log_workout", dance)], _ack())
    assert "committed" in _names(events) and _pending(events) == []


async def test_someone_elses_entry_is_never_a_repeat(store, async_engine, lunchtime):
    other = await account(store, async_engine, email="other@example.com")
    await _logged(async_engine, other.user_id, "workout", BRIDGES, lunchtime)
    me = await account(store, async_engine)
    _, _, events = await _turn(store, async_engine, me, "physical",
                               [("log_workout", BRIDGES)], _ack())
    assert "committed" in _names(events) and _pending(events) == []


async def test_a_practice_repeats_too(store, async_engine, lunchtime):
    me = await account(store, async_engine)
    meditation = {"catalogue_id": "box_breathing", "duration_min": 10, "mood_before": None,
                  "mood_after": None, "note": ""}
    await _logged(async_engine, me.user_id, "practice", meditation, lunchtime - timedelta(hours=1))
    _, _, events = await _turn(store, async_engine, me, "mental",
                               [("log_practice", meditation)], _mental(),
                               "was that a good practice to log?")
    [card] = _pending(events)
    assert card["repeat_of"]["summary"].endswith(": 10 min")


async def test_two_repeats_in_one_message_both_wait(store, async_engine, lunchtime):
    """One card on the screen (the app groups an answer's repeats); two entries here."""
    me = await account(store, async_engine)
    await _logged(async_engine, me.user_id, "meal", LUNCH, lunchtime - timedelta(hours=1))
    snack = {"meal": "snack", "foods": [RICE]}
    await _logged(async_engine, me.user_id, "meal", snack, lunchtime - timedelta(hours=2))
    _, _, events = await _turn(store, async_engine, me, "nutrition",
                               [("log_meal", LUNCH), ("log_meal", snack)], _lunch(),
                               "how's my day looking?")
    cards = _pending(events)
    assert [c["repeat_of"]["summary"] for c in cards] == ["Lunch: Dal", "Snack: Rice"]
    assert "committed" not in _names(events)
    assert await _count(async_engine, "nutrition_logs") == 2


async def test_one_activity_logged_twice_in_one_turn_waits_once(store, async_engine):
    """D052: two log calls for one activity in one message."""
    me = await account(store, async_engine)
    app, models, events = await _turn(store, async_engine, me, "physical",
                                      [("log_workout", BRIDGES), ("log_workout", BRIDGES)],
                                      _ack())
    [committed] = [d for n, d in events if n == "committed"]
    assert len(committed["writes"]) == 1
    [card] = _pending(events)
    assert card["repeat_of"]["this_turn"] is True and card["repeat_of"]["log_id"] is None
    tool = models.fakes["physical"].calls[1].messages[-1].output
    assert "Replace" not in tool["next"] and "Don't mention a card" in tool["next"]
    # Nothing to replace: it isn't saved until the turn is
    response = await _confirm(app, me, card["write_id"], {"replace": True})
    assert response.status_code == 400
    assert await sql(async_engine, "SELECT status FROM pending_writes") == [("pending",)]


# --- Log again, Replace, Don't log ---


async def _repeat(store, async_engine, lunchtime):
    me = await account(store, async_engine)
    old_id = await _logged(async_engine, me.user_id, "workout", BRIDGES,
                           lunchtime - timedelta(hours=1))
    app, _, events = await _turn(store, async_engine, me, "physical",
                                 [("log_workout", BRIDGES)], _ack())
    [card] = _pending(events)
    return app, me, old_id, card["write_id"]


async def test_log_again_saves_it_once(store, async_engine, lunchtime):
    app, me, _, write_id = await _repeat(store, async_engine, lunchtime)
    first = await _confirm(app, me, write_id)
    again = await _confirm(app, me, write_id)
    assert first.status_code == again.status_code == 200 and first.json() == again.json()
    assert await _count(async_engine, "workout_logs") == 2


async def test_replace_deletes_the_earlier_entry_as_it_logs_this_one(store, async_engine,
                                                                    lunchtime):
    """D052: "the chai was at 11:30" changes the entry instead of adding one."""
    app, me, old_id, write_id = await _repeat(store, async_engine, lunchtime)
    response = await _confirm(app, me, write_id, {"replace": True})
    assert response.status_code == 200
    [(new_id,)] = await sql(async_engine, "SELECT id FROM workout_logs")
    assert new_id != old_id
    assert response.json()["writes"][0]["write_id"] == str(new_id)


async def test_replace_after_the_earlier_entry_was_deleted_still_logs(store, async_engine,
                                                                     lunchtime):
    app, me, old_id, write_id = await _repeat(store, async_engine, lunchtime)
    await sql(async_engine, f"DELETE FROM workout_logs WHERE id = {old_id}")
    assert (await _confirm(app, me, write_id, {"replace": True})).status_code == 200
    assert await _count(async_engine, "workout_logs") == 1


async def test_dont_log_keeps_only_the_earlier_entry(store, async_engine, lunchtime):
    app, me, old_id, write_id = await _repeat(store, async_engine, lunchtime)
    assert (await _discard(app, me, write_id)).status_code == 200
    assert await sql(async_engine, "SELECT id FROM workout_logs") == [(old_id,)]


async def test_replace_only_on_a_repeat(store, async_engine):
    me = await account(store, async_engine)
    app, _, events = await _turn(store, async_engine, me, "nutrition",
                                 [("log_meal", {**LUNCH, "when": {
                                     "day": "yesterday", "time": None, "ampm": None,
                                     "part": None}})], _lunch())
    [card] = _pending(events)  # held for the time only
    response = await _confirm(app, me, card["write_id"], {"replace": True})
    assert response.status_code == 400
    assert await _count(async_engine, "nutrition_logs") == 0


# --- Guests: the entries their browser sends ---


def _guest_log(args, at, log_id="g1") -> dict:
    return {"id": log_id, "at": at.isoformat(),
            "entry": {"kind": "workout", "args": args, "warnings": []}}


async def test_a_guest_repeat_of_an_entry_the_browser_sent_waits(store, async_engine,
                                                                 lunchtime):
    me = await guest(store)
    sent = [_guest_log(BRIDGES_AS_SENT, lunchtime - timedelta(hours=1)),
            {"entry": {"kind": "nope"}, "at": "yesterday"}]  # unreadable: skipped
    _, _, events = await _turn(store, async_engine, me, "physical",
                               [("log_workout", BRIDGES)], _ack(), guest_logs=sent)
    assert "committed" not in _names(events)
    [card] = _pending(events)
    assert card["repeat_of"]["log_id"] == "g1"
    assert card["entry"]["repeat_of"]["log_id"] == "g1"  # the browser keeps it to replace


async def test_a_guest_entry_outside_the_window_saves(store, async_engine, lunchtime):
    me = await guest(store)
    sent = [_guest_log(BRIDGES_AS_SENT, lunchtime - timedelta(hours=5))]
    _, _, events = await _turn(store, async_engine, me, "physical",
                               [("log_workout", BRIDGES)], _ack(), guest_logs=sent)
    assert "committed" in _names(events) and _pending(events) == []


async def test_guest_logs_are_capped_and_only_for_guests(store, async_engine, lunchtime):
    sent = [_guest_log(BRIDGES_AS_SENT, lunchtime)] * (GUEST_LOGS_SENT + 1)
    models = Models()
    app = _writes_app(store, async_engine, models)
    response = await _post(app, await guest(store), _payload("hi", guest_logs=sent))
    assert response.status_code == 400
    me = await account(store, async_engine)
    response = await _post(app, me, _payload("hi", guest_logs=sent[:1]))
    assert response.status_code == 400 and "logs" in response.json()["message"]
