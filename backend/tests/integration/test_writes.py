"""Writes from a chat turn and their confirmation, end to end on a real Postgres, with
scripted models (Plan C.17, P4.8): a write is gated when a coach stages it; a turn
without web search commits with its messages in one transaction, a turn with one waits
for the person's confirmation; confirm commits once, and checks the profile again."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, time, timedelta
from unittest.mock import ANY

import httpx
import pytest
import pytest_asyncio

from app.agents.clock import UTC_ZONE, now_note, when_text, zone
from app.agents.schemas import (
    LoggedFood,
    LogMealArgs,
    LogWorkoutArgs,
    MentalReply,
    NutritionReply,
    PhysicalReply,
    StagedWrite,
    UserProfile,
)
from app.agents.tools import WebSearch
from app.config.settings import get_settings
from app.data.state_store import StateStore
from app.jobs.scheduler import Jobs
from app.orchestration import staging
from app.orchestration.principal import csrf_token
from app.providers import LLMResult, ToolCall, Usage
from app.routers import chat

from ..unit.tools.conftest import FakeSearchClient
from .test_admission import APP, account, guest, settings, sql
from .test_chat import (
    KNEE_NOTE,
    Models,
    _app,
    _events,
    _names,
    _payload,
    _physical,
    _post,
    _result,
    _route,
    _settled,
    requests_finish,  # noqa: F401  (autouse: requests end before the DB is emptied)
)

pytestmark = pytest.mark.asyncio

BRIDGES = {"catalogue_id": "glute_bridge", "sets": 3, "reps": 12, "duration_s": None,
           "note": ""}
SQUATS = {"catalogue_id": "back_squat", "sets": 1, "reps": 10, "duration_s": None, "note": ""}
DAL = {"day": None, "name": "Dal", "ingredients": ["lentils"], "allergen_tags": [],
       "diet_tags": ["vegan"], "portion": "1 bowl", "calories": 230, "note": "",
       "protein_g": 12, "carbs_g": 35, "fat_g": 5}
NOW = {"day": None, "time": None, "ampm": None, "part": None}  # a log's `when`: just now
RICE = {**DAL, "name": "Rice", "ingredients": ["rice"], "calories": 200, "protein_g": 4,
        "carbs_g": 45, "fat_g": 0.5}
KNEE = {"condition_ids": ["knee_ligament_injury"], "allergen_tags": [], "diet_tags": [],
        "notes": ""}


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


def _calls(*calls) -> LLMResult:
    return LLMResult(provider="fake", model="m", usage=Usage(900, 40),
                     tool_calls=tuple(ToolCall(f"c{i}", name, args)
                                      for i, (name, args) in enumerate(calls)))


def _ack(summary="Nice work.") -> LLMResult:
    return _result(PhysicalReply(kind="log_ack", summary=summary, items=[], notes=[],
                                 source_ids=[], follow_up=None, risk_flag=False))


def _lunch(summary="Lunch noted.") -> LLMResult:
    return _result(NutritionReply(kind="log_ack", summary=summary, items=[], notes=[],
                                  source_ids=[], follow_up=None, risk_flag=False))


def _with_search(models: Models) -> Models:
    models.services.search = WebSearch(FakeSearchClient(), None)
    return models


def _writes_app(store, async_engine, models):
    app = _app(store, async_engine, models)
    app.include_router(chat.writes_router)
    return app


async def _confirm(app, principal, write_id, body=None) -> httpx.Response:
    cfg = settings()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://testserver") as client:
        return await client.post(
            f"/agents/writes/{write_id}/confirm", json=body,
            headers={"origin": APP, "x-csrf-token": csrf_token(principal.raw_session_id, cfg)},
            cookies={cfg.session_cookie: principal.raw_session_id})


def _line(write: dict, tz=UTC_ZONE) -> str:
    """A "Logged" line without its time, once the time is checked to be the entry's own,
    in the person's zone (Part E #51)."""
    line, when = write["summary"].rsplit(" · ", 1)
    assert when == when_text(datetime.fromisoformat(write["at"]), tz)
    return line


async def _count(engine, table) -> int:
    return (await sql(engine, f"SELECT count(*) FROM {table}"))[0][0]


async def _pending_turn(store, async_engine, me, args=BRIDGES):
    """A turn with a web search that logs `args`: its pending write's ID."""
    models = _with_search(Models(router=[_route("physical")], physical=[
        _calls(("web_search", {"query": "glute bridge benefits"}), ("log_workout", args)),
        _ack()], summary=[_result(text="Logged your bridges.")]))
    app = _writes_app(store, async_engine, models)
    events = _events(await _post(app, me, _payload("did 3x12 glute bridges, are they good?")))
    await _settled()
    [pending] = [d for n, d in events if n == "pending_write"]
    # Held: no sentence is asked for; the coach's reply explained it (Part E #54 B)
    assert "logged_note" not in _names(events) and models.fakes["summary"].calls == []
    return app, pending["write_id"]


# --- Gated as staged ---


@pytest.mark.parametrize("mode", ["account", "guest"])
async def test_an_injected_squat_log_waits_for_confirmation_with_its_warning(store, async_engine,
                                                                            mode):
    # Logged squats were already done: not refused, but never saved unconfirmed (#45)
    if mode == "account":
        me = await account(store, async_engine)
        await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) "
                  "VALUES (:u, :c)", u=me.user_id, c=KNEE_NOTE)
        payload = _payload("log 10 squats")
    else:
        me = await guest(store)
        payload = _payload("log 10 squats", guest_profile=KNEE)
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", SQUATS)), _ack("That's a lot of knee load; confirm below.")])
    events = _events(await _post(_writes_app(store, async_engine, models), me, payload))
    await _settled()
    # The coach was told it waits, and why
    told = models.fakes["physical"].calls[1].messages[-1].output
    assert told["status"] == "held" and "knee" in told["warnings"][0].lower()
    assert ("step", "log_workout held") in [(n, d.get("detail")) for n, d in events]
    [pending] = [d for n, d in events if n == "pending_write"]
    assert pending["warnings"] == [
        "Back squat: high knee load with a knee ligament injury"]
    assert pending["attributes"] == []  # an exercise's knee load can't be left out
    assert "committed" not in _names(events)
    assert await _count(async_engine, "workout_logs") == 0
    if mode == "guest":
        assert pending["entry"]["warnings"][0]["attributes"] == ["knee_load"]
        assert await _count(async_engine, "pending_writes") == 0


