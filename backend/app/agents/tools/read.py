"""get_recent_logs (Plan C.10). Profile and history are already in the prompt (C.8)."""

import json
import logging
from typing import Any

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from app.agents.schemas import GetRecentLogsArgs
from app.data.repositories import (
    MentalLogRepository,
    NutritionLogRepository,
    WorkoutLogRepository,
)

from .base import Tool, ToolContext

log = logging.getLogger(__name__)

_REPOS = {
    "workout": WorkoutLogRepository,
    "meal": NutritionLogRepository,
    "practice": MentalLogRepository,
}
_FIELDS = {
    "workout": ("workout_date",
                ["exercise_type", "exercises", "duration_minutes", "notes", "warnings"]),
    "meal": ("meal_date", ["meal_type", "foods", "calories", "macros", "notes", "warnings"]),
    "practice": ("activity_date", ["activity_type", "duration_minutes", "notes", "warnings"]),
}


async def get_recent_logs(args: GetRecentLogsArgs, ctx: ToolContext) -> dict[str, Any]:
    """Up to 20 entries, newest first. Guests have no server-side logs. If the database
    can't answer, the coach is told so and answers without them (failure library)."""
    if ctx.mode == "guest" or ctx.sessions is None or ctx.user_id is None:
        return {"entries": []}
    date_field, fields = _FIELDS[args.kind]
    try:
        async with ctx.sessions() as session:
            rows = await _REPOS[args.kind](session, ctx.user_id).recent(days=args.days)
    except (OperationalError, InterfaceError, PoolTimeout):
        log.warning("recent logs unavailable: trace=%s", ctx.trace_id)
        return {"status": "unavailable"}
    ctx.read_logs += [_had(args.kind, r) for r in rows]
    return {
        "entries": [
            {"date": getattr(r, date_field).isoformat(), **{f: getattr(r, f) for f in fields}}
            for r in rows
        ]
    }


def _had(kind: str, row: Any) -> dict[str, Any]:
    """A row as the gate reads a logged entry, with what the person left out of a meal."""
    if kind == "workout":
        return {"catalogue_id": row.exercise_type}
    if kind == "practice":
        return {"catalogue_id": row.activity_type}
    try:
        foods = json.loads(row.foods or "[]")
    except ValueError:
        foods = []
    left_out = sorted({a for w in row.warnings or [] if isinstance(w, dict) and w.get("left_out")
                       for a in w.get("attributes", [])})
    return {"foods": foods if isinstance(foods, list) else [], "left_out": left_out}


GET_RECENT_LOGS = Tool(
    name="get_recent_logs",
    kind="read",
    description="The user's recent workout, meal or practice logs, newest first (up to 20).",
    args_model=GetRecentLogsArgs,
    handler=get_recent_logs,
)
