"""The account's medical history (C.8): conditions, limitations, medications, notes.

    GET  /medical/history   → the saved history, or 404 before the first save
    POST /medical/history   → create or update; only the fields sent change

The gate reads conditions and limitations through `storage/profile.py` on every chat
turn, so a save takes effect on the next message.
"""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_database
from app.models.user import User
from app.observability.terms import count_saved
from app.routers.errors import ApiError
from app.schemas.medical import MedicalHistoryCreate, MedicalHistoryResponse
from app.services.medical_service import get_medical_history, update_medical_history

log = logging.getLogger(__name__)

router = APIRouter(prefix="/medical", tags=["medical"])


@router.get("/history", response_model=MedicalHistoryResponse)
def get_medical_history_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
):
    medical_history = get_medical_history(current_user.id, db)
    if medical_history is None:
        raise ApiError(404, "not_found", "There is no medical history yet.")
    return medical_history


@router.post("/history", response_model=MedicalHistoryResponse,
             status_code=status.HTTP_201_CREATED)
def create_or_update_medical_history(
    medical_data: MedicalHistoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
):
    old = get_medical_history(current_user.id, db)
    before = {f: getattr(old, f, None) for f in ("conditions", "limitations")}
    medical_history = update_medical_history(
        user_id=current_user.id, data=medical_data.model_dump(exclude_none=True), db=db)
    _count_unresolved(db, before, medical_history)
    return medical_history


def _count_unresolved(db: Session, before: dict, saved) -> None:
    """New phrases that name nothing, for the owner's catalogue review (P4.10). A
    counting failure never fails the save."""
    try:
        for field, old in before.items():
            count_saved(db, field, old, getattr(saved, field, None))
        db.commit()
    except Exception:
        db.rollback()
        log.warning("unresolved terms not counted", exc_info=True)