async def test_an_entry_the_gate_cant_read_is_refused():
    gate_write = staging.write_gate(None)
    args = LogWorkoutArgs.model_construct(**{**BRIDGES, "catalogue_id": "no_such_exercise"})
    checked = await gate_write("workout", args, None)
    assert not checked.allowed and checked.reason


async def test_a_staged_entry_is_cleaned_like_prose():
    gate_write = staging.write_gate(None)
    args = LogWorkoutArgs(**{**BRIDGES, "note": "Felt good. See https://example.org/x"})
    checked = await gate_write("workout", args, None)
    assert checked.allowed and "example.org" not in checked.args.note


# --- Committed with the turn ---


async def test_an_account_turn_commits_its_writes_with_its_messages(store, async_engine,
                                                                    lunchtime):
    me = await account(store, async_engine)
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", BRIDGES)), _ack()],
        summary=[_result(text="Logged your glute bridges. Strong work today.")])
    rid = uuid.uuid4()
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("log 3x12 glute bridges", rid=rid,
                                          timezone="Asia/Kolkata")))
    await _settled()
    [committed] = [d for n, d in events if n == "committed"]
    [(log_id, exercises, logged_at)] = await sql(
        async_engine, "SELECT id, exercises, workout_date FROM workout_logs")
    [write] = committed["writes"]
    assert _line(write, zone("Asia/Kolkata")) == "Logged: Glute bridge: 3 x 12"
    assert datetime.fromisoformat(write.pop("at")) == logged_at == lunchtime
    assert write == {"kind": "workout", "summary": write["summary"], "write_id": str(log_id),
                     "entry": None, "warnings": []}
    assert '"catalogue_id": "glute_bridge"' in exercises
    coach = models.fakes["physical"].calls[0].messages[-1].text
    assert now_note(zone("Asia/Kolkata"), logged_at) in coach  # the person's day (#51)
    # Then the coach's sentence (Part E #54 B), which may say "logged": the save happened
    assert _names(events)[-4:] == ["section_end", "committed", "logged_note", "done"]
    assert [d["text"] for n, d in events if n == "logged_note"] == [
        "Logged your glute bridges. Strong work today."]
    prompt = models.fakes["summary"].calls[0].messages[-1].text
    assert "Glute bridge: 3 x 12" in prompt and "log 3x12 glute bridges" in prompt
    assert await _count(async_engine, "conversation_messages") == 2


async def test_a_failed_sentence_leaves_the_save_and_the_stream_whole(store, async_engine):
    """No scripted reply: the sentence's call fails as a bug. The record went out and the
    turn ends normally, without the sentence (Part E #54 B)."""
    me = await account(store, async_engine)
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", BRIDGES)), _ack()])
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("log 3x12 glute bridges")))
    await _settled()
    assert _names(events)[-3:] == ["section_end", "committed", "done"]
    assert await _count(async_engine, "workout_logs") == 1


async def test_an_unknown_time_zone_is_refused_before_anything_runs(store, async_engine):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    for name in ("Mars/Olympus", "../../etc/passwd", "x" * 65):
        response = await _post(app, me, _payload("log 3x12 glute bridges", timezone=name))
        assert response.status_code in (400, 422), name
    write_id = await _held(store, me)
    response = await _confirm(app, me, write_id, {"timezone": "Mars/Olympus"})
    assert response.status_code == 400
    assert await sql(async_engine, "SELECT status FROM pending_writes") == [("pending",)]


async def test_messages_and_writes_are_one_transaction(store, async_engine, monkeypatch):
    me = await account(store, async_engine)

    async def broken(session, user_id, write):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(staging, "insert_log", broken)
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", BRIDGES)), _ack()])
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("log 3x12 glute bridges")))
    await _settled()
    # Neither the log nor the messages: nothing says "Logged", and the stream ends
    assert events[-1][0] == "error" and "committed" not in _names(events)
    assert await _count(async_engine, "conversation_messages") == 0
    assert await _count(async_engine, "workout_logs") == 0


async def test_a_guest_turn_sends_its_entries_and_stores_nothing(store, async_engine):
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", BRIDGES)), _ack()])
    events = _events(await _post(_writes_app(store, async_engine, models), await guest(store),
                                 _payload("log 3x12 glute bridges")))
    await _settled()
    [committed] = [d for n, d in events if n == "committed"]
    assert _line(committed["writes"][0]) == "Logged: Glute bridge: 3 x 12"
    del committed["writes"][0]["at"]
    assert committed["writes"] == [{"kind": "workout", "summary": ANY, "write_id": None,
                                    "warnings": [],
                                    "entry": {"kind": "workout", "args": {**BRIDGES, "when": NOW},
                                              "warnings": [], "at": None,
                                              "time_guessed": False}}]
    assert await _count(async_engine, "workout_logs") == 0
    assert await _count(async_engine, "pending_writes") == 0


