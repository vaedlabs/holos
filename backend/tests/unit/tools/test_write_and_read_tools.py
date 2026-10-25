"""Write tools gate then stage and never touch the DB; read tools in guest mode (Plan P2.2)."""

import pytest

from app.agents.schemas import Decision
from app.agents.tools import AGENT_TOOLS, GateResult, ToolContext

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

TOOLS = {t.name: t for tools in AGENT_TOOLS.values() for t in tools}

WRITES = {
    "log_workout": ("workout", {"catalogue_id": "push_up", "sets": 3, "reps": 10,
                                "duration_s": None, "note": ""}, "Push-up: 3 x 10"),
    "log_meal": ("meal", {"meal": "lunch", "foods": [{
        "name": "Dal rice", "ingredients": ["lentils", "rice"], "allergen_tags": [],
        "diet_tags": ["vegan"], "portion": "1 plate", "calories": 520, "note": ""}]},
        "Lunch: Dal rice"),
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
