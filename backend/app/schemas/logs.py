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

