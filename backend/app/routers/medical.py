"""
Medical history routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.services.medical_service import get_medical_history, update_medical_history
from app.schemas.medical import MedicalHistoryCreate, MedicalHistoryResponse

router = APIRouter(prefix="/medical", tags=["medical"])


@router.get("/history", response_model=MedicalHistoryResponse)
async def get_medical_history_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Get current user's medical history"""
    medical_history = get_medical_history(current_user.id, db)
    
    if not medical_history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical history not found"
        )
    
    return medical_history


@router.post("/history", response_model=MedicalHistoryResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_medical_history(
    medical_data: MedicalHistoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Create or update medical history for current user"""
    try:
        medical_history = update_medical_history(
            user_id=current_user.id,
            data=medical_data.dict(exclude_none=True),
            db=db
        )
        return medical_history
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update medical history: {str(e)}"
        )

