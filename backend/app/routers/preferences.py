"""
User preferences routes for managing user fitness and wellness preferences.

This module provides FastAPI router endpoints for user preferences management:
- Get user preferences: Retrieve current user's fitness and wellness preferences
- Create or update preferences: Create new preferences or update existing ones

Key Features:
- User preferences management (goals, activity level, dietary restrictions, etc.)
- Partial updates supported (only provided fields are updated)
- Cache invalidation integrated with user service
- Authentication required for all endpoints

User Preferences Include:
- Fitness goals (e.g., weight loss, muscle gain, general fitness)
- Activity level (sedentary, lightly active, moderately active, very active)
- Exercise types (calisthenics, weight lifting, cardio, HIIT, yoga, Pilates)
- Dietary restrictions (vegetarian, vegan, gluten-free, etc.)
- Lifestyle factors (age, gender, lifestyle habits)
- Other preferences relevant to wellness guidance

Security:
- All endpoints require authentication (get_current_user dependency)
- Users can only access and modify their own preferences
- Preferences are user-specific (filtered by user_id)

Cache Integration:
- User preferences are cached via ContextManager
- Cache invalidation occurs on updates (via user_service)
- Ensures agents receive up-to-date preference data
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.services.user_service import get_user_preferences, update_user_preferences
from app.schemas.preferences import UserPreferencesCreate, UserPreferencesResponse

# FastAPI router for user preferences endpoints
# Prefix: /preferences (all routes will be prefixed with /preferences)
# Tags: ["preferences"] (for API documentation grouping)
router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=UserPreferencesResponse)
async def get_user_preferences_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Get current user's preferences.
    
    This endpoint retrieves the authenticated user's fitness and wellness preferences.
    Preferences include goals, activity level, exercise types, dietary restrictions,
    and other factors that influence agent recommendations.
    
    Args:
        current_user: Authenticated user (injected dependency)
                     Ensures users can only access their own preferences
        db: Database session (injected dependency)
    
    Returns:
        UserPreferencesResponse: User preferences data including:
            - goals: str (fitness goals)
            - activity_level: str (activity level)
            - exercise_types: str (preferred exercise types)
            - dietary_restrictions: str (dietary restrictions)
            - lifestyle: str (lifestyle factors)
            - age: Optional[int] (user age)
            - gender: Optional[str] (user gender)
            - Other preference fields
            
    Raises:
        HTTPException 404: If user preferences not found
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only access their own preferences
        
    Cache Integration:
        - Preferences are cached via ContextManager
        - Cache is checked first before database query
        - Reduces database load for frequently accessed preferences
        
    Example:
        GET /preferences
        
        Returns user's preferences or 404 if not found
    """
    # Get user preferences using user service
    # Service handles caching and database queries
    preferences = get_user_preferences(current_user.id, db)
    
    # Check if preferences exist
    # Users may not have set preferences yet
    if not preferences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User preferences not found"
        )
    
    # Return preferences
    return preferences


@router.post("", response_model=UserPreferencesResponse, status_code=status.HTTP_200_OK)
async def create_or_update_user_preferences(
    preferences_data: UserPreferencesCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Create or update user preferences for current user.
    
    This endpoint creates new user preferences or updates existing ones. It supports
    partial updates - only provided fields are updated, existing fields are preserved.
    Preferences are used by agents to provide personalized recommendations.
    
    Update Behavior:
        - If preferences don't exist: Creates new preferences record
        - If preferences exist: Updates existing record with provided fields
        - Partial updates: Only provided fields are updated (exclude_none=True)
        - Existing fields: Preserved if not provided in request
    
    Cache Integration:
        - Cache is invalidated on update (via user_service)
        - Ensures agents receive up-to-date preference data
        - ContextManager cache refreshed on next access
    
    Args:
        preferences_data: UserPreferencesCreate schema containing:
            - goals: Optional[str] (fitness goals)
            - activity_level: Optional[str] (activity level)
            - exercise_types: Optional[str] (preferred exercise types)
            - dietary_restrictions: Optional[str] (dietary restrictions)
            - lifestyle: Optional[str] (lifestyle factors)
            - age: Optional[int] (user age)
            - gender: Optional[str] (user gender)
            - Other optional preference fields
        current_user: Authenticated user (injected dependency)
                     Ensures users can only modify their own preferences
        db: Database session (injected dependency)
    
    Returns:
        UserPreferencesResponse: Updated user preferences data
        
    Raises:
        HTTPException 400: If update fails (validation error, database error)
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only modify their own preferences
        
    Note:
        - exclude_none=True ensures only provided fields are updated
        - Cache invalidation ensures agents see updated preferences immediately
        - Partial updates allow flexible preference management
        
    Example:
        POST /preferences
        {
            "goals": "Weight loss",
            "activity_level": "moderately active",
            "exercise_types": "cardio, weight lifting"
        }
        
        Updates only provided fields, preserves existing fields
    """
    try:
        # Update user preferences using user service
        # Service handles create/update logic and cache invalidation
        preferences = update_user_preferences(
            user_id=current_user.id,  # User ID for user-specific preferences
            data=preferences_data.dict(exclude_none=True),  # Only include provided fields (partial update)
            db=db  # Database session
        )
        return preferences  # Return updated preferences
    except Exception as e:
        # Handle update errors
        # Validation errors, database errors, etc.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update preferences: {str(e)}"
        )


