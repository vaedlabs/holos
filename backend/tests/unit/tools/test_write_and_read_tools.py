"""Write tools gate then stage and never touch the DB; read tools in guest mode (Plan P2.2)."""

from datetime import timedelta

import pytest
from sqlalchemy.exc import OperationalError

from app.agents.clock import zone
from app.agents.schemas import Decision, WriteWarning
from app.agents.tools import AGENT_TOOLS, GateResult, ToolContext, TurnEntries
from app.agents.tools import write as write_tools
from app.config.limits import ENTRIES_PER_TURN

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

TOOLS = {t.name: t for tools in AGENT_TOOLS.values() for t in tools}

WRITES = {
    "log_workout": ("workout", {"catalogue_id": "push_up", "sets": 3, "reps": 10,
                                "duration_s": None, "note": ""}, "Push-up: 3 x 10"),
    "log_meal": ("meal", {"meal": "lunch", "foods": [{
        "day": None, "name": "Dal rice", "ingredients": ["lentils", "rice"], "allergen_tags": [],
        "diet_tags": ["vegan"], "portion": "1 plate", "calories": 520, "note": "",
        "protein_g": 18, "carbs_g": 85, "fat_g": 10}]},
        "Lunch: Dal rice · 520 kcal · protein 18 g, carbs 85 g, fat 10 g"),
    "log_practice": ("practice", {"catalogue_id": "box_breathing", "duration_min": 5,
                                  "mood_before": None, "mood_after": 4, "note": ""},
                     "Box breathing: 5 min"),
}


def _no_db():
    raise AssertionError("a write tool opened a database session")


@pytest.fixture
def account_ctx():
    # sessions() raises if called: write tools must not touch the database
    return ToolContext(mode="account", trace_id="t1", user_id=7, sessions=_no_db)


@pytest.mark.parametrize("name", list(WRITES))
async def test_write_stages_and_never_opens_the_db(account_ctx, name):
    kind, args, summary = WRITES[name]
    out = await TOOLS[name].run(args, account_ctx)
    assert out == {"status": "staged", "summary": summary}
    [staged] = account_ctx.staged_writes
    assert staged.kind == kind


# --- When it happened (Part E #51) ---


async def test_a_time_the_person_gave_is_staged_with_it(account_ctx, lunchtime):
    args = {**WRITES["log_workout"][1],
            "when": {"day": "yesterday", "time": "7:00", "ampm": "am", "part": None}}
    out = await TOOLS["log_workout"].run(args, account_ctx)
    assert out["status"] == "staged"
    [staged] = account_ctx.staged_writes
    assert staged.at == (lunchtime - timedelta(days=1)).replace(hour=7, minute=0)
    assert not staged.time_guessed and not staged.waits


async def test_no_time_given_waits_with_the_usual_time_for_the_person_to_pick(account_ctx):
    account_ctx.tz = zone("Asia/Kolkata")  # lunchtime in UTC is 6 pm there
    args = {**WRITES["log_meal"][1],
            "when": {"day": "yesterday", "time": None, "ampm": None, "part": None}}
    out = await TOOLS["log_meal"].run(args, account_ctx)
    assert out["status"] == "held"
    assert "with yesterday, 1:00 pm filled in" in out["next"]
    [staged] = account_ctx.staged_writes
    assert staged.time_guessed and staged.waits


@pytest.mark.parametrize(("when", "reason"), [
    ({"day": "today", "time": "11:00", "ampm": "pm", "part": None}, "ahead of time"),
    ({"day": "2025-01-01", "time": None, "ampm": None, "part": None}, "more than 30 days"),
])
async def test_a_time_ahead_or_too_far_back_stages_nothing(account_ctx, when, reason):
    async def never(kind, args, ctx):
        raise AssertionError("the gate ran")

    account_ctx.gate_write = never
    out = await TOOLS["log_practice"].run({**WRITES["log_practice"][1], "when": when},
                                          account_ctx)
    assert out["status"] == "refused" and reason in out["reason"]
    assert account_ctx.staged_writes == []


@pytest.mark.parametrize("name", list(WRITES))
async def test_after_a_web_search_a_write_is_held_not_staged(account_ctx, name):
    kind, args, summary = WRITES[name]
    account_ctx.untrusted = True
    out = await TOOLS[name].run(args, account_ctx)
    assert out == {"status": "held", "summary": summary, "next": write_tools.HELD}
    assert [w.kind for w in account_ctx.staged_writes] == [kind]


async def test_a_conflict_is_held_and_says_what_to_tell_the_person(account_ctx):
    peanut = WriteWarning(kind="conflict", item="Dal rice", rule_id="DI-ALG-01",
                          attributes=["peanut"], reason="contains peanut")

    async def warn(kind, args, ctx):
        return GateResult(allowed=True, warnings=(peanut,))

    account_ctx.gate_write = warn
    out = await TOOLS["log_meal"].run(WRITES["log_meal"][1], account_ctx)
    assert out["status"] == "held" and out["next"] == write_tools.HELD
    assert out["warnings"] == ["Dal rice: contains peanut"]
    assert "waits for the person to confirm it" in out["next"]


