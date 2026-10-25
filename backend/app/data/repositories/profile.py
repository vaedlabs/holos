from sqlalchemy import select

from app.models import MedicalHistory, UserPreferences

from .base import UserScopedRepository

MEDICAL_FIELDS = {"conditions", "limitations", "medications", "notes"}
PREFERENCE_FIELDS = {
    "goals", "dietary_restrictions", "location", "exercise_types", "activity_level",
    "age", "gender", "lifestyle",
}


class ProfileRepository(UserScopedRepository):
    """The user's medical history and preferences."""

    async def get_medical(self) -> MedicalHistory | None:
        return await self._session.scalar(
            select(MedicalHistory).where(MedicalHistory.user_id == self._user_id)
        )

    async def get_preferences(self) -> UserPreferences | None:
        return await self._session.scalar(
            select(UserPreferences).where(UserPreferences.user_id == self._user_id)
        )

    async def save_medical(self, **fields) -> MedicalHistory:
        """Create or update the medical history with the given fields."""
        row = await self.get_medical() or MedicalHistory(user_id=self._user_id)
        for key, value in self._fields(fields, MEDICAL_FIELDS).items():
            setattr(row, key, value)
        self._session.add(row)
        await self._session.flush()
        return row

    async def save_preferences(self, **fields) -> UserPreferences:
        """Create or update the preferences with the given fields."""
        row = await self.get_preferences() or UserPreferences(user_id=self._user_id)
        for key, value in self._fields(fields, PREFERENCE_FIELDS).items():
            setattr(row, key, value)
        self._session.add(row)
        await self._session.flush()
        return row