async def test_a_reply_that_fails_the_gate_discards_the_staged_writes(store, async_engine):
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) "
              "VALUES (:u, :c)", u=me.user_id, c=KNEE_NOTE)
    blocked = _physical("back_squat", "glute_bridge")
    # Both tries log the bridges, and both plans still hold squats
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", BRIDGES)), blocked, _calls(("log_workout", BRIDGES)), blocked])
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("log my bridges and give me a leg plan")))
    await _settled()
    assert [d["removed_count"] for n, d in events if n == "section_end"] == [1]
    assert "committed" not in _names(events) and "pending_write" not in _names(events)
    assert await _count(async_engine, "workout_logs") == 0
    assert await _count(async_engine, "pending_writes") == 0


# --- Held after a web search ---


async def test_a_turn_with_web_search_holds_its_writes(store, async_engine):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me)
    assert await _count(async_engine, "workout_logs") == 0
    [(status, kind, hash_)] = await sql(async_engine, "SELECT status, kind, profile_hash "
                                        "FROM pending_writes WHERE id = :i", i=write_id)
    assert (status, kind) == ("pending", "workout") and len(hash_) == 64
    assert await _count(async_engine, "conversation_messages") == 2  # same transaction


async def test_a_guests_held_entry_carries_the_profile_hash(store, async_engine):
    models = _with_search(Models(router=[_route("physical")], physical=[
        _calls(("web_search", {"query": "bridges"}), ("log_workout", BRIDGES)), _ack()]))
    profile = {**KNEE, "notes": "desk job"}
    events = _events(await _post(_writes_app(store, async_engine, models), await guest(store),
                                 _payload("did bridges, good?", guest_profile=profile)))
    await _settled()
    [pending] = [d for n, d in events if n == "pending_write"]
    # The hash of the profile the browser sent, so it can tell if it changed (C.17)
    assert pending["profile_hash"] == staging.profile_hash(UserProfile(**profile))
    assert pending["entry"] == {"kind": "workout", "args": {**BRIDGES, "when": NOW},
                                "warnings": [], "at": None, "time_guessed": False}
    assert pending["warnings"] == []  # held for the search only
    assert await _count(async_engine, "pending_writes") == 0


async def test_a_search_holds_only_the_writes_of_the_coach_that_ran_it(store, async_engine):
    me = await account(store, async_engine)
    dal = LoggedFood(day=None, name="Dal", ingredients=["lentils"], allergen_tags=[],
                     diet_tags=[], portion="1 bowl", calories=300, note="", protein_g=14,
                     carbs_g=40, fat_g=6)
    meal = {"meal": "lunch", "foods": [dal.model_dump(mode="json")]}
    lunch = _result(NutritionReply(kind="log_ack", summary="Lunch noted.", items=[], notes=[],
                                   source_ids=[], follow_up=None, risk_flag=False))
    models = _with_search(Models(
        router=[_route("physical", "nutrition")],
        physical=[_calls(("log_workout", BRIDGES)), _ack()],
        nutrition=[_calls(("web_search", {"query": "dal protein"}), ("log_meal", meal)), lunch],
        summary=[_result(text="Good day."), _result(text="Bridges logged. Nice.")]))
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("log my bridges and my dal lunch")))
    await _settled()
    [committed] = [d["writes"] for n, d in events if n == "committed"]
    assert [w["kind"] for w in committed] == ["workout"]
    assert [d["summary"] for n, d in events if n == "pending_write"] == [
        "Lunch: Dal · 300 kcal · protein 14 g, carbs 40 g, fat 6 g"]


# --- Confirm (C.17) ---


async def test_confirm_commits_once_and_a_repeat_gets_the_same_answer(store, async_engine):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me)
    first = await _confirm(app, me, write_id)
    again = await _confirm(app, me, write_id)
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    [(log_id,)] = await sql(async_engine, "SELECT id FROM workout_logs")
    [write] = first.json()["writes"]
    assert _line(write) == "Logged: Glute bridge: 3 x 12"  # when it was said, no zone sent
    assert write == {"kind": "workout", "summary": write["summary"], "at": write["at"],
                     "write_id": str(log_id), "entry": None, "warnings": []}
    assert (await sql(async_engine, "SELECT status FROM pending_writes")) == [("committed",)]


async def test_a_held_entry_is_never_called_refused_or_saved(store, async_engine):
    """Part E #52: live, the coach said "I couldn't save this snack" over a Confirm card."""
    me = await account(store, async_engine)
    models = _with_search(Models(router=[_route("physical")], physical=[
        _calls(("web_search", {"query": "glute bridge benefits"}), ("log_workout", BRIDGES)),
        _ack("Glute bridges build your hips. I couldn't save it yet. Confirm it below.")]))
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("did 3x12 glute bridges, are they good?")))
    await _settled()
    text = "".join(d["chunk"] for n, d in events if n == "text")
    assert "couldn't save" not in text and "Confirm it below." in text
    assert [n for n, _ in events].count("pending_write") == 1


# --- Waiting, replaced, dated and discarded (Part E #50) ---


async def _discard(app, principal, write_id) -> httpx.Response:
    cfg = settings()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://testserver") as client:
        return await client.post(
            f"/agents/writes/{write_id}/discard",
            headers={"origin": APP, "x-csrf-token": csrf_token(principal.raw_session_id, cfg)},
            cookies={cfg.session_cookie: principal.raw_session_id})


async def _held(store, me, kind="meal", args=None, trace="t-held") -> str:
    """A held entry as a turn stages it, without the turn."""
    args = args or LogMealArgs(meal="lunch", foods=[LoggedFood(**DAL)])
    write = StagedWrite(kind=kind, args=args)
    return str(await store.stage_write(me.user_id, kind, staging.held_payload(write),
                                       "hash", trace))


def _ago(**delta) -> str:
    return (datetime.now(UTC) - timedelta(**delta)).isoformat()


