"""Traces and gate decisions written after the response (Plan P4.10, C.2 stage 15): one
trace per request with its decisions; an honest success flag; a crisis trace holds no
message text; the writer never delays `done`."""

import asyncio
import time

import pytest
import pytest_asyncio

from app import main
from app.agents.schemas import Decision
from app.data.state_store import StateStore
from app.observability import background
from app.observability.tracer import Trace
from app.orchestration import worker
from app.providers.fake import Slow
from app.providers import BadRequest

from .test_admission import account, guest, sql
from .test_chat import (
    KNEE_NOTE,
    Models,
    _app,
    _events,
    _mental,
    _payload,
    _physical,
    _post,
    _route,
    _settled,
    requests_finish,  # noqa: F401  (autouse)
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


async def _written():
    await _settled()
    await background.settled()


async def test_a_request_writes_one_trace_and_its_decisions(store, async_engine):
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) "
              "VALUES (:u, :c)", u=me.user_id, c=KNEE_NOTE)
    models = Models(router=[_route("physical")],
                    physical=[_physical("back_squat"), _physical("glute_bridge")])
    events = _events(await _post(_app(store, async_engine, models), me, _payload()))
    await _written()
    trace_id = events[-1][1]["trace_id"]
    [(route, success, user_id, steps, usage)] = await sql(
        async_engine, "SELECT route, success, user_id, steps, usage FROM traces")
    assert (route, success, user_id) == ("coaching", True, me.user_id)
    assert {"coach", "gate", "retry"} <= {s["name"] for s in steps["steps"]}
    assert [a["call"] for a in steps["attempts"]] == ["router", "physical", "physical"]
    assert usage["tokens_in"] == events[-1][1]["usage"]["tokens_in"]
    decisions = await sql(async_engine, "SELECT trace_id, user_id, rule_id, action, item "
                          "FROM gate_decisions")
    assert ("EX-KNEE-01", "block", "Back squat") in [(r[2], r[3], r[4]) for r in decisions]
    assert {(r[0], r[1]) for r in decisions} == {(trace_id, me.user_id)}


async def test_each_offending_item_is_a_row(async_engine):
    many = Decision(action="block", rule_id="DI-NUT-01", rules_version=1, reason="nuts",
                    offending_items=["Peanuts", "x" * 300])
    clean = Decision(action="allow", rule_id="EX-ANY", rules_version=1, reason="ok")
    await background.write(async_engine, background.Outcome(
        Trace("t-items"), None, None, decisions=[many, clean]))
    rows = await sql(async_engine, "SELECT rule_id, item FROM gate_decisions ORDER BY id")
    assert rows == [("DI-NUT-01", "Peanuts"), ("DI-NUT-01", "x" * background.ITEM_MAX),
                    ("EX-ANY", None)]


async def test_a_failed_request_is_not_a_success(store, async_engine):
    models = Models(router=[_route("physical")],
                    physical=[BadRequest("no", "openai"), BadRequest("no", "openai")])
    await _post(_app(store, async_engine, models), await guest(store), _payload())
    await _written()
    [(success, user_id, session_hash)] = await sql(
        async_engine, "SELECT success, user_id, session_id_hash FROM traces")
    assert success is False and user_id is None and session_hash


async def test_a_partial_answer_is_not_a_success(store, async_engine):
    models = Models(router=[_route("physical", "mental")], physical=[_physical("glute_bridge")],
                    mental=[BadRequest("no", "openai"), BadRequest("no", "openai")])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("a workout and help with stress")))
    await _written()
    assert events[-1][0] == "done"  # the person got an answer, but not the whole one
    assert await sql(async_engine, "SELECT success FROM traces") == [(False,)]


async def test_a_request_past_its_hard_limit_is_not_a_success(store, async_engine,
                                                              monkeypatch):
    monkeypatch.setattr(worker, "HARD_LIMIT_S", 0.3)
    models = Models(router=[_route("physical")], physical=[Slow(5, _physical("glute_bridge"))])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload()))
    await _written()
    assert events[-1][0] == "error"
    assert await sql(async_engine, "SELECT success FROM traces") == [(False,)]


async def test_a_restart_waits_for_trace_writes(async_engine, monkeypatch):
    real = background.write

    async def slow(engine, outcome):
        await asyncio.sleep(0.3)
        await real(engine, outcome)

    monkeypatch.setattr(background, "write", slow)
    background.record(async_engine, background.Outcome(Trace("t-restart"), None, None))
    try:
        await main.finish_running_requests()
    finally:
        worker._reset_for_tests()
    assert await sql(async_engine, "SELECT trace_id FROM traces") == [("t-restart",)]


async def test_holos_own_reply_is_a_success(store, async_engine):
    models = Models(router=[_route(kind="greeting", reply="Hi!")])
    await _post(_app(store, async_engine, models), await guest(store), _payload("hi"))
    await _written()
    assert await sql(async_engine, "SELECT route, success FROM traces") == [("greeting", True)]


async def test_a_crisis_trace_has_no_message_text(store, async_engine):
    message = "i want to kill myself tonight"
    me = await guest(store)
    await _post(_app(store, async_engine, Models()), me, _payload(message))
    await background.settled()
    [(route, steps, success)] = await sql(async_engine,
                                          "SELECT route, steps, success FROM traces")
    assert route == "crisis" and success is True
    assert [s["name"] for s in steps["steps"]] == ["crisis"]
    assert steps["steps"][0]["detail"]  # the rule that matched
    everything = str(await sql(async_engine, "SELECT * FROM traces"))
    assert "kill" not in everything and "tonight" not in everything


async def test_the_writer_doesnt_delay_done(store, async_engine, monkeypatch):
    real = background.write

    async def slow(engine, outcome):
        await asyncio.sleep(1)
        await real(engine, outcome)

    monkeypatch.setattr(background, "write", slow)
    models = Models(router=[_route("mental")], mental=[_mental()])
    began = time.monotonic()
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("stress")))
    await _settled()
    assert events[-1][0] == "done" and time.monotonic() - began < 0.9
    assert await sql(async_engine, "SELECT count(*) FROM traces") == [(0,)]  # not yet
    await background.settled()
    assert await sql(async_engine, "SELECT count(*) FROM traces") == [(1,)]


async def test_a_failed_write_never_fails_the_request(store, async_engine, monkeypatch,
                                                      caplog):
    async def broken(engine, outcome):
        raise RuntimeError("db down")

    monkeypatch.setattr(background, "write", broken)
    models = Models(router=[_route("mental")], mental=[_mental()])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("stress")))
    await _written()
    assert events[-1][0] == "done"
    assert "trace not stored" in caplog.text
