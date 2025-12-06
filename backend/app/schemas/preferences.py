"""
User preferences schemas
"""

from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class UserPreferencesCreate(BaseModel):
    """Schema for creating/updating user preferences"""
    goals: Optional[str] = None
    exercise_types: Optional[str] = None
    activity_level: Optional[str] = None
    location: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    lifestyle: Optional[str] = None

    @field_validator('age')
    @classmethod
    def validate_age(cls, v):
        if v is not None:
            if not isinstance(v, int) or v < 13 or v > 120:
                raise ValueError('Age must be between 13 and 120')
        return v

    @field_validator('gender')
    @classmethod
    def validate_gender(cls, v):
        if v is not None:
            valid_genders = ['XX', 'XY', 'other']
            if v not in valid_genders:
                raise ValueError(f'Gender must be one of: {", ".join(valid_genders)}')
        return v


class UserPreferencesResponse(BaseModel):
    """Schema for user preferences response"""
    id: int
    user_id: int
    goals: Optional[str]
    exercise_types: Optional[str]
    activity_level: Optional[str]
    location: Optional[str]
    dietary_restrictions: Optional[str]
    age: Optional[int]
    gender: Optional[str]
    lifestyle: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