async def test_a_held_entry_waits_with_no_time_limit_and_keeps_when_it_was_said(
        store, async_engine):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me)
    [(expires, said)] = await sql(async_engine, "SELECT expires_at, created_at "
                                  "FROM pending_writes")
    assert expires is None
    await sql(async_engine, "UPDATE pending_writes SET created_at = now() - interval '3 days'")
    await Jobs(async_engine, None).run_once()
    assert (await _confirm(app, me, write_id)).status_code == 200
    [(logged, staged)] = await sql(async_engine, "SELECT w.workout_date, p.created_at "
                                   "FROM workout_logs w, pending_writes p")
    assert logged == staged  # when they said it, not when they tapped


async def test_the_event_carries_when_it_was_said_and_the_meal(store, async_engine):
    me = await account(store, async_engine)
    models = _with_search(Models(router=[_route("nutrition")], nutrition=[
        _calls(("web_search", {"query": "dal protein"}),
               ("log_meal", {"meal": "lunch", "foods": [DAL]})), _lunch()]))
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("had dal for lunch, is it good protein?")))
    await _settled()
    [pending] = [d for n, d in events if n == "pending_write"]
    [(write_id, said)] = await sql(async_engine, "SELECT id, created_at FROM pending_writes")
    assert (pending["write_id"], datetime.fromisoformat(pending["at"])) == (str(write_id), said)
    assert pending["meal"] == "lunch" and "expires_at" not in pending


# --- When it happened, from what the person said (Part E #51 step 2) ---


def _yesterday(time=None, ampm=None, part=None) -> dict:
    return {"day": "yesterday", "time": time, "ampm": ampm, "part": part}


async def test_a_time_the_person_gave_is_logged_at_it(store, async_engine, lunchtime):
    me = await account(store, async_engine)
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", {**BRIDGES, "when": _yesterday("7:00", "am")})), _ack()],
        summary=[_result(text="Bridges logged for yesterday morning.")])
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("did 3x12 glute bridges yesterday at 7 am",
                                          timezone="Asia/Kolkata")))
    await _settled()
    india = zone("Asia/Kolkata")  # 7 am the day before, in their zone
    day = lunchtime.astimezone(india).date() - timedelta(days=1)
    seven = datetime.combine(day, time(7), tzinfo=india).astimezone(UTC)
    [[write]] = [d["writes"] for n, d in events if n == "committed"]
    assert _line(write, india) == "Logged: Glute bridge: 3 x 12"
    assert datetime.fromisoformat(write["at"]) == seven
    assert await sql(async_engine, "SELECT workout_date FROM workout_logs") == [(seven,)]
    note = models.fakes["summary"].calls[0].messages[-1].text
    assert f"({when_text(seven, india)})" in note


async def test_no_time_given_waits_on_the_card_with_the_usual_time(store, async_engine,
                                                                  lunchtime):
    """Owner (9 Nov 2026, B): "yesterday's lunch" has no time; 1 pm is filled in, and the
    person picks the time and confirms. Nothing is saved, and no sentence comes."""
    me = await account(store, async_engine)
    models = Models(router=[_route("nutrition")], nutrition=[
        _calls(("log_meal", {"meal": "lunch", "foods": [DAL], "when": _yesterday()})),
        _lunch("I couldn't save it yet. Pick the time on the card.")],
        summary=[_result(text="Logged.")])
    app = _writes_app(store, async_engine, models)
    events = _events(await _post(app, me, _payload("log yesterday's lunch: dal")))
    await _settled()
    one_pm = (lunchtime - timedelta(days=1)).replace(hour=13, minute=0)
    [pending] = [d for n, d in events if n == "pending_write"]
    assert pending["time_guessed"] is True and datetime.fromisoformat(pending["at"]) == one_pm
    assert "committed" not in _names(events) and models.fakes["summary"].calls == []
    said = " ".join(d["chunk"] for n, d in events if n == "text")
    assert said == "Pick the time on the card."  # held: never "couldn't save" (#52)
    tool = models.fakes["nutrition"].calls[1].messages[-1].output
    assert tool["status"] == "held" and "yesterday, 1:00 pm filled in" in tool["next"]
    assert await _count(async_engine, "nutrition_logs") == 0
    # Confirmed as it is: the filled-in time
    response = await _confirm(app, me, pending["write_id"])
    assert datetime.fromisoformat(response.json()["writes"][0]["at"]) == one_pm
    assert await sql(async_engine, "SELECT meal_date FROM nutrition_logs") == [(one_pm,)]


async def test_the_time_the_person_picks_is_logged(store, async_engine, lunchtime):
    me = await account(store, async_engine)
    models = Models(router=[_route("nutrition")], nutrition=[
        _calls(("log_meal", {"meal": "dinner", "foods": [DAL], "when": _yesterday()})),
        _lunch()])
    app = _writes_app(store, async_engine, models)
    events = _events(await _post(app, me, _payload("log yesterday's dinner: dal")))
    await _settled()
    [pending] = [d for n, d in events if n == "pending_write"]
    picked = (lunchtime - timedelta(days=1)).replace(hour=21, minute=15)
    response = await _confirm(app, me, pending["write_id"], {"at": picked.isoformat()})
    [write] = response.json()["writes"]
    assert datetime.fromisoformat(write["at"]) == picked
    assert _line(write).startswith("Logged: Dinner")
    assert await sql(async_engine, "SELECT meal_date FROM nutrition_logs") == [(picked,)]


async def test_a_time_ahead_of_now_logs_nothing_and_the_coach_says_so(store, async_engine):
    me = await account(store, async_engine)
    tomorrow = {"day": "today", "time": "11:30", "ampm": "pm", "part": None}
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", {**BRIDGES, "when": tomorrow})),
        _ack("I can log it once you've done it.")])
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("log my bridges for 11:30 tonight")))
    await _settled()
    assert not {"committed", "pending_write", "logged_note"} & set(_names(events))
    tool = models.fakes["physical"].calls[1].messages[-1].output
    assert tool["status"] == "refused" and "ahead of time" in tool["reason"]
    assert await _count(async_engine, "workout_logs") == 0


