"""BaseAgent and the three coaches (Plan C.10, P4.5), on the FakeProvider through the real
ResilientProvider, gate and tools."""

import asyncio
import logging
import time

import pytest

from app.agents.base import (
    LOG_RETRY,
    UNSAFE_FALLBACK,
    AgentRun,
)
from app.agents.display import history_text
from app.agents.mental import MentalAgent
from app.agents.nutrition import NutritionAgent
from app.agents.physical import PhysicalAgent
from app.agents.schemas import (
    ExerciseItem,
    FoodItem,
    MentalReply,
    NutritionReply,
    PhysicalReply,
    PracticeItem,
    Source,
    UserProfile,
    WebSearchArgs,
)
from app.agents.tools import Tool, ToolContext
from app.config.limits import TOOL_ROUNDS
from app.guardrails.gate import PHOTO_CAVEAT
from app.observability import Trace
from app.providers import (
    BadRequest,
    Breakers,
    FakeProvider,
    ImageInput,
    LLMResult,
    OverBudget,
    ProviderUnavailable,
    ResilientProvider,
    Route,
    ToolCall,
    ToolResult,
    Usage,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

KNEE = UserProfile(condition_ids=["knee_ligament_injury"], allergen_tags=[], diet_tags=[],
                   notes="")
GLUTEN = UserProfile(condition_ids=[], allergen_tags=["gluten"], diet_tags=["vegetarian"],
                     notes="")
NONE = UserProfile(condition_ids=[], allergen_tags=[], diet_tags=[], notes="")


def _agent(cls, *script, took: float = 0.0):
    """took: seconds each model call takes on the agent's clock (none really pass)."""
    fake = FakeProvider(list(script), name="openai")
    llm = ResilientProvider(Route(fake, cls.options()), None, Breakers())
    passed = [0.0]
    generate = fake.generate

    async def timed(*args, **kwargs):
        passed[0] += took
        return await generate(*args, **kwargs)

    fake.generate = timed
    return cls(llm, clock=lambda: time.monotonic() + passed[0]), fake


def _run(message="a leg workout", profile=KNEE, left=60.0, images=(), ctx=None, trace=None):
    return AgentRun(message=message, profile=profile, history=[],
                    tools=ctx or ToolContext(mode="guest", trace_id="t"),
                    deadline=time.monotonic() + left, principal="p", images=images,
                    trace=trace)


def _steps(trace: Trace) -> list[tuple[str, str, str]]:
    return [(s.name, s.outcome, s.detail) for s in trace.steps]


def _result(parsed, **kw):
    return LLMResult(provider="openai", model="m", parsed=parsed,
                     text=parsed.model_dump_json() if parsed is not None else None,
                     usage=Usage(900, 300), **kw)


def _calls(*calls):
    return LLMResult(provider="openai", model="m", usage=Usage(900, 40),
                     tool_calls=tuple(ToolCall(f"c{i}", name, args)
                                      for i, (name, args) in enumerate(calls)))


def _ex(cid, note=""):
    return ExerciseItem(day=None, catalogue_id=cid, sets=2, reps=10, duration_s=None,
                        intensity="low", note=note)


def _physical(*cids, kind=None, summary="Here is your plan.", source_ids=()):
    return PhysicalReply(kind=kind or ("plan" if cids else "answer"), summary=summary,
                         items=[_ex(c) for c in cids], notes=[], source_ids=list(source_ids),
                         follow_up=None, risk_flag=False)


def _food(name, ingredients, allergens=()):
    return FoodItem(day=None, name=name, ingredients=ingredients, allergen_tags=list(allergens),
                    diet_tags=[], portion="1 plate", calories=400, note="")


def _logged(food):
    """A plan's food as a meal log's: with its macros (Part E #44)."""
    return {**food.model_dump(), "protein_g": 12, "carbs_g": 60, "fat_g": 8}


def _nutrition(*foods, kind=None, summary="Here you go."):
    return NutritionReply(kind=kind or ("plan" if foods else "answer"), summary=summary,
                          items=list(foods), notes=[], source_ids=[], follow_up=None,
                          risk_flag=False)


# --- The gate and the retry (C.10 steps 5-7) ---


async def test_a_valid_plan_passes():
    agent, fake = _agent(PhysicalAgent, _result(_physical("glute_bridge")))
    result = await agent.run(_run())
    assert [i.catalogue_id for i in result.reply.items] == ["glute_bridge"]
    assert result.warnings == [] and result.error is None and len(fake.calls) == 1


async def test_a_blocked_plan_retries_once_with_the_violations_in_the_prompt():
    agent, fake = _agent(PhysicalAgent, _result(_physical("back_squat")),
                         _result(_physical("glute_bridge")))
    trace = Trace("t")
    result = await agent.run(_run(trace=trace))
    assert [i.catalogue_id for i in result.reply.items] == ["glute_bridge"]
    correction = fake.calls[1].messages[-1].text
    assert "not allowed" in correction and "knee ligament injury" in correction.lower()
    assert "whole reply again" in correction and "keep every other item" in correction
    assert "Back squat" in correction
    assert _steps(trace) == [("gate", "block", ""), ("retry", "ok", "blocked"),
                             ("gate", "allow", ""), ("coach", "ok", "")]
    assert [(a.call, a.role, a.outcome) for a in trace.attempts] == [
        ("physical", "first", "ok"), ("physical", "first", "ok")]


async def test_a_retry_that_is_still_blocked_drops_the_items():
    both = _physical("back_squat", "glute_bridge")
    agent, fake = _agent(PhysicalAgent, _result(both), _result(both))
    result = await agent.run(_run())
    assert [i.catalogue_id for i in result.reply.items] == ["glute_bridge"]
    assert result.warnings[0].startswith("1 item removed for your safety: High knee load")
    assert len(fake.calls) == 2
    assert {d.rule_id for d in result.decisions} >= {"EX-KNEE-01"}


EXPLAINED = ("Deep knee bending and landing from a height put too much strain on your "
             "injured ligament, so I held back. Would gentle hip or core work help instead?")


async def test_all_items_dropped_the_coach_explains_in_its_own_words():
    explained = _physical("glute_bridge", kind="plan", summary=EXPLAINED)
    agent, fake = _agent(PhysicalAgent, _result(_physical("back_squat")),
                         _result(_physical("back_squat", "jump_squat")), _result(explained))
    trace = Trace("t")
    result = await agent.run(_run(trace=trace))
    # The coach is told what was removed and why, not given sentences to use
    note = fake.calls[2].messages[-1].text
    assert "Back squat" in note and "Jump squat" in note and "High knee load" in note
    assert fake.calls[2].tools is None
    # Its reply is the answer, without items even if it wrote some
    assert result.reply.summary == EXPLAINED and result.reply.items == []
    assert result.reply.kind == "answer" and result.error is None
    assert "removed for your safety" in result.warnings[0]
    assert ("explain", "ok", "") in _steps(trace)


async def test_the_explanation_is_gated_too():
    # It recommends a blocked exercise in prose: that sentence goes; nothing is left
    unsafe = _physical(summary="Try back squats instead.")
    agent, _ = _agent(PhysicalAgent, _result(_physical("back_squat")),
                      _result(_physical("back_squat")), _result(unsafe))
    trace = Trace("t")
    result = await agent.run(_run(trace=trace))
    assert result.reply.summary == UNSAFE_FALLBACK["physical"]
    assert ("explain", "fixed_reply", "") in _steps(trace)


async def test_a_failed_explanation_gives_the_fixed_reply():
    agent, _ = _agent(PhysicalAgent, _result(_physical("back_squat")),
                      _result(_physical("back_squat")), BadRequest("no", "openai"))
    trace = Trace("t")
    result = await agent.run(_run(trace=trace))
    assert result.reply.summary == UNSAFE_FALLBACK["physical"] and result.error is None
    assert trace.attempts[-1].outcome == "bad_request"


async def test_no_time_to_explain_gives_the_fixed_reply():
    # The first try took 5 of 9 s: no retry (5 x 1.35 + 0.5) and no explanation (p95 8.7
    # + 0.5)
    agent, fake = _agent(PhysicalAgent, _result(_physical("back_squat")), took=5.0)
    result = await agent.run(_run(left=9.0))
    assert len(fake.calls) == 1 and result.reply.summary == UNSAFE_FALLBACK["physical"]


async def test_the_explanation_needs_only_a_short_answers_time():
    # The first try took 10 of 22 s: no retry (10 x 1.35 + 0.5 = 14) but an
    # explanation, which has no items (p95 8.7 + 0.5)
    agent, fake = _agent(PhysicalAgent, _result(_physical("back_squat")),
                         _result(_physical(kind="answer", summary="That move loads the knee.")),
                         took=10.0)
    result = await agent.run(_run(left=22.0))
    assert len(fake.calls) == 2 and result.reply.summary == "That move loads the knee."


async def test_the_provider_retries_only_with_time_for_a_week_plan():
    # 12 s left: an outage retry would fit a short answer (8.7 + 0.5) but not a week
    # plan (16.3 + 0.5), so the call is given up rather than run into the deadline
    agent, fake = _agent(PhysicalAgent, ProviderUnavailable("down", "openai"),
                         _result(_physical("glute_bridge")))
    result = await agent.run(_run(left=12.0))
    assert len(fake.calls) == 1 and result.error == "unavailable"


async def test_a_retry_clears_the_staged_writes():
    log = ("log_workout", {"catalogue_id": "back_squat", "sets": 3, "reps": 5,
                           "duration_s": None, "note": ""})
    agent, _ = _agent(PhysicalAgent, _calls(log), _result(_physical("back_squat")),
                      _result(_physical("glute_bridge")))
    result = await agent.run(_run())
    assert result.staged_writes == []


async def test_a_long_first_try_needs_as_long_for_its_retry():
    # The first try took 20 of 45 s: 25 s left is more than any fixed figure (week plan
    # 16.3 + 0.5) but less than a retry of the same size (20 x 1.35 + 0.5 = 27.5), so the
    # blocked item is dropped
    agent, fake = _agent(PhysicalAgent, _result(_physical("back_squat", "glute_bridge")),
                         took=20.0)
    result = await agent.run(_run(left=45.0))
    assert len(fake.calls) == 1
    assert [i.catalogue_id for i in result.reply.items] == ["glute_bridge"]


async def test_a_quick_first_try_leaves_room_for_a_retry():
    # The first try took 2 of 8 s: 6 s left is enough for a retry of a short answer
    # (the floor, p50 3.3 x 1.35 + 0.5 = 5.0), though not for a week plan
    agent, fake = _agent(PhysicalAgent, _result(_physical("back_squat")),
                         _result(_physical("glute_bridge")), took=2.0)
    result = await agent.run(_run(left=8.0))
    assert len(fake.calls) == 2
    assert [i.catalogue_id for i in result.reply.items] == ["glute_bridge"]


async def test_a_try_that_failed_fast_still_needs_a_short_answers_time():
    # A garbled reply after 1 s of 5.5: 4.5 s left is under the floor (5.0), so no retry
    cut = LLMResult(provider="openai", model="m", parsed=None, truncated=True)
    agent, fake = _agent(PhysicalAgent, cut, took=1.0)
    result = await agent.run(_run(left=5.5))
    assert len(fake.calls) == 1 and result.error == "malformed"


async def test_the_deadline_reserve_skips_tool_rounds_when_time_is_short():
    # 20 s: room for one call, not a tool round (p95 8.7) plus the final reserve (a week
    # plan's 16.3 + 0.5)
    agent, fake = _agent(PhysicalAgent, _result(_physical("glute_bridge")))
    await agent.run(_run(left=20.0))
    assert fake.calls[0].tools is None
    agent, fake = _agent(PhysicalAgent, _result(_physical("glute_bridge")))
    await agent.run(_run(left=60.0))
    assert [t.name for t in fake.calls[0].tools] == ["get_recent_logs", "web_search",
                                                     "log_workout"]


async def test_an_unknown_catalogue_id_is_malformed_and_retried():
    bad = PhysicalReply.model_construct(
        kind="plan", summary="ok", notes=[], source_ids=[], follow_up=None, risk_flag=False,
        items=[ExerciseItem.model_construct(catalogue_id="moon_squat", sets=1, reps=1,
                                            duration_s=None, intensity="low", note="")])
    agent, fake = _agent(PhysicalAgent, _result(bad), _result(_physical("glute_bridge")))
    result = await agent.run(_run())
    assert len(fake.calls) == 2 and result.reply.items[0].catalogue_id == "glute_bridge"
    assert "Not a known catalogue item" in fake.calls[1].messages[-1].text


@pytest.mark.parametrize("bad", [
    LLMResult(provider="openai", model="m", parsed=None, truncated=True, usage=Usage(9, 2200)),
    LLMResult(provider="openai", model="m", parsed=None, text="{", usage=Usage(9, 9)),
])
async def test_a_cut_off_or_unparsed_reply_is_malformed_and_retried(bad):
    agent, fake = _agent(PhysicalAgent, bad, _result(_physical("glute_bridge")))
    result = await agent.run(_run())
    assert len(fake.calls) == 2 and result.reply.items[0].catalogue_id == "glute_bridge"


async def test_malformed_twice_gives_no_reply_and_its_cause():
    cut = LLMResult(provider="openai", model="m", parsed=None, truncated=True)
    agent, _ = _agent(PhysicalAgent, cut, cut)
    trace = Trace("t")
    result = await agent.run(_run(trace=trace))
    # No chat text: the app shows a status with Retry (Part E #38)
    assert result.reply is None and result.error == "malformed"
    assert _steps(trace) == [("retry", "ok", "truncated"), ("failed", "truncated", ""),
                             ("coach", "error", "")]


async def test_a_provider_failure_gives_no_reply_and_its_code():
    agent, _ = _agent(PhysicalAgent, OverBudget("no room"))
    trace = Trace("t")
    result = await agent.run(_run(trace=trace))
    assert result.reply is None and result.error == "cap_reached"
    assert ("failed", "over_budget", "") in _steps(trace)


async def test_a_bug_is_logged_and_ends_only_this_coach(caplog):
    def broken(call):
        raise KeyError("oops")

    agent, _ = _agent(PhysicalAgent, broken)
    trace = Trace("t-bug")
    with caplog.at_level(logging.ERROR):
        result = await agent.run(_run(trace=trace))
    assert result.reply is None and result.error == "unavailable"
    assert ("failed", "bug", "") in _steps(trace)
    assert trace.attempts[0].outcome == "bug"
    # Logged with the trace ID and the stack, once by the call and once by the coach
    logged = [r for r in caplog.records if "t-bug" in r.getMessage()]
    assert len(logged) == 2 and all(r.exc_info for r in logged)


# --- Model settings and the prompt (C.9) ---


@pytest.mark.parametrize(("cls", "max_out"), [(PhysicalAgent, 3400), (NutritionAgent, 6000),
                                              (MentalAgent, 2200)])
async def test_each_agent_sends_its_max_output_setting(cls, max_out):
    options = cls.options()
    assert (options.model, options.reasoning, options.max_output_tokens) == (
        "gpt-6-luna", "low", max_out)


async def test_the_prompt_prefix_is_the_same_for_every_user():
    agent, fake = _agent(PhysicalAgent, _result(_physical("glute_bridge")),
                         _result(_physical("glute_bridge")))
    await agent.run(_run(profile=KNEE))
    await agent.run(_run(profile=GLUTEN, message="different words"))
    assert fake.calls[0].system == fake.calls[1].system
    assert "knee_ligament_injury" not in fake.calls[0].system  # the profile is a message
    assert "knee_ligament_injury" in fake.calls[0].messages[0].text


@pytest.mark.parametrize("cls", [PhysicalAgent, NutritionAgent, MentalAgent])
async def test_the_prefix_is_long_enough_to_cache(cls):
    import tiktoken
    assert len(tiktoken.get_encoding("o200k_base").encode(cls(None).system)) >= 1024


# --- Tools (C.10 step 3) ---


async def test_tool_calls_in_one_round_run_at_the_same_time():
    async def slow(args, ctx):
        await asyncio.sleep(1)
        return {"ok": True}

    agent, _ = _agent(MentalAgent, _calls(("slow", {"query": "a"}), ("slow", {"query": "b"})),
                      _result(MentalReply(kind="answer", summary="ok", items=[], notes=[],
                                          source_ids=[], follow_up=None, risk_flag=False)))
    agent.tools["slow"] = Tool("slow", "read", "slow", WebSearchArgs, slow)
    began = time.monotonic()
    await agent.run(_run(profile=NONE))
    assert time.monotonic() - began < 1.5


async def test_a_tool_round_and_the_reply_take_one_call_each():
    # Live (Part D): tools and the schema in one call, no separate tool phase
    log = ("log_meal", {"meal": "lunch", "foods": [_logged(_food("Dal", ["lentils"]))]})
    agent, fake = _agent(NutritionAgent, _calls(log),
                         _result(_nutrition(kind="log_ack", summary="Lunch noted.")))
    result = await agent.run(_run(message="log my lunch: dal", profile=NONE))
    assert len(fake.calls) == 2
    assert fake.calls[1].tools is not None and fake.calls[1].schema is NutritionReply
    assert len(result.staged_writes) == 1


@pytest.mark.parametrize(("cls", "tool", "args", "reply"), [
    (PhysicalAgent, "log_workout",
     {"catalogue_id": "glute_bridge", "sets": 3, "reps": 12, "duration_s": None, "note": ""},
     _physical(kind="log_ack", summary="Nice work.")),
    (NutritionAgent, "log_meal",
     {"meal": "lunch", "foods": [_logged(_food("Dal and rice", ["lentils", "rice"]))]},
     _nutrition(kind="log_ack", summary="Lunch noted.")),
    (MentalAgent, "log_practice",
     {"catalogue_id": "box_breathing", "duration_min": 5, "mood_before": 2, "mood_after": 4,
      "note": ""},
     MentalReply(kind="log_ack", summary="Well done.", items=[], notes=[], source_ids=[],
                 follow_up=None, risk_flag=False)),
])
async def test_an_explicit_log_request_stages_a_write(cls, tool, args, reply):
    agent, _ = _agent(cls, _calls((tool, args)), _result(reply))
    result = await agent.run(_run(message="log it please", profile=NONE))
    assert [w.kind for w in result.staged_writes] == [
        {"log_workout": "workout", "log_meal": "meal", "log_practice": "practice"}[tool]]


async def test_saying_logged_without_a_write_is_a_failure_and_retried():
    claim = _physical(kind="log_ack", summary="Done, I've logged your squats.")
    agent, fake = _agent(PhysicalAgent, _result(claim),
                         _result(_physical(kind="answer", summary="Great session!")))
    result = await agent.run(_run(message="did 3x10 squats", profile=NONE))
    assert fake.calls[1].messages[-1].text == LOG_RETRY
    assert result.reply.summary == "Great session!"


async def test_only_this_turns_sources_are_kept():
    ctx = ToolContext(mode="guest", trace_id="t",
                      sources=[Source(id="s1", title="Study", url="https://example.org/a")])
    agent, _ = _agent(PhysicalAgent, _result(_physical("glute_bridge", source_ids=["s1", "s9"])))
    result = await agent.run(_run(ctx=ctx))
    assert result.reply.source_ids == ["s1"] and [s.id for s in result.sources] == ["s1"]


# --- Meal photos (C.14 step 7) ---

PIE = _food("Blueberry pie", ["wheat", "butter", "sugar"], ["gluten", "milk"])
PHOTO = (ImageInput(b"\xff\xd8 jpeg"),)


async def test_a_photo_conflict_is_kept_with_its_warning_and_no_retry():
    summary = "This looks like blueberry pie. A peanut cookie would go well with it."
    agent, fake = _agent(NutritionAgent, _result(_nutrition(PIE, summary=summary)))
    result = await agent.run(_run(message="is this ok?", profile=UserProfile(
        condition_ids=[], allergen_tags=["gluten", "peanut"], diet_tags=[], notes=""),
        images=PHOTO))
    assert len(fake.calls) == 1
    assert [i.name for i in result.reply.items] == ["Blueberry pie"]
    assert result.item_caveats == [["Likely contains gluten, which is in your allergies"]]
    assert PHOTO_CAVEAT in result.warnings
    assert result.reply.summary == "This looks like blueberry pie."
    assert fake.calls[0].messages[-1].images == PHOTO


async def test_the_same_food_in_a_plan_is_still_removed():
    agent, _ = _agent(NutritionAgent, _result(_nutrition(PIE)), _result(_nutrition(PIE)),
                      BadRequest("no", "openai"))
    result = await agent.run(_run(message="a dessert idea", profile=GLUTEN))
    assert result.reply.summary == UNSAFE_FALLBACK["nutrition"]


async def test_a_tool_round_leaves_the_final_calls_reserve():
    # The call with tools must end with the final call's reserve left: a week plan's
    # p95 16.3 + 0.5
    agent, fake = _agent(PhysicalAgent, _result(_physical("glute_bridge")))
    await agent.run(_run(left=60.0))
    assert 42.0 < fake.calls[0].options.timeout_s <= 60.0 - 16.8


async def test_a_cut_off_reply_is_malformed_even_if_it_parsed():
    cut = _result(_physical("glute_bridge"), truncated=True)
    agent, fake = _agent(PhysicalAgent, cut, _result(_physical("bird_dog")))
    result = await agent.run(_run())
    assert len(fake.calls) == 2 and result.reply.items[0].catalogue_id == "bird_dog"


async def test_saying_logged_with_a_write_is_fine():
    log = ("log_workout", {"catalogue_id": "glute_bridge", "sets": 3, "reps": 12,
                           "duration_s": None, "note": ""})
    agent, fake = _agent(PhysicalAgent, _calls(log),
                         _result(_physical(kind="log_ack", summary="Logged your bridges.")))
    result = await agent.run(_run(message="log 3x12 bridges", profile=NONE))
    assert len(fake.calls) == 2 and len(result.staged_writes) == 1
    # The claim itself is removed: the composer confirms from the commit result (C.17)
    assert result.reply.summary == "" and result.reply.kind == "log_ack"


async def test_a_photo_uses_the_photo_speed():
    # 15 s left: room for a photo tool round (p95 4.7 + reserve 5.2 = 9.9) but not a text
    # one, whose reply may be a week plan (4.6 + reserve 23.7 + 0.5 = 28.8)
    agent, fake = _agent(NutritionAgent, _result(_nutrition(_food("Dal", ["lentils"]))))
    await agent.run(_run(message="is this ok?", profile=NONE, images=PHOTO, left=15.0))
    assert fake.calls[0].tools is not None
    assert fake.calls[0].options.timeout_s <= 15.0 - 5.2
    agent, fake = _agent(NutritionAgent, _result(_nutrition(_food("Dal", ["lentils"]))))
    await agent.run(_run(message="dal ok?", profile=NONE, left=15.0))
    assert fake.calls[0].tools is None


# --- History (what a follow-up sees) ---


def test_history_text_shows_the_plan_not_only_the_summary():
    reply = PhysicalReply(kind="plan", summary="A gentle week.", notes=["Stop if it hurts."],
                          items=[_ex("glute_bridge"),
                                 ExerciseItem(day=None, catalogue_id="walking", sets=None,
                                              reps=None, duration_s=1200, intensity="low",
                                              note="")],
                          source_ids=[], follow_up=None, risk_flag=False)
    assert history_text(reply) == ("A gentle week.\n1. Glute bridge: 2 x 10\n"
                                   "2. Walking: 20 min\n- Stop if it hurts.")
    meal = _nutrition(_food("Dal", ["lentils"]))
    assert history_text(meal) == "Here you go.\n1. Dal (1 plate, about 400 kcal)"
    practice = MentalReply(kind="plan", summary="Tonight:", notes=[], source_ids=[],
                           follow_up=None, risk_flag=False,
                           items=[PracticeItem(day=None, catalogue_id="box_breathing",
                                               duration_min=5, note="")])
    assert history_text(practice) == "Tonight:\n1. Box breathing: 5 min"
    assert history_text(reply, limit=30) == "A gentle week."
    holds = PhysicalReply(kind="plan", summary="Core.", notes=[], source_ids=[], follow_up=None,
                          risk_flag=False, items=[
                              ExerciseItem(day=None, catalogue_id="plank", sets=3, reps=None,
                                           duration_s=30, intensity="low", note=""),
                              ExerciseItem(day=None, catalogue_id="wall_sit", sets=None,
                                           reps=None, duration_s=12, intensity="low", note="")])
    # Live (Part D): a 12-second hold was shown as "0.2 min"
    assert history_text(holds) == "Core.\n1. Plank: 3 x 30 s\n2. Wall sit: 12 s"
    week = PhysicalReply(kind="plan", summary="Your week.", notes=[], source_ids=[],
                         follow_up=None, risk_flag=False,
                         items=[_ex("glute_bridge").model_copy(update={"day": "Mon"}),
                                _ex("bird_dog").model_copy(update={"day": "Thu"})])
    assert history_text(week) == ("Your week.\n1. Mon: Glute bridge: 2 x 10\n"
                                  "2. Thu: Bird dog: 2 x 10")


# --- The per-turn note: language and the other coaches (Part D) ---


@pytest.mark.parametrize(("message", "says"), [
    ("leg workout please", "reply in English"),
    ("aaj leg workout kya karu", "reply in Hinglish"),
    ("आज कौन सी exercise करूँ?", "reply in Hindi, in Devanagari"),
])
async def test_the_coach_is_told_the_persons_language(message, says):
    agent, fake = _agent(PhysicalAgent, _result(_physical("glute_bridge")))
    await agent.run(_run(message=message))
    last = fake.calls[0].messages[-1].text
    assert last.startswith(message) and says in last


async def test_the_coach_is_told_who_else_is_answering():
    agent, fake = _agent(NutritionAgent, _result(_nutrition(_food("Dal", ["lentils"]))))
    run = _run(message="workouts and snacks for my hike", profile=NONE)
    run.others = ("physical", "mental")
    await agent.run(run)
    last = fake.calls[0].messages[-1].text
    assert ("The exercise and mental wellbeing coaches are answering the rest of this message: "
            "answer only the food part. Don't mention them or their part: their answers "
            "appear next to yours.") in last


async def test_the_coach_is_told_not_to_mention_the_one_other_coach():
    # Live, 10 Nov 2026: "the exercise coach can help with tomorrow's workout"
    agent, fake = _agent(MentalAgent, _result(MentalReply(
        kind="answer", summary="ok", items=[], notes=[], source_ids=[], follow_up=None,
        risk_flag=False)))
    run = _run(message="breathing for stress and a light workout", profile=NONE)
    run.others = ("physical",)
    await agent.run(run)
    assert ("Don't mention that coach or their part: its answer appears next to yours."
            in fake.calls[0].messages[-1].text)


async def test_the_coach_is_told_the_persons_day_and_time():
    """Part E #51: "yesterday" and "this morning" need the person's own day."""
    agent, fake = _agent(MentalAgent, _result(MentalReply(
        kind="answer", summary="ok", items=[], notes=[], source_ids=[], follow_up=None,
        risk_flag=False)))
    run = _run(message="can't sleep", profile=NONE)
    run.now = "It's Monday 9 Nov 2026, 9:30 am for this person."
    await agent.run(run)
    assert run.now in fake.calls[0].messages[-1].text


async def test_a_lone_coach_gets_no_other_coaches_note():
    agent, fake = _agent(MentalAgent, _result(MentalReply(
        kind="answer", summary="ok", items=[], notes=[], source_ids=[], follow_up=None,
        risk_flag=False)))
    await agent.run(_run(message="can't sleep", profile=NONE))
    last = fake.calls[0].messages[-1].text
    assert "answering the rest" not in last and "Don't mention" not in last


# --- Failure library (Part E #55) ---

_ANSWER = MentalReply(kind="answer", summary="ok", items=[], notes=[], source_ids=[],
                      follow_up=None, risk_flag=False)


async def test_a_tool_the_coach_doesnt_have_is_answered_and_the_coach_goes_on():
    trace = Trace("t")
    agent, fake = _agent(MentalAgent, _calls(("delete_everything", {})), _result(_ANSWER))
    result = await agent.run(_run(profile=NONE, trace=trace))
    assert result.reply is not None
    assert ("tool_call", "unknown_tool", "delete_everything") in _steps(trace)
    sent = [m for m in fake.calls[1].messages if isinstance(m, ToolResult)]
    assert [(r.name, r.output) for r in sent] == [("delete_everything",
                                                   {"status": "unknown_tool"})]


async def test_a_coach_that_keeps_calling_tools_must_reply_after_its_rounds():
    search = ("web_search", {"query": "box breathing"})
    agent, fake = _agent(MentalAgent, *[_calls(search)] * TOOL_ROUNDS, _result(_ANSWER))
    result = await agent.run(_run(profile=NONE))
    assert result.reply is not None and len(fake.calls) == TOOL_ROUNDS + 1
    assert all(c.tools for c in fake.calls[:TOOL_ROUNDS])
    assert fake.calls[TOOL_ROUNDS].tools is None  # the last call can only reply
