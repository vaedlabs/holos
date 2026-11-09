"""log_workout, log_meal, log_practice (Plan C.10, C.17).

A write tool gates the entry, then stages it on the request context. It never
touches the database: the Composer commits staged writes after the final reply
passes the gate, or turns them into pending writes after a web search or when the
entry conflicts with the profile ("held": the person confirms, Part E #45). The tool
says "held" for both, so the coach never tells the person it was logged (Part E #52).

Before the gate, the entry's `when` becomes a time (agents/when.py, Part E #51): one
ahead of now or too far back is refused, nothing staged; one the person didn't give is
the usual time, and the entry waits for them to pick it on the card.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.agents.clock import when_text
from app.agents.display import item_display
from app.agents.schemas import (
    LogMealArgs,
    LogPracticeArgs,
    LogWorkoutArgs,
    StagedWrite,
    WriteKind,
)
from app.agents.when import NotLoggable, resolve

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


# What the coach says about a held entry (Part E #52): live, it said "I couldn't save
# this snack" in 2 of 4 turns while the card below offered Confirm
HELD = ("Not refused and not saved yet: it waits for the person to confirm it on the card "
        "below your reply, where they can also choose Don't log. Say what conflicts, if "
        "anything, and that they can confirm it there. Don't say it was refused, couldn't "
        "be saved, or was logged.")
# Part E #51: no time given, so the card asks for one (owner, 9 Nov 2026)
HELD_TIME = ("Not saved yet: the person didn't say what time, so it waits on the card below "
             "your reply with {} filled in, for them to pick the time and confirm. Say so "
             "briefly. Don't say it was refused, couldn't be saved, or was logged.")


async def _stage(kind: WriteKind, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
    said = ctx.said or datetime.now(UTC)
    try:
        when = resolve(args.when, getattr(args, "meal", None), said, ctx.tz)
    except NotLoggable as exc:
        return {"status": "refused", "reason": str(exc)}
    gate = await ctx.gate_write(kind, args, ctx)
    ctx.decisions.extend(gate.decisions)
    if not gate.allowed:
        return {"status": "refused", "reason": gate.reason or "Not allowed for your profile"}
    args = gate.args or args
    write = StagedWrite(kind=kind, args=args, warnings=list(gate.warnings),
                        at=None if when.at == said else when.at, time_guessed=when.guessed)
    ctx.staged_writes.append(write)
    if write.conflicts:  # something they already had conflicts: they confirm (Part E #45)
        return {"status": "held", "summary": summarise(kind, args),
                "warnings": [f"{w.item}: {w.reason}" for w in write.conflicts], "next": HELD}
    if write.time_guessed:
        return {"status": "held", "summary": summarise(kind, args),
                "next": HELD_TIME.format(when_text(when.at, ctx.tz, said))}
    if ctx.untrusted:  # a web search came first: the person confirms it (C.17)
        return {"status": "held", "summary": summarise(kind, args), "next": HELD}
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