async def test_an_entry_held_before_when_existed_still_confirms(store, async_engine):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    old = {"args": {k: v for k, v in BRIDGES.items() if k != "when"}, "warnings": []}
    write_id = str(await store.stage_write(me.user_id, "workout", old, "hash", "t-old"))
    response = await _confirm(app, me, write_id)
    assert response.status_code == 200
    assert response.json()["writes"][0]["summary"].startswith("Logged: Glute bridge")


async def test_the_confirmed_date_time_and_meal_are_logged(store, async_engine):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    write_id = await _held(store, me)
    at = (datetime.now(UTC) - timedelta(days=2)).replace(hour=8, minute=15, microsecond=0)
    response = await _confirm(app, me, write_id, {"at": at.isoformat(), "meal": "breakfast",
                                                  "timezone": "America/New_York"})
    assert response.status_code == 200
    [write] = response.json()["writes"]
    assert _line(write, zone("America/New_York")).startswith("Logged: Breakfast")
    assert datetime.fromisoformat(write["at"]) == at
    assert await sql(async_engine, "SELECT meal_type, meal_date FROM nutrition_logs") == [
        ("breakfast", at)]


# Out of range is 400; a time without its zone can't be read at all, 422 like any bad body
@pytest.mark.parametrize("body, status", [({"at": _ago(minutes=-60)}, 400),
                                          ({"at": _ago(days=31)}, 400),
                                          ({"at": "2026-11-05T08:00:00"}, 422)])
async def test_a_date_out_of_range_is_refused_and_the_entry_still_waits(store, async_engine,
                                                                        body, status):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    write_id = await _held(store, me)
    response = await _confirm(app, me, write_id, body)
    assert response.status_code == status
    assert (await sql(async_engine, "SELECT status FROM pending_writes")) == [("pending",)]
    ok = await _confirm(app, me, write_id, {"at": _ago(days=29)})
    assert ok.status_code == 200 and await _count(async_engine, "nutrition_logs") == 1


async def test_a_bad_date_says_what_to_pick(store, async_engine):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    response = await _confirm(app, me, await _held(store, me), {"at": _ago(minutes=-60)})
    assert response.json() == {"code": "bad_date", "message":
                               "Choose a date and time in the last 30 days, not in the future."}


async def test_only_a_meal_has_a_meal_time(store, async_engine):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    write_id = await _held(store, me, "workout", LogWorkoutArgs(**BRIDGES))
    assert (await _confirm(app, me, write_id, {"meal": "lunch"})).status_code == 400
    assert (await sql(async_engine, "SELECT status FROM pending_writes")) == [("pending",)]


async def test_a_newer_entry_replaces_the_waiting_one_of_its_kind(store, async_engine):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    old_meal = await _held(store, me, trace="t1")
    workout = await _held(store, me, "workout", LogWorkoutArgs(**BRIDGES), trace="t2")
    new_meal = await _held(store, me, trace="t3")

    replaced = await _confirm(app, me, old_meal)
    assert (replaced.status_code, replaced.json()["code"]) == (410, "replaced")
    assert replaced.json()["message"] == ("A newer entry replaced this one. "
                                          "Please log it again if you still want it.")
    assert await sql(async_engine, "SELECT payload::text FROM pending_writes "
                     "WHERE id = :i", i=old_meal) == [("{}",)]  # its content is gone
    assert (await _confirm(app, me, workout)).status_code == 200  # another kind: kept
    assert (await _confirm(app, me, new_meal)).status_code == 200


async def test_one_turns_entries_of_a_kind_wait_together(store, async_engine):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    first, second = [await _held(store, me, trace="t1") for _ in range(2)]
    other = await account(store, async_engine, email="b@example.com")
    theirs = await _held(store, other, trace="t2")  # someone else's never replaces mine
    for write_id in (first, second):
        assert (await _confirm(app, me, write_id)).status_code == 200
    assert (await _confirm(app, other, theirs)).status_code == 200


async def test_a_turn_that_holds_nothing_leaves_the_waiting_entry(store, async_engine):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me)
    chat_only = _writes_app(store, async_engine, Models(router=[_route("physical")],
                                                        physical=[_ack("Sounds good.")]))
    await _post(chat_only, me, _payload("thanks!"))
    await _settled()
    assert (await _confirm(app, me, write_id)).status_code == 200


async def test_dont_log_drops_the_entry(store, async_engine):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    write_id = await _held(store, me)
    for _ in range(2):  # a repeat gets the same answer
        response = await _discard(app, me, write_id)
        assert (response.status_code, response.json()) == (200, {"discarded": True})
    assert await sql(async_engine, "SELECT status, payload::text, expires_at > now() "
                     "FROM pending_writes") == [("discarded", "{}", True)]
    confirm = await _confirm(app, me, write_id)
    assert (confirm.status_code, confirm.json()["code"]) == (409, "discarded")
    assert await _count(async_engine, "nutrition_logs") == 0


async def test_dont_log_after_logging_or_on_someone_elses_entry(store, async_engine):
    me = await account(store, async_engine)
    app = _writes_app(store, async_engine, Models())
    write_id = await _held(store, me)
    await _confirm(app, me, write_id)
    response = await _discard(app, me, write_id)
    assert (response.status_code, response.json()["code"]) == (409, "logged")
    other = await account(store, async_engine, email="b@example.com")
    assert (await _discard(app, other, await _held(store, me, trace="t9"))).status_code == 404
    assert (await _discard(app, await guest(store), write_id)).status_code == 404


