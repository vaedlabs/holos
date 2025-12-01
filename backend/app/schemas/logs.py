"""
Workout log schemas
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class WorkoutLogResponse(BaseModel):
    """Schema for workout log response"""
    id: int
    user_id: int
    workout_date: datetime
    exercise_type: Optional[str]
    exercises: Optional[str]
    duration_minutes: Optional[float]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class WorkoutLogsListResponse(BaseModel):
    """Schema for list of workout logs"""
    logs: List[WorkoutLogResponse]
    total: int


class NutritionLogResponse(BaseModel):
    """Schema for nutrition log response"""
    id: int
    user_id: int
    meal_date: datetime
    meal_type: Optional[str]
    foods: Optional[str]  # JSON string
    calories: Optional[float]
    macros: Optional[str]  # JSON string
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class NutritionLogsListResponse(BaseModel):
    """Schema for list of nutrition logs"""
    logs: List[NutritionLogResponse]
    total: int


class MentalFitnessLogResponse(BaseModel):
    """Schema for mental fitness log response"""
    id: int
    user_id: int
    activity_date: datetime
    activity_type: Optional[str]
    duration_minutes: Optional[float]
    mood_before: Optional[str]
    mood_after: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class MentalFitnessLogsListResponse(BaseModel):
    """Schema for list of mental fitness logs"""
    logs: List[MentalFitnessLogResponse]
    total: int

