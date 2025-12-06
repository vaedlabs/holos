"""
User service - Handles user preferences
"""

from typing import Optional
from sqlalchemy.orm import Session
from app.models.user_preferences import UserPreferences


def get_user_preferences(user_id: int, db: Session) -> Optional[UserPreferences]:
    """Get user preferences for a user"""
    return db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()


def update_user_preferences(user_id: int, data: dict, db: Session) -> UserPreferences:
    """Create or update user preferences for a user"""
    preferences = get_user_preferences(user_id, db)
    
    if preferences:
        # Update existing
        if "goals" in data:
            preferences.goals = data["goals"]
        if "exercise_types" in data:
            preferences.exercise_types = data["exercise_types"]
        if "activity_level" in data:
            preferences.activity_level = data["activity_level"]
        if "location" in data:
            preferences.location = data["location"]
        if "dietary_restrictions" in data:
            preferences.dietary_restrictions = data["dietary_restrictions"]
        if "age" in data:
            preferences.age = data["age"]
        if "gender" in data:
            preferences.gender = data["gender"]
        if "lifestyle" in data:
            preferences.lifestyle = data["lifestyle"]
    else:
        # Create new
        preferences = UserPreferences(
            user_id=user_id,
            goals=data.get("goals"),
            exercise_types=data.get("exercise_types"),
            activity_level=data.get("activity_level"),
            location=data.get("location"),
            dietary_restrictions=data.get("dietary_restrictions"),
            age=data.get("age"),
            gender=data.get("gender"),
            lifestyle=data.get("lifestyle")
        )
        db.add(preferences)
    
    db.commit()
    db.refresh(preferences)
    return preferences


