"""The account's logs as GET /logs/* returns them (C.17 writes them), newest first.

The rows keep a workout's exercises, a meal's foods and its macros as JSON text; the
responses send them as lists and an object (R9, Part E #74), so the app reads real
shapes and the contracts can type them. Stored text that doesn't read as the shape
(the old app's `{"foods": [...]}`, a row from before the rebuild) gives what does read:
each item without a name is left out, never sent as raw JSON (D062 B1, B3).
Each log also sends the warnings stored with it (Part E #65 (4)), so the logs can say
what was left out and which conflicts the person confirmed.
"""

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.agents.schemas import WriteWarning


class _Read(BaseModel):
    # Stored items carry more than the logs show (ingredients, tags): ignored
    model_config = ConfigDict(extra="ignore")


class LoggedExerciseView(_Read):
    name: str
    catalogue_id: str | None = None
    sets: int | None = None
    reps: int | None = None
    duration_s: int | None = None


class LoggedFoodView(_Read):
    name: str
    portion: str | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None


class MacrosView(_Read):
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    complete: bool | None = None  # every food gave all four


def _json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return None


def _items(value: Any, key: str, model: type[_Read]) -> list[dict]:
    """A stored list as the items that read; the old app wrapped it as {key: [...]}."""
    value = _json(value)
    if isinstance(value, dict):
        value = value.get(key)
    out = []
    for item in value if isinstance(value, list) else []:
        try:
            out.append(model.model_validate(item).model_dump())
        except ValidationError:
            continue
    return out


def _warnings(value: Any) -> list[dict]:
    """The stored warnings that read; a row from before them (or JSON null) has none."""
    out = []
    for item in value if isinstance(value, list) else []:
        try:
            out.append(WriteWarning.model_validate(item).model_dump())
        except ValidationError:
            continue
    return out


class _Logged(BaseModel):
    warnings: list[WriteWarning] = []

    @field_validator("warnings", mode="before")
    @classmethod
    def _read_warnings(cls, value: Any) -> list[dict]:
        return _warnings(value)


class WorkoutLogResponse(_Logged):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    workout_date: datetime
    exercise_type: str | None
    exercises: list[LoggedExerciseView]
    duration_minutes: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime | None

    @field_validator("exercises", mode="before")
    @classmethod
    def _read_exercises(cls, value: Any) -> list[dict]:
        return _items(value, "exercises", LoggedExerciseView)


class NutritionLogResponse(_Logged):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    meal_date: datetime
    meal_type: str | None
    foods: list[LoggedFoodView]
    calories: float | None
    macros: MacrosView | None
    notes: str | None
    created_at: datetime
    updated_at: datetime | None

    @field_validator("foods", mode="before")
    @classmethod
    def _read_foods(cls, value: Any) -> list[dict]:
        return _items(value, "foods", LoggedFoodView)

    @field_validator("macros", mode="before")
    @classmethod
    def _read_macros(cls, value: Any) -> dict | None:
        try:
            return MacrosView.model_validate(_json(value)).model_dump()
        except ValidationError:
            return None


class MentalFitnessLogResponse(_Logged):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    activity_date: datetime
    activity_type: str | None
    duration_minutes: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime | None


class WorkoutLogsListResponse(BaseModel):
    logs: list[WorkoutLogResponse]
    total: int


class NutritionLogsListResponse(BaseModel):
    logs: list[NutritionLogResponse]
    total: int


class MentalFitnessLogsListResponse(BaseModel):
    logs: list[MentalFitnessLogResponse]
    total: int
