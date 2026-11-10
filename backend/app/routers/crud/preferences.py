"""The account's preferences (C.8): goals, activity level, exercise types, dietary
restrictions, lifestyle, age and gender.

    GET  /preferences   → the saved preferences, or 404 before the first save
    POST /preferences   → create or update; only the fields sent change
"""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_database
from app.models.user import User
from app.observability.terms import count_saved
from app.routers.errors import ApiError
from app.schemas.preferences import UserPreferencesCreate, UserPreferencesResponse
from app.services.user_service import get_user_preferences, update_user_preferences

log = logging.getLogger(__name__)

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=UserPreferencesResponse)
def get_user_preferences_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
):
    preferences = get_user_preferences(current_user.id, db)
    if preferences is None:
        raise ApiError(404, "not_found", "There are no preferences yet.")
    return preferences


@router.post("", response_model=UserPreferencesResponse, status_code=status.HTTP_200_OK)
def create_or_update_user_preferences(
    preferences_data: UserPreferencesCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
):
    old = get_user_preferences(current_user.id, db)
    before = getattr(old, "dietary_restrictions", None)
    preferences = update_user_preferences(
        user_id=current_user.id, data=preferences_data.model_dump(exclude_none=True), db=db)
    try:  # new unresolved phrases, for the catalogue review (P4.10); never fails the save
        count_saved(db, "dietary_restrictions", before, preferences.dietary_restrictions)
        db.commit()
    except Exception:
        db.rollback()
        log.warning("unresolved terms not counted", exc_info=True)
    return preferences
