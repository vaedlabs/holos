"""
User preferences schemas
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserPreferencesCreate(BaseModel):
    """Schema for creating/updating user preferences"""
    goals: Optional[str] = None
    exercise_types: Optional[str] = None
    activity_level: Optional[str] = None
    location: Optional[str] = None
    dietary_restrictions: Optional[str] = None


class UserPreferencesResponse(BaseModel):
    """Schema for user preferences response"""
    id: int
    user_id: int
    goals: Optional[str]
    exercise_types: Optional[str]
    activity_level: Optional[str]
    location: Optional[str]
    dietary_restrictions: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


