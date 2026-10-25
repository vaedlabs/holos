from datetime import UTC, datetime, timedelta
from typing import ClassVar

from sqlalchemy import delete, select

from app.models import MentalFitnessLog, NutritionLog, WorkoutLog

from .base import UserScopedRepository

MAX_RECENT = 20  # get_recent_logs returns at most 20 entries (Plan C.10)


class _LogRepository(UserScopedRepository):
    model: ClassVar[type]
    date_column: ClassVar[str]
    fields: ClassVar[set[str]]

    async def add(self, **fields):
        row = self.model(user_id=self._user_id, **self._fields(fields, self.fields))
        self._session.add(row)
        await self._session.flush()
        return row

    async def recent(self, days: int, limit: int = MAX_RECENT) -> list:
        """Entries from the last `days` days, newest first."""
        date = getattr(self.model, self.date_column)
        since = datetime.now(UTC) - timedelta(days=days)
        rows = await self._session.scalars(
            select(self.model)
            .where(self.model.user_id == self._user_id, date >= since)
            .order_by(date.desc(), self.model.id.desc())
            .limit(min(limit, MAX_RECENT))
        )
        return list(rows)

    async def delete(self, log_id: int) -> bool:
        result = await self._session.execute(
            delete(self.model).where(self.model.id == log_id, self.model.user_id == self._user_id)
        )
        return result.rowcount == 1


class WorkoutLogRepository(_LogRepository):
    model = WorkoutLog
    date_column = "workout_date"
    fields = {"workout_date", "exercise_type", "exercises", "duration_minutes", "notes"}


class NutritionLogRepository(_LogRepository):
    model = NutritionLog
    date_column = "meal_date"
    fields = {"meal_date", "meal_type", "foods", "calories", "macros", "notes"}


class MentalLogRepository(_LogRepository):
    model = MentalFitnessLog
    date_column = "activity_date"
    fields = {"activity_date", "activity_type", "duration_minutes", "mood_before", "mood_after",
              "notes"}
