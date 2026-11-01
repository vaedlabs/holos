"""The composer (Plan C.5): each sample stream in contracts/streams is what the composer
sends for that situation (golden files); only gated text is sent; one terminal event;
sections never interleave; the trace shown to the person stays under 32 KB."""

import asyncio
import json
from datetime import UTC, datetime

import pytest

from app.agents.schemas import (
    AgentResult,
    Decision,
    ExerciseItem,
    FoodItem,
    HistoryTurn,
    LogMealArgs,
    LogWorkoutArgs,
    MentalReply,
    NutritionReply,
    PhysicalReply,
    PracticeItem,
    Source,
    StagedWrite,
    TraceView,
    Usage,
    UserProfile,
)
from app.contracts import generate
from app.observability.tracer import Trace
from app.orchestration import composer as composer_module
from app.orchestration.composer import (
    TRACE_VIEW_MAX,
    Composer,
    Gated,
    StreamEnded,
    gated,
    history_turn,
    trace_view,
    turn_text,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

STREAMS = generate.CONTRACTS_DIR / "streams"
KNEE = UserProfile(condition_ids=["knee_ligament_injury"], allergen_tags=[], diet_tags=[],
                   notes="")


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[int, str, dict]] = []
        self.finals: list[bool] = []

    async def emit(self, events, final):
        self.events += events
        self.finals.append(final)

    def lines(self) -> list[dict]:
        return [{"event": name, "data": data} for _, name, data in self.events]


def _sample(name: str) -> list[dict]:
    return [json.loads(line) for line in (STREAMS / f"{name}.jsonl").read_text().splitlines()]


def _done_inputs(sample: list[dict]) -> tuple[TraceView, Usage, HistoryTurn | None]:
    data = sample[-1]["data"]
    turn = HistoryTurn(**data["turn"]) if "turn" in data else None
    return TraceView(**data["trace"]), Usage(**data["usage"]), turn


def _reply(model, kind="plan", summary="", items=(), notes=(), follow_up=None):
    return model(kind=kind, summary=summary, items=list(items), notes=list(notes),
                 source_ids=[], follow_up=follow_up, risk_flag=False)


def _exercise(cid, sets=None, reps=None, duration_s=None, intensity="moderate", note=""):
    return ExerciseItem(day=None, catalogue_id=cid, sets=sets, reps=reps,
                        duration_s=duration_s, intensity=intensity, note=note)


def _food(name, ingredients, portion, calories, note="", diet=()):
    return FoodItem(day=None, name=name, ingredients=ingredients, allergen_tags=[],
                    diet_tags=list(diet), portion=portion, calories=calories, note=note)


KNEE_BLOCK = Decision(action="block", rule_id="EX-KNEE-01", rules_version=4,
                      reason="High knee load with a knee ligament injury",
                      offending_items=["Back squat"])


# --- Golden streams: each sample, rebuilt from its situation ---


