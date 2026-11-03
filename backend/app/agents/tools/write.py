"""log_workout, log_meal, log_practice (Plan C.10, C.17).

A write tool gates the entry, then stages it on the request context. It never
touches the database: the Composer commits staged writes after the final reply
passes the gate, or turns them into pending writes after a web search or when the
entry conflicts with the profile ("held": the person confirms, Part E #45).
"""

from typing import Any

from pydantic import BaseModel

from app.agents.display import item_display
from app.agents.schemas import (
    LogMealArgs,
    LogPracticeArgs,
    LogWorkoutArgs,
    StagedWrite,
    WriteKind,
)

from .base import Tool, ToolContext


def summarise(kind: WriteKind, args: BaseModel) -> str:
    """A short human summary of a staged write, e.g. "Push-up: 3 x 10" (a hold under a
    minute read "0 min")."""
    if isinstance(args, LogWorkoutArgs | LogPracticeArgs):
        return item_display(args)
    if isinstance(args, LogMealArgs):
        return f"{args.meal.capitalize()}: {', '.join(f.name for f in args.foods)}" + _amounts(args)
    raise TypeError(f"no summary for {kind}")


def _amounts(meal: LogMealArgs) -> str:
    """ " · 520 kcal · protein 18 g, carbs 70 g, fat 9 g": only totals every food gave,
    so a sum is never shown short."""
    t = meal.totals()
    complete = {n: all(getattr(f, n) is not None for f in meal.foods)
                for n in ("calories", "protein_g", "carbs_g", "fat_g")}
    parts = [f"{round(t['calories'])} kcal"] if complete["calories"] else []
    macros = [f"{label} {round(t[n])} g" for n, label in
              (("protein_g", "protein"), ("carbs_g", "carbs"), ("fat_g", "fat")) if complete[n]]
    if macros:
        parts.append(", ".join(macros))
    return "".join(f" · {p}" for p in parts)


async def _stage(kind: WriteKind, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
    gate = await ctx.gate_write(kind, args, ctx)
    ctx.decisions.extend(gate.decisions)
    if not gate.allowed:
        return {"status": "refused", "reason": gate.reason or "Not allowed for your profile"}
    args = gate.args or args
    write = StagedWrite(kind=kind, args=args, warnings=list(gate.warnings))
    ctx.staged_writes.append(write)
    if write.conflicts:  # something they already had conflicts: they confirm (Part E #45)
        return {"status": "held", "summary": summarise(kind, args),
                "warnings": [f"{w.item}: {w.reason}" for w in write.conflicts]}
    return {"status": "staged", "summary": summarise(kind, args)}


async def log_workout(args: LogWorkoutArgs, ctx: ToolContext) -> dict[str, Any]:
    return await _stage("workout", args, ctx)


async def log_meal(args: LogMealArgs, ctx: ToolContext) -> dict[str, Any]:
    return await _stage("meal", args, ctx)


async def log_practice(args: LogPracticeArgs, ctx: ToolContext) -> dict[str, Any]:
    return await _stage("practice", args, ctx)


_DESCRIPTION = "Log a {} for the user. It is saved only after the reply passes the safety check."

LOG_WORKOUT = Tool("log_workout", "write", _DESCRIPTION.format("workout"), LogWorkoutArgs,
                   log_workout)
LOG_MEAL = Tool("log_meal", "write", _DESCRIPTION.format("meal"), LogMealArgs, log_meal)
LOG_PRACTICE = Tool("log_practice", "write", _DESCRIPTION.format("practice"), LogPracticeArgs,
                    log_practice)
