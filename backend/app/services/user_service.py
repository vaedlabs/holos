"""
User Service - Handles user preferences management.

This module provides user preferences management functionality, including
retrieval and updates. User preferences are used by agents to personalize
recommendations (exercises, meals, etc.).

Key Features:
- User preferences retrieval
- User preferences creation and updates
- Partial update support (only update provided fields)
- Integration with context manager for caching

Preference Fields:
- goals: User fitness/health goals
- exercise_types: Preferred exercise types
- activity_level: Current activity level
- location: User location (for weather-based recommendations)
- dietary_restrictions: Dietary restrictions/preferences
- age: User age (for age-appropriate recommendations)
- gender: User gender (for personalized recommendations)
- lifestyle: Lifestyle factors (work schedule, etc.)

Usage:
- Used by agents to personalize recommendations
- Cached by ContextManager to avoid redundant queries
- Should invalidate context cache after updates
"""

from typing import Optional
from sqlalchemy.orm import Session
from app.models.user_preferences import UserPreferences


def get_user_preferences(user_id: int, db: Session) -> Optional[UserPreferences]:
    """
    Get user preferences for a user.
    
    This function retrieves the user preferences record for a specific user.
    Returns None if the user has no preferences on file.
    
    Args:
        user_id: User ID to fetch preferences for
        db: Database session for querying
        
    Returns:
        Optional[UserPreferences]: User preferences record if exists, None otherwise
        
    Preference Fields:
        - goals: Fitness/health goals
        - exercise_types: Preferred exercise types
        - activity_level: Current activity level
        - location: User location
        - dietary_restrictions: Dietary restrictions/preferences
        - age: User age
        - gender: User gender
        - lifestyle: Lifestyle factors
        
    Note:
        - Returns None if user has no preferences
        - Used by agents to personalize recommendations
        - Cached by ContextManager to avoid redundant queries
    """
    return db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()


def update_user_preferences(user_id: int, data: dict, db: Session) -> UserPreferences:
    """
    Create or update user preferences for a user.
    
    This function creates a new user preferences record or updates an existing one.
    Supports partial updates (only updates fields provided in data dictionary).
    
    Args:
        user_id: User ID to create/update preferences for
        data: Dictionary with preference fields (all optional):
              - goals: Fitness/health goals (optional)
              - exercise_types: Preferred exercise types (optional)
              - activity_level: Current activity level (optional)
              - location: User location (optional)
              - dietary_restrictions: Dietary restrictions/preferences (optional)
              - age: User age (optional)
              - gender: User gender (optional)
              - lifestyle: Lifestyle factors (optional)
        db: Database session for persistence
        
    Returns:
        UserPreferences: Created or updated user preferences record
        
    Update Logic:
        - If preferences exist: Updates only provided fields (partial update)
        - If preferences don't exist: Creates new record with provided fields
        
    Partial Updates:
        - Only fields present in data dictionary are updated
        - Fields not in data dictionary remain unchanged
        - Allows updating individual fields without affecting others
        
    Cache Invalidation:
        - Should invalidate context cache after update
        - Call context_manager.invalidate_cache(user_id) after update
        - Ensures agents get fresh preferences on next request
        
    Note:
        - Supports partial updates (only update fields in data)
        - Commits changes to database
        - Should invalidate context cache after update
        - Used by API endpoints for preference management
    """
    # Get existing preferences (if any)
    preferences = get_user_preferences(user_id, db)
    
    if preferences:
        # Update existing preferences record
        # Only update fields that are provided (partial update)
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
        # Create new preferences record
        # Use data.get() to handle missing fields gracefully
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
    
    # Persist changes to database
    db.commit()
    db.refresh(preferences)
    return preferences


