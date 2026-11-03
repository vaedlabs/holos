"""A gated write as an account's log row (Plan C.10: workout → workout_logs, meal →
nutrition_logs, practice → mental_fitness_logs).

    log_id = await insert_log(session, user_id, write)   # inside the caller's transaction

The chat turn's auto-commit and the confirm endpoint both insert through here, so a
confirmed entry reads the same as one logged at once. JSON columns are text in the old
tables; `get_recent_logs` hands them to the coaches as they are.
"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.display import NAMES
from app.agents.schemas import LogMealArgs, LogPracticeArgs, LogWorkoutArgs, StagedWrite
from app.data.repositories import (
    MentalLogRepository,
    NutritionLogRepository,
    WorkoutLogRepository,
)


async def insert_log(session: AsyncSession, user_id: int, write: StagedWrite) -> int:
    args = write.args
    warnings = [w.model_dump(mode="json") for w in write.warnings] or None
    if isinstance(args, LogWorkoutArgs):
        row = await WorkoutLogRepository(session, user_id).add(
            exercise_type=args.catalogue_id,
            exercises=json.dumps([{"catalogue_id": args.catalogue_id,
                                   "name": NAMES[args.catalogue_id], "sets": args.sets,
                                   "reps": args.reps, "duration_s": args.duration_s}]),
            duration_minutes=args.duration_s / 60 if args.duration_s else None,
            notes=args.note or None, warnings=warnings)
    elif isinstance(args, LogMealArgs):
        totals = args.totals()
        row = await NutritionLogRepository(session, user_id).add(
            meal_type=args.meal,
            foods=json.dumps([f.model_dump(mode="json") for f in args.foods],
                             ensure_ascii=False),
            calories=totals.pop("calories"), macros=json.dumps(totals), warnings=warnings)
    elif isinstance(args, LogPracticeArgs):
        row = await MentalLogRepository(session, user_id).add(
            activity_type=args.catalogue_id, duration_minutes=args.duration_min,
            mood_before=_mood(args.mood_before), mood_after=_mood(args.mood_after),
            notes=args.note or None, warnings=warnings)
    else:
        raise TypeError(f"no log table for {write.kind}")
    return row.id


def _mood(value: int | None) -> str | None:
    return None if value is None else str(value)
