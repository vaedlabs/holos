"""log_workout, log_meal, log_practice (Plan C.10, C.17).

A write tool gates the entry, then stages it on the request context. It never
touches the database: the Composer commits staged writes after the final reply
passes the gate, or turns them into pending writes after a web search.
"""

from typing import Any

from pydantic import BaseModel

from app.agents.schemas import (
    LogMealArgs,
    LogPracticeArgs,
    LogWorkoutArgs,
    StagedWrite,
    WriteKind,
)
from app.guardrails.loader import get_guardrails

from .base import Tool, ToolContext

_catalogue = get_guardrails().catalogue
_NAMES = {item.id: item.name for item in [*_catalogue.exercises, *_catalogue.practices]}


def summarise(kind: WriteKind, args: BaseModel) -> str:
    """A short human summary of a staged write, e.g. "Push-up: 3 x 10"."""
    if isinstance(args, LogWorkoutArgs):
        name = _NAMES[args.catalogue_id]
        if args.sets and args.reps:
            return f"{name}: {args.sets} x {args.reps}"
        if args.duration_s:
            return f"{name}: {round(args.duration_s / 60)} min"
        return name
    if isinstance(args, LogPracticeArgs):
        return f"{_NAMES[args.catalogue_id]}: {args.duration_min} min"
    if isinstance(args, LogMealArgs):
        return f"{args.meal.capitalize()}: {', '.join(f.name for f in args.foods)}"
    raise TypeError(f"no summary for {kind}")


async def _stage(kind: WriteKind, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
    gate = await ctx.gate_write(kind, args, ctx)
    ctx.decisions.extend(gate.decisions)
    if not gate.allowed:
        return {"status": "refused", "reason": gate.reason or "Not allowed for your profile"}
    ctx.staged_writes.append(StagedWrite(kind=kind, args=args))
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