async def _plan_single(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.step("admitted")
    await c.step("routed", "physical", "physical")
    await c.step("agent_started", "physical")
    trace.step("tool_call", "physical", "staged", "log_workout")
    trace.step("gate", "physical", "allow")
    await c.step("composing")
    await c.section("physical", AgentResult(reply=_reply(
        PhysicalReply, summary="A 25-minute upper-body session that keeps your knees out of it.",
        items=[_exercise("push_up", 3, 10, note="Knees down if form slips"),
               _exercise("seated_cable_row", 3, 12, note="Squeeze shoulder blades"),
               _exercise("plank", 3, None, 30, "low", "Keep hips level")])))
    walk = LogWorkoutArgs(catalogue_id="brisk_walking", sets=None, reps=None,
                          duration_s=1800, note="")
    await c.committed([(StagedWrite(kind="workout", args=walk), "w_81f2")])


async def _holistic(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.step("admitted")
    await c.step("routed", detail="physical, nutrition, mental")
    for agent in ("physical", "nutrition", "mental"):
        await c.step("agent_started", agent)
    await c.step("composing")
    await c.section("physical", AgentResult(reply=_reply(PhysicalReply, items=[
        _exercise("brisk_walking", duration_s=1800, note="Daily, after dinner")])))
    await c.section("nutrition", AgentResult(reply=_reply(NutritionReply, items=[
        _food("Moong dal chilla", ["moong dal", "spinach", "cumin"], "2 chillas", 280,
              "Add curd if you eat dairy", ["vegan", "vegetarian", "jain"])])))
    await c.section("mental", AgentResult(reply=_reply(MentalReply, items=[
        PracticeItem(day=None, catalogue_id="coherent_breathing", duration_min=5,
                     note="Before bed")])))
    await c.summary(gated("Walk after dinner, keep breakfast high in protein, and wind "
                          "down with slow breathing.", KNEE))


async def _blocked_and_retried(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.step("admitted")
    await c.step("routed", "physical", "physical")
    await c.step("agent_started", "physical")
    trace.step("gate", "physical", "block")
    trace.step("retry", "physical", detail="blocked")
    trace.step("gate", "physical", "block")
    await c.step("composing")
    await c.section("physical", AgentResult(
        reply=_reply(PhysicalReply, items=[
            _exercise("leg_curl", 3, 12, intensity="low", note="Slow and controlled"),
            _exercise("glute_bridge", 3, 15, intensity="low", note="Pause at the top")]),
        removed_count=1, decisions=[KNEE_BLOCK],
        warnings=["1 item removed for your safety: High knee load with a knee ligament "
                  "injury"]))


async def _pending_write(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.step("admitted")
    await c.step("routed", "nutrition", "nutrition")
    await c.step("agent_started", "nutrition")
    trace.step("tool_call", "nutrition", "ok", "web_search")
    trace.step("tool_call", "nutrition", "staged", "log_meal")
    trace.step("gate", "nutrition", "allow")
    await c.step("composing")
    await c.section("nutrition", AgentResult(
        reply=_reply(NutritionReply, kind="log_ack", summary="Poha with peanuts is about "
                     "350 kcal. Confirm below to add it to your log."),
        sources=[Source(id="s1", title="Protein in common Indian breakfasts",
                        url="https://example.org/protein")]))
    poha = _food("Poha with peanuts", ["flattened rice", "peanut", "onion"], "1 plate", 350)
    await c.pending_write(StagedWrite(kind="meal", args=LogMealArgs(meal="breakfast",
                                                                    foods=[poha])),
                          write_id="pw_3c9a",
                          expires_at=datetime(2026, 10, 25, 9, 45, tzinfo=UTC))


async def _crisis(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.crisis()


async def _cap_reached(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.notice("cap_reached")


async def _search_off(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.step("admitted")
    await c.step("routed", "mental", "mental")
    await c.step("agent_started", "mental")
    trace.step("tool_call", "mental", "search_unavailable", "web_search")
    await c.step("composing")
    await c.notice("search_off")
    await c.section("mental", AgentResult(reply=_reply(
        MentalReply, kind="answer", summary="Slow breathing with a longer exhale can calm "
        "the body within a few minutes.")))


async def _error_mid_stream(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.step("admitted")
    await c.step("routed", "physical", "physical")
    await c.step("agent_started", "physical")
    await c.error("unavailable")


async def _coach_failed(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.step("admitted")
    await c.step("routed", detail="physical, nutrition")
    await c.step("agent_started", "physical")
    await c.step("agent_started", "nutrition")
    await c.step("composing")
    await c.section("physical", AgentResult(reply=_reply(PhysicalReply, items=[
        _exercise("brisk_walking", duration_s=1200, intensity="low", note="Easy pace")])))
    await c.section("nutrition", AgentResult(reply=None, error="unavailable"))


async def _own_reply(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.step("admitted")
    await c.step("routed", detail="greeting")
    await c.reply(gated("Good morning, Riya! How did yesterday's revision go?", KNEE))


async def _risk_flag(c: Composer, trace: Trace) -> None:
    await c.accepted(1)
    await c.step("admitted")
    await c.step("routed", "mental", "mental")
    await c.step("agent_started", "mental")
    await c.step("composing")
    reply = _reply(MentalReply, kind="answer", summary="I'm really glad you told me. You "
                   "don't have to carry this alone.")
    await c.section("mental", AgentResult(reply=reply.model_copy(update={"risk_flag": True})))
    await c.helplines(full=True)


SCENARIOS = {
    "plan_single": ("account", _plan_single), "holistic": ("guest", _holistic),
    "blocked_and_retried": ("account", _blocked_and_retried),
    "pending_write": ("account", _pending_write), "crisis": ("guest", _crisis),
    "cap_reached": ("guest", _cap_reached), "search_off": ("account", _search_off),
    "error_mid_stream": ("account", _error_mid_stream),
    "coach_failed": ("account", _coach_failed), "own_reply": ("guest", _own_reply),
    "risk_flag": ("account", _risk_flag),
}


def test_every_sample_stream_has_a_scenario():
    assert {p.stem for p in STREAMS.glob("*.jsonl")} == set(SCENARIOS)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_the_composer_sends_the_sample_stream(name):
    sample = _sample(name)
    mode, scenario = SCENARIOS[name]
    sink = Recorder()
    c = Composer(sample[0]["data"]["trace_id"], mode, sink)
    trace = Trace(c.trace_id, listener=c.on_trace_step)
    await scenario(c, trace)
    if not c.ended:
        await c.done(*_done_inputs(sample))
    assert sink.lines() == sample


# --- Only gated text ---


async def test_text_takes_gated_text_only():
    c = Composer("t", "guest", Recorder())
    with pytest.raises(TypeError):
        await c.reply("Try back squats.")  # type: ignore[arg-type]


async def test_a_blocked_sentence_never_reaches_the_stream():
    sink = Recorder()
    c = Composer("t", "guest", sink)
    await c.summary(gated("Do back squats daily. Walk after dinner.", KNEE))
    assert sink.events[0][2]["chunk"] == "Walk after dinner."
    await c.reply(gated("Back squats are the best move for you.", KNEE))
    assert len(sink.events) == 1  # nothing safe left, nothing sent


# --- One terminal event, sections whole ---


async def test_nothing_is_sent_after_the_terminal_event():
    sink = Recorder()
    c = Composer("t", "account", sink)
    await c.error("busy")
    with pytest.raises(StreamEnded):
        await c.step("composing")
    with pytest.raises(StreamEnded):
        await c.error("unavailable")
    assert sink.finals == [True] and [e[1] for e in sink.events] == ["error"]


async def test_concurrent_sections_never_interleave_and_seq_follows_order():
    sink = Recorder()

    class Slow(Recorder):
        async def emit(self, events, final):
            await asyncio.sleep(0.01)  # a slow database: the other coach waits
            await sink.emit(events, final)

    c = Composer("t", "guest", Slow())
    walk = AgentResult(reply=_reply(PhysicalReply, summary="Walk.", items=[
        _exercise("walking", duration_s=600)]))
    calm = AgentResult(reply=_reply(MentalReply, summary="Breathe.", items=[
        PracticeItem(day=None, catalogue_id="box_breathing", duration_min=5, note="")]))
    await asyncio.gather(c.section("physical", walk), c.section("mental", calm))
    agents = [e[2]["agent"] for e in sink.events]
    assert agents in (["physical"] * 4 + ["mental"] * 4, ["mental"] * 4 + ["physical"] * 4)
    assert [e[0] for e in sink.events] == list(range(8))


async def test_trace_steps_reported_late_still_go_before_the_end():
    sink = Recorder()
    c = Composer("t", "account", sink)
    trace = Trace("t", listener=c.on_trace_step)
    trace.step("gate", "physical", "warn")
    trace.step("retry", "physical", detail="blocked")
    await c.error("unavailable")
    assert [(e[1], e[2].get("name")) for e in sink.events] == [
        ("step", "gate"), ("step", "retry"), ("error", None)]


async def test_a_section_shows_follow_up_notes_caveats_and_warnings_in_order():
    sink = Recorder()
    c = Composer("t", "guest", sink)
    reply = _reply(PhysicalReply, kind="clarify", summary="Happy to help.",
                   follow_up="How many days a week can you train?",
                   items=[], notes=["Warm up first."])
    await c.section("physical", AgentResult(reply=reply, warnings=["x" * 500]))
    assert [(e[1], e[2].get("chunk")) for e in sink.events] == [
        ("section_start", None), ("text", "Happy to help."),
        ("text", "How many days a week can you train?"), ("text", "Warm up first."),
        ("section_end", None)]
    assert sink.events[-1][2]["warnings"] == ["x" * 400]
    sink.events.clear()
    item = _exercise("plank", 3, None, 30)
    await c.section("physical", AgentResult(reply=_reply(PhysicalReply, items=[item]),
                                            item_caveats=[["Keep your back flat"]]))
    assert sink.events[1][2]["caveats"] == ["Keep your back flat"]
    assert sink.events[1][2]["display"] == "Plank: 3 x 30 s"


async def test_still_working_after_eight_quiet_seconds(monkeypatch):
    monkeypatch.setattr(composer_module, "STILL_WORKING_S", 0.05)
    sink = Recorder()
    c = Composer("t", "guest", sink)
    await c.accepted(1)
    watcher = asyncio.create_task(c.still_working())
    await asyncio.sleep(0.08)
    assert [e[2].get("name") for e in sink.events] == [None, "still_working"]
    await c.step("composing")  # an event resets the wait
    await asyncio.sleep(0.03)
    assert len(sink.events) == 3
    await c.error("busy")
    await asyncio.wait_for(watcher, 1)  # it stops at the end


# --- Writes, helplines ---


async def test_a_committed_hold_under_a_minute_reads_in_seconds():
    sink = Recorder()
    c = Composer("t", "guest", sink)
    hold = LogWorkoutArgs(catalogue_id="plank", sets=3, reps=None, duration_s=30, note="")
    await c.committed([(StagedWrite(kind="workout", args=hold), None)])
    write = sink.events[0][2]["writes"][0]
    assert write["summary"] == "Logged: Plank: 3 x 30 s"  # was "Plank: 0 min"
    assert write["entry"]["args"]["catalogue_id"] == "plank" and write["write_id"] is None


async def test_the_crisis_reminder_is_the_short_signed_off_line():
    sink = Recorder()
    await Composer("t", "guest", sink).helplines(full=False)
    assert sink.events[0][2]["text"].startswith("If things feel heavy")
    assert len(sink.events[0][2]["helplines"]) == 3


# --- What the person sees of the trace, and the history turn ---


async def test_the_trace_view_stays_under_32_kb():
    trace = Trace("t")
    for i in range(3000):
        trace.step("tool_call", "nutrition", "ok", f"web_search_{i}")
        trace.step("gate", "nutrition", "warn")
        trace.attempt("nutrition", "openai", "gpt-6-luna", "first")
    decisions = [KNEE_BLOCK] * 400
    view = trace_view(trace, "coaching", ["nutrition"], decisions, [],
                      Usage(tokens_in=1, tokens_out=1, cost_usd=0.0))
    assert len(view.model_dump_json()) <= TRACE_VIEW_MAX
    assert view.decisions  # shortened last


async def test_the_trace_view_keeps_steps_calls_and_tools_but_no_text():
    trace = Trace("t")
    trace.step("tool_call", "nutrition", "search_unavailable", "web_search")
    trace.step("retry", "physical", detail="blocked")
    trace.end(trace.attempt("meal_photo", "openai", "m", "first"))
    view = trace_view(trace, "coaching", ["nutrition"], [], [],
                      Usage(tokens_in=1, tokens_out=1, cost_usd=0.0))
    assert [(t.name, t.args, t.status) for t in view.tools] == [
        ("web_search", "", "unavailable")]
    assert view.retries == 1
    assert ("call_first", "nutrition") in [(s.name, s.agent) for s in view.steps]


async def test_the_holistic_sample_turn_is_what_the_person_saw():
    sink = Recorder()
    c = Composer("t", "guest", sink)
    results: list[AgentResult] = []

    async def keep(agent, result):
        results.append(result)

    c.section = keep  # type: ignore[method-assign]
    summaries: list[Gated] = []

    async def summary(text):
        summaries.append(text)

    c.summary = summary  # type: ignore[method-assign]
    await _holistic(c, Trace("t"))
    turn = _sample("holistic")[-1]["data"]["turn"]["content"]
    assert turn_text(summary=summaries[0], results=results) == turn


def test_the_history_turn_holds_what_the_person_saw():
    week = AgentResult(reply=_reply(PhysicalReply, summary="Your week.", items=[
        _exercise("glute_bridge", 2, 10).model_copy(update={"day": "Mon"})]))
    text = turn_text(summary=Gated("Move, eat, rest."), results=[week])
    assert text == "Move, eat, rest.\nYour week.\n1. Mon: Glute bridge: 2 x 10"
    assert turn_text(own=Gated("Hello!")) == "Hello!"
    many = AgentResult(reply=_reply(PhysicalReply, summary="s", items=[
        _exercise("walking", duration_s=600, note="")] * 30))
    assert len(turn_text(results=[many] * 3)) <= 2000
    assert history_turn("Hello!", []).agents is None


# --- A real coach's result through the composer (P4.5 output, P4.6 input) ---


async def test_a_real_coachs_blocked_retry_reaches_the_stream_in_order():
    from app.agents.physical import PhysicalAgent
    from tests.unit.agents.test_base import _agent, _physical, _result, _run

    sink = Recorder()
    c = Composer("t", "guest", sink)
    trace = Trace("t", listener=c.on_trace_step)
    # The first reply gives squats to a knee injury; the retry still keeps one blocked
    agent, _ = _agent(PhysicalAgent, _result(_physical("back_squat")),
                      _result(_physical("back_squat", "glute_bridge")))
    await c.step("agent_started", "physical")
    result = await agent.run(_run(trace=trace))
    await c.section("physical", result)
    await c.error("busy")  # any end: the progress must already be out
    names = [(e[1], e[2].get("name") or e[2].get("chunk") or e[2].get("display"))
             for e in sink.events]
    assert names == [
        ("step", "agent_started"), ("step", "gate"), ("step", "retry"), ("step", "gate"),
        ("section_start", None), ("text", "Here is your plan."),
        ("item", "Glute bridge: 2 x 10"), ("section_end", None), ("error", None)]
    end = sink.events[-2][2]
    assert end["removed_count"] == 1 and end["decisions"][0]["rule_id"].startswith("EX-KNEE")
    assert end["warnings"][0].startswith("1 item removed for your safety")
    assert "back_squat" not in json.dumps([e[2] for e in sink.events[:-1]])