@pytest.mark.parametrize("name", list(WRITES))
async def test_gate_refusal_stages_nothing(account_ctx, name):
    block = Decision(action="block", rule_id="DI-ALG-01", rules_version=1,
                     reason="Contains an allergen in your profile")

    async def refuse(kind, args, ctx):
        return GateResult(allowed=False, reason=block.reason, decisions=(block,))

    account_ctx.gate_write = refuse
    out = await TOOLS[name].run(WRITES[name][1], account_ctx)
    assert out == {"status": "refused", "reason": "Contains an allergen in your profile"}
    assert account_ctx.staged_writes == []
    assert account_ctx.decisions == [block]


async def test_gate_sees_the_validated_arguments(account_ctx):
    seen = []

    async def record(kind, args, ctx):
        seen.append((kind, args.catalogue_id))
        return GateResult(allowed=True)

    account_ctx.gate_write = record
    await TOOLS["log_workout"].run(WRITES["log_workout"][1], account_ctx)
    assert seen == [("workout", "push_up")]


async def test_unknown_catalogue_id_is_invalid_and_not_staged(account_ctx):
    args = {**WRITES["log_workout"][1], "catalogue_id": "death_squat"}
    out = await TOOLS["log_workout"].run(args, account_ctx)
    assert out["status"] == "invalid_arguments"
    assert account_ctx.staged_writes == []


# --- Limits a hostile or confused model can't pass (Part E #59) ---


async def test_one_message_logs_at_most_its_cap_across_every_coach():
    turn = TurnEntries()
    physical = ToolContext(mode="guest", trace_id="t", turn=turn)
    nutrition = ToolContext(mode="guest", trace_id="t", turn=turn)
    for _ in range(ENTRIES_PER_TURN - 1):
        assert (await TOOLS["log_workout"].run(WRITES["log_workout"][1], physical)
                )["status"] == "staged"
    assert (await TOOLS["log_meal"].run(WRITES["log_meal"][1], nutrition))["status"] == "staged"
    out = await TOOLS["log_workout"].run(WRITES["log_workout"][1], physical)
    assert out == {"status": "refused", "reason": write_tools.TOO_MANY}
    assert turn.count() == ENTRIES_PER_TURN


@pytest.mark.parametrize("activity, logged", [
    ("Barbell back squats", "back_squat"),
    ("pistol squats", "pistol_squat"),
    ("Archery", "other_activity"),
    ("Archery, no squats", "other_activity"),
    ("squats and lunges", "other_activity"),  # two exercises: kept as they named it
])
async def test_another_activity_named_after_one_exercise_is_that_exercise(account_ctx,
                                                                           activity, logged):
    args = {**WRITES["log_workout"][1], "catalogue_id": "other_activity",
            "activity": activity}
    await TOOLS["log_workout"].run(args, account_ctx)
    [staged] = account_ctx.staged_writes
    assert staged.args.catalogue_id == logged
    assert staged.args.activity == (activity if logged == "other_activity" else None)


async def test_retry_clears_staged_writes(account_ctx):
    await TOOLS["log_practice"].run(WRITES["log_practice"][1], account_ctx)
    account_ctx.clear_staged()
    assert account_ctx.staged_writes == []


@pytest.mark.parametrize(
    ("args", "summary"),
    [({"sets": None, "reps": None, "duration_s": 1800}, "Push-up: 30 min"),
     ({"sets": None, "reps": None, "duration_s": None}, "Push-up")],
)
async def test_workout_summaries(account_ctx, args, summary):
    out = await TOOLS["log_workout"].run({**WRITES["log_workout"][1], **args}, account_ctx)
    assert out["summary"] == summary


async def test_guest_recent_logs_are_empty():
    ctx = ToolContext(mode="guest", trace_id="t1", sessions=_no_db)
    out = await TOOLS["get_recent_logs"].run({"kind": "meal", "days": 7}, ctx)
    assert out == {"entries": []}


@pytest.mark.parametrize("days", [0, 15])
async def test_recent_logs_days_bounds(days):
    ctx = ToolContext(mode="guest", trace_id="t1")
    out = await TOOLS["get_recent_logs"].run({"kind": "meal", "days": days}, ctx)
    assert out["status"] == "invalid_arguments"


def test_agents_get_the_c10_tools():
    names = {agent: {t.name for t in tools} for agent, tools in AGENT_TOOLS.items()}
    shared = {"get_recent_logs", "web_search"}
    assert names == {"physical": shared | {"log_workout"}, "nutrition": shared | {"log_meal"},
                     "mental": shared | {"log_practice"}}


async def test_recent_logs_when_the_database_cant_answer():
    """Failure library (Part E #55): the coach answers without them, it doesn't fail."""
    def down():
        raise OperationalError("SELECT", {}, ConnectionRefusedError("refused"))

    ctx = ToolContext(mode="account", trace_id="t1", user_id=7, sessions=down)
    out = await TOOLS["get_recent_logs"].run({"kind": "meal", "days": 7}, ctx)
    assert out == {"status": "unavailable"}