async def test_a_confirm_after_the_profile_gained_a_knee_injury_is_409(store, async_engine):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me, SQUATS)
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) "
              "VALUES (:u, :c)", u=me.user_id, c=KNEE_NOTE)
    first = await _confirm(app, me, write_id)
    assert first.status_code == 409 and first.json()["code"] == "blocked"
    assert "knee" in first.json()["message"].lower()
    # Discarded: the same 409 again, even with the injury gone
    await sql(async_engine, "DELETE FROM medical_history")
    again = await _confirm(app, me, write_id)
    assert (again.status_code, again.json()) == (409, first.json())
    assert await _count(async_engine, "workout_logs") == 0
    assert (await sql(async_engine, "SELECT status FROM pending_writes")) == [("discarded",)]


async def test_a_failed_commit_leaves_the_write_pending_and_confirmable(store, async_engine,
                                                                       monkeypatch):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me)
    real = chat.insert_log

    async def broken(session, user_id, write, at=None):
        await real(session, user_id, write, at)  # the row is inserted, then the step fails
        raise RuntimeError("insert failed")

    monkeypatch.setattr(chat, "insert_log", broken)
    with pytest.raises(RuntimeError):
        await _confirm(app, me, write_id)
    assert (await sql(async_engine, "SELECT status FROM pending_writes")) == [("pending",)]
    assert await _count(async_engine, "workout_logs") == 0
    monkeypatch.setattr(chat, "insert_log", real)
    assert (await _confirm(app, me, write_id)).status_code == 200
    assert await _count(async_engine, "workout_logs") == 1


async def test_only_the_owner_can_confirm(store, async_engine):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me)
    other = await account(store, async_engine, email="other@example.com")
    assert (await _confirm(app, other, write_id)).status_code == 404
    assert (await _confirm(app, await guest(store), write_id)).status_code == 404
    assert (await _confirm(app, me, uuid.uuid4())).status_code == 404
    assert await _count(async_engine, "workout_logs") == 0


async def test_confirm_needs_the_csrf_token(store, async_engine):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me)
    app.dependency_overrides[get_settings] = settings
    cfg = settings()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://testserver") as client:
        response = await client.post(f"/agents/writes/{write_id}/confirm",
                                     headers={"origin": APP},
                                     cookies={cfg.session_cookie: me.raw_session_id})
    assert response.status_code == 403
    assert await _count(async_engine, "workout_logs") == 0


def test_the_hash_changes_with_the_profile():
    plain = UserProfile(**{**KNEE, "condition_ids": []})
    assert staging.profile_hash(plain) != staging.profile_hash(UserProfile(**KNEE))
    assert staging.profile_hash(None) != staging.profile_hash(plain)


# --- More ways a write is refused or lost (re-audit, 3 Nov 2026) ---


POHA = {**DAL, "name": "Poha with peanuts", "ingredients": ["flattened rice", "peanut"],
        "allergen_tags": ["peanut"], "diet_tags": [], "calories": 300, "protein_g": 8,
        "carbs_g": 50, "fat_g": 9}
PEANUT = {**KNEE, "condition_ids": [], "allergen_tags": ["peanut"]}


@pytest.mark.parametrize(("profile", "tool", "args", "warning", "attributes"), [
    (PEANUT, "log_meal", {"meal": "breakfast", "foods": [POHA]},
     "Poha with peanuts: contains peanut, which is in your allergies", ["peanut"]),
    ({**KNEE, "condition_ids": [], "diet_tags": ["vegan"]}, "log_meal",
     {"meal": "dinner", "foods": [{**DAL, "name": "Paneer tikka", "ingredients": ["paneer"],
                                   "allergen_tags": ["milk"], "diet_tags": []}]},
     "Paneer tikka: contains an animal product", ["animal_product"]),
    ({**KNEE, "condition_ids": ["asthma"]}, "log_practice",
     {"catalogue_id": "box_breathing", "duration_min": 5, "mood_before": None,
      "mood_after": None, "note": ""},
     "Box breathing: breath-holding with a heart condition or asthma", []),
])
async def test_each_kind_of_conflict_is_held_with_its_warning(store, async_engine, profile,
                                                              tool, args, warning, attributes):
    agent = "nutrition" if tool == "log_meal" else "mental"
    reply = _lunch("Noted.") if agent == "nutrition" else _result(MentalReply(
        kind="log_ack", summary="Noted.", items=[], notes=[], source_ids=[], follow_up=None,
        risk_flag=False))
    models = Models(router=[_route(agent)], **{agent: [_calls((tool, args)), reply]})
    events = _events(await _post(_writes_app(store, async_engine, models), await guest(store),
                                 _payload("log it", guest_profile=profile)))
    await _settled()
    assert models.fakes[agent].calls[1].messages[-1].output["status"] == "held"
    [pending] = [d for n, d in events if n == "pending_write"]
    assert (pending["warnings"], pending["attributes"]) == ([warning], attributes)
    assert "committed" not in _names(events)


async def _held_poha(store, async_engine):
    """An account with a peanut allergy logs poha with peanuts: held, not saved."""
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO user_preferences (user_id, dietary_restrictions) "
              "VALUES (:u, 'peanut allergy')", u=me.user_id)
    models = Models(router=[_route("nutrition")], nutrition=[
        _calls(("log_meal", {"meal": "breakfast", "foods": [POHA, RICE]})), _lunch()])
    app = _writes_app(store, async_engine, models)
    events = _events(await _post(app, me, _payload("log my poha breakfast")))
    await _settled()
    [pending] = [d for n, d in events if n == "pending_write"]
    assert await _count(async_engine, "nutrition_logs") == 0
    return app, me, pending


