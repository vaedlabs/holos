"""
User preferences routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.services.user_service import get_user_preferences, update_user_preferences
from app.schemas.preferences import UserPreferencesCreate, UserPreferencesResponse

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=UserPreferencesResponse)
async def get_user_preferences_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Get current user's preferences"""
    preferences = get_user_preferences(current_user.id, db)
    
    if not preferences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User preferences not found"
        )
    
    return preferences


@router.post("", response_model=UserPreferencesResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_user_preferences(
    preferences_data: UserPreferencesCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Create or update user preferences for current user"""
    try:
        preferences = update_user_preferences(
            user_id=current_user.id,
            data=preferences_data.dict(exclude_none=True),
            db=db
        )
        return preferences
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update preferences: {str(e)}"
        )