async def test_picked_out_peanuts_are_logged_as_left_out(store, async_engine):
    app, me, pending = await _held_poha(store, async_engine)
    assert pending["attributes"] == ["peanut"]
    response = await _confirm(app, me, pending["write_id"], {"left_out": ["peanut"]})
    assert response.status_code == 200
    assert response.json()["writes"][0]["warnings"] == ["Poha with peanuts: left out peanut"]
    [(warnings,)] = await sql(async_engine, "SELECT warnings FROM nutrition_logs")
    assert warnings == [{"kind": "conflict", "item": "Poha with peanuts", "rule_id": "DI-ALG-01",
                         "attributes": ["peanut"],
                         "reason": "Contains an allergen in your profile", "left_out": True}]


async def test_a_conflict_eaten_anyway_is_logged_with_its_warning(store, async_engine):
    app, me, pending = await _held_poha(store, async_engine)
    response = await _confirm(app, me, pending["write_id"])  # no body: they ate it all
    assert response.json()["writes"][0]["warnings"] == [
        "Poha with peanuts: contains peanut, which is in your allergies"]
    [(warnings,)] = await sql(async_engine, "SELECT warnings FROM nutrition_logs")
    assert [w["left_out"] for w in warnings] == [False]


async def test_only_what_the_warning_names_can_be_left_out(store, async_engine):
    app, me, pending = await _held_poha(store, async_engine)
    response = await _confirm(app, me, pending["write_id"], {"left_out": ["gluten"]})
    assert response.status_code == 400
    # Nothing was decided: the entry still waits, and a right answer logs it
    assert (await sql(async_engine, "SELECT status FROM pending_writes")) == [("pending",)]
    assert (await _confirm(app, me, pending["write_id"],
                           {"left_out": ["peanut"]})).status_code == 200


async def test_a_clean_log_has_no_warnings_in_its_row(store, async_engine):
    me = await account(store, async_engine)
    models = Models(router=[_route("nutrition")], nutrition=[
        _calls(("log_meal", {"meal": "lunch", "foods": [DAL]})), _lunch()])
    await _post(_writes_app(store, async_engine, models), me, _payload("log my dal"))
    await _settled()
    assert await sql(async_engine, "SELECT warnings FROM nutrition_logs") == [(None,)]


async def test_unchecked_ingredients_are_recorded_but_ask_nothing(store, async_engine):
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO user_preferences (user_id, dietary_restrictions) "
              "VALUES (:u, 'peanut allergy')", u=me.user_id)
    zucchini = {**DAL, "name": "Zucchini fritters", "ingredients": ["zucchini"]}
    models = Models(router=[_route("nutrition")], nutrition=[
        _calls(("log_meal", {"meal": "lunch", "foods": [zucchini]})), _lunch()])
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("log my fritters")))
    await _settled()
    assert "pending_write" not in _names(events) and "committed" in _names(events)
    [(warnings,)] = await sql(async_engine, "SELECT warnings FROM nutrition_logs")
    assert [(w["kind"], w["attributes"]) for w in warnings] == [("unchecked", ["zucchini"])]


async def test_the_coach_sees_past_warnings(store, async_engine):
    app, me, pending = await _held_poha(store, async_engine)
    await _confirm(app, me, pending["write_id"], {"left_out": ["peanut"]})
    models = Models(router=[_route("nutrition")], nutrition=[
        _calls(("get_recent_logs", {"kind": "meal", "days": 2})), _lunch("Noted.")])
    await _post(_writes_app(store, async_engine, models), me, _payload("what did I eat?"))
    await _settled()
    [entry] = models.fakes["nutrition"].calls[1].messages[-1].output["entries"]
    assert entry["warnings"][0]["left_out"] is True


async def test_a_retry_that_logs_nothing_commits_nothing(store, async_engine):
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) "
              "VALUES (:u, :c)", u=me.user_id, c=KNEE_NOTE)
    # The first try logs and is blocked; the retry gives a safe plan and logs nothing
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", BRIDGES)), _physical("back_squat"), _physical("glute_bridge")])
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("a leg plan")))
    await _settled()
    assert ("step", "retry") in [(n, d["name"]) for n, d in events if n == "step"]
    assert "committed" not in _names(events)
    assert await _count(async_engine, "workout_logs") == 0


async def test_a_reconnect_sees_what_was_logged(store, async_engine):
    me = await account(store, async_engine)
    models = Models(router=[_route("physical")], physical=[
        _calls(("log_workout", BRIDGES)), _ack()])
    app = _writes_app(store, async_engine, models)
    rid = uuid.uuid4()
    live = _events(await _post(app, me, _payload("log 3x12 glute bridges", rid=rid)))
    await _settled()
    cfg = settings()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://testserver") as client:
        again = await client.get(f"/agents/chat/stream/{rid}?after=-1",
                                 cookies={cfg.session_cookie: me.raw_session_id})
    assert [e for e in _events(again) if e[0] == "committed"] == [
        e for e in live if e[0] == "committed"]


async def test_racing_confirms_log_once(store, async_engine):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me)
    answers = await asyncio.gather(*(_confirm(app, me, write_id) for _ in range(5)))
    assert {r.status_code for r in answers} == {200}
    assert len({r.text for r in answers}) == 1
    assert await _count(async_engine, "workout_logs") == 1


async def test_a_held_entry_that_no_longer_validates_is_discarded(store, async_engine):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me)
    # e.g. held before a schema change: the entry can't be checked, so it isn't saved
    await sql(async_engine, "UPDATE pending_writes SET payload = CAST(:p AS json)",
              p=json.dumps({"args": {**BRIDGES, "catalogue_id": "no_such_exercise"},
                            "warnings": []}))
    response = await _confirm(app, me, write_id)
    assert response.status_code == 409 and "no longer be checked" in response.json()["message"]
    assert await _count(async_engine, "workout_logs") == 0


# --- Macros in meal logs (owner, 3 Nov 2026, Part E #44) ---


async def test_a_logged_meal_keeps_its_macros_and_the_coach_can_read_them(store,
                                                                         async_engine):
    me = await account(store, async_engine)
    meal = {"meal": "lunch", "foods": [DAL, RICE]}
    models = Models(router=[_route("nutrition"), _route("nutrition")], nutrition=[
        _calls(("log_meal", meal)), _lunch(),
        _calls(("get_recent_logs", {"kind": "meal", "days": 1})), _lunch("About 16 g.")])
    app = _writes_app(store, async_engine, models)
    events = _events(await _post(app, me, _payload("log my lunch: dal and rice")))
    await _settled()
    [committed] = [d["writes"] for n, d in events if n == "committed"]
    assert _line(committed[0]) == ("Logged: Lunch: Dal, Rice · 430 kcal · "
                                   "protein 16 g, carbs 80 g, fat 6 g")
    [(calories, macros, foods)] = await sql(async_engine, "SELECT calories, macros, foods "
                                            "FROM nutrition_logs")
    assert calories == 430
    assert json.loads(macros) == {"protein_g": 16.0, "carbs_g": 80.0, "fat_g": 5.5,
                                  "complete": True}
    assert [f["protein_g"] for f in json.loads(foods)] == [12, 4]
    # The next turn: "how much protein today?" reads the totals
    await _post(app, me, _payload("how much protein have I had today?"))
    await _settled()
    entries = models.fakes["nutrition"].calls[3].messages[-1].output["entries"]
    assert json.loads(entries[0]["macros"])["protein_g"] == 16.0


async def test_unknown_macros_are_stored_as_unknown_and_never_shown_short(store,
                                                                         async_engine):
    me = await account(store, async_engine)
    meal = {"meal": "lunch", "foods": [DAL, {**RICE, "protein_g": None, "calories": None}]}
    models = Models(router=[_route("nutrition")], nutrition=[_calls(("log_meal", meal)),
                                                             _lunch()])
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("log my lunch")))
    await _settled()
    [committed] = [d["writes"] for n, d in events if n == "committed"]
    # Only totals every food gave: carbs and fat, not calories or protein
    assert _line(committed[0]) == "Logged: Lunch: Dal, Rice · carbs 80 g, fat 6 g"
    [(calories, macros)] = await sql(async_engine, "SELECT calories, macros FROM nutrition_logs")
    assert calories == 230  # the known part, marked incomplete
    assert json.loads(macros) == {"protein_g": 12.0, "carbs_g": 80.0, "fat_g": 5.5,
                                  "complete": False}


async def test_impossible_macros_go_back_to_the_coach_to_correct(store, async_engine):
    me = await account(store, async_engine)
    bad = {"meal": "lunch", "foods": [{**DAL, "protein_g": 60, "carbs_g": 80, "fat_g": 30}]}
    models = Models(router=[_route("nutrition")], nutrition=[
        _calls(("log_meal", bad)), _calls(("log_meal", {"meal": "lunch", "foods": [DAL]})),
        _lunch()])
    events = _events(await _post(_writes_app(store, async_engine, models), me,
                                 _payload("log my dal")))
    await _settled()
    told = models.fakes["nutrition"].calls[1].messages[-1].output
    assert told["status"] == "invalid_arguments"
    assert "more than the 230 kcal stated" in told["errors"][0]
    [committed] = [d["writes"] for n, d in events if n == "committed"]
    assert len(committed) == 1  # the corrected call, once
    assert await _count(async_engine, "nutrition_logs") == 1


async def test_a_confirmed_meal_keeps_its_macros(store, async_engine):
    me = await account(store, async_engine)
    models = _with_search(Models(router=[_route("nutrition")], nutrition=[
        _calls(("web_search", {"query": "dal protein"}),
               ("log_meal", {"meal": "lunch", "foods": [DAL]})), _lunch()]))
    app = _writes_app(store, async_engine, models)
    events = _events(await _post(app, me, _payload("is dal good protein? log my bowl")))
    await _settled()
    [pending] = [d for n, d in events if n == "pending_write"]
    assert pending["summary"] == "Lunch: Dal · 230 kcal · protein 12 g, carbs 35 g, fat 5 g"
    assert (await _confirm(app, me, pending["write_id"])).status_code == 200
    [(macros,)] = await sql(async_engine, "SELECT macros FROM nutrition_logs")
    assert json.loads(macros)["protein_g"] == 12.0


async def test_a_guests_entry_carries_its_macros(store, async_engine):
    models = Models(router=[_route("nutrition")], nutrition=[
        _calls(("log_meal", {"meal": "lunch", "foods": [DAL]})), _lunch()])
    events = _events(await _post(_writes_app(store, async_engine, models), await guest(store),
                                 _payload("log my dal")))
    await _settled()
    [committed] = [d["writes"] for n, d in events if n == "committed"]
    assert committed[0]["entry"]["args"]["foods"][0]["fat_g"] == 5


@pytest.mark.parametrize(("food", "ok"), [
    (DAL, True),
    ({**DAL, "name": "Lager", "calories": 430, "protein_g": 4, "carbs_g": 36, "fat_g": 0},
     True),  # alcohol: far fewer kcal from macros than stated, measured live
    ({**DAL, "calories": 230, "protein_g": 14, "carbs_g": 44, "fat_g": 7}, True),  # +22%
    ({**DAL, "calories": 100, "protein_g": 10, "carbs_g": 30, "fat_g": 10}, False),
    ({**DAL, "protein_g": -1}, False),
    ({**DAL, "carbs_g": 501}, False),
    ({**DAL, "calories": None}, True),  # nothing to compare with
])
def test_macros_are_checked_against_the_calories(food, ok):
    from pydantic import ValidationError
    try:
        LogMealArgs(meal="lunch", foods=[food])
    except ValidationError:
        assert not ok
    else:
        assert ok
