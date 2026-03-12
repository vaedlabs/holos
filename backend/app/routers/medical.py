"""
Medical history routes for managing user medical information.

This module provides FastAPI router endpoints for medical history management:
- Get medical history: Retrieve current user's medical history
- Create or update medical history: Create new medical history or update existing one

Key Features:
- Medical history management (conditions, medications, limitations, notes)
- Partial updates supported (only provided fields are updated)
- Critical for agent safety checks (exercise conflict detection, dietary restrictions)
- Cache integration for efficient agent access

Medical History Includes:
- Medical conditions (e.g., heart disease, diabetes, back injury, knee pain)
- Medications (current medications that may affect exercise or nutrition)
- Physical limitations (mobility restrictions, joint issues, etc.)
- Medical notes (additional context, doctor's recommendations, etc.)

Safety Integration:
- Medical history is used by agents for safety checks
- Physical Fitness Agent: Checks exercise conflicts with medical conditions
- Nutrition Agent: Checks dietary restrictions and medication interactions
- Mental Fitness Agent: Considers mental health conditions and medications
- Exercise conflict detection uses severity levels (BLOCK vs WARNING)

Security:
- All endpoints require authentication (get_current_user dependency)
- Users can only access and modify their own medical history
- Medical history is user-specific (filtered by user_id)
- Sensitive medical information requires proper authentication

Cache Integration:
- Medical history is cached via ContextManager
- Cache invalidation occurs on updates (via medical_service)
- Ensures agents receive up-to-date medical data for safety checks
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.services.medical_service import get_medical_history, update_medical_history
from app.schemas.medical import MedicalHistoryCreate, MedicalHistoryResponse

# FastAPI router for medical history endpoints
# Prefix: /medical (all routes will be prefixed with /medical)
# Tags: ["medical"] (for API documentation grouping)
router = APIRouter(prefix="/medical", tags=["medical"])


@router.get("/history", response_model=MedicalHistoryResponse)
async def get_medical_history_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Get current user's medical history.
    
    This endpoint retrieves the authenticated user's medical history, including
    conditions, medications, limitations, and notes. Medical history is critical
    for agent safety checks and personalized recommendations.
    
    Medical History Usage:
        - Physical Fitness Agent: Checks exercise conflicts with medical conditions
        - Nutrition Agent: Checks dietary restrictions and medication interactions
        - Mental Fitness Agent: Considers mental health conditions and medications
        - Exercise conflict detection uses severity levels (BLOCK vs WARNING)
    
    Args:
        current_user: Authenticated user (injected dependency)
                     Ensures users can only access their own medical history
        db: Database session (injected dependency)
    
    Returns:
        MedicalHistoryResponse: Medical history data including:
            - conditions: str (medical conditions)
            - medications: str (current medications)
            - limitations: str (physical limitations)
            - notes: Optional[str] (additional medical notes)
            
    Raises:
        HTTPException 404: If medical history not found
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only access their own medical history
        - Sensitive medical information requires proper authentication
        
    Cache Integration:
        - Medical history is cached via ContextManager
        - Cache is checked first before database query
        - Reduces database load for frequently accessed medical data
        
    Example:
        GET /medical/history
        
        Returns user's medical history or 404 if not found
    """
    # Get medical history using medical service
    # Service handles caching and database queries
    medical_history = get_medical_history(current_user.id, db)
    
    # Check if medical history exists
    # Users may not have set medical history yet
    if not medical_history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical history not found"
        )
    
    # Return medical history
    return medical_history


@router.post("/history", response_model=MedicalHistoryResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_medical_history(
    medical_data: MedicalHistoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Create or update medical history for current user.
    
    This endpoint creates new medical history or updates existing one. It supports
    partial updates - only provided fields are updated, existing fields are preserved.
    Medical history is critical for agent safety checks and personalized recommendations.
    
    Update Behavior:
        - If medical history doesn't exist: Creates new medical history record
        - If medical history exists: Updates existing record with provided fields
        - Partial updates: Only provided fields are updated (exclude_none=True)
        - Existing fields: Preserved if not provided in request
    
    Safety Impact:
        - Medical history updates immediately affect agent safety checks
        - Exercise conflict detection uses updated conditions and limitations
        - Dietary restriction checks use updated medications and conditions
        - Cache invalidation ensures agents see updated medical data immediately
    
    Cache Integration:
        - Cache is invalidated on update (via medical_service)
        - Ensures agents receive up-to-date medical data for safety checks
        - ContextManager cache refreshed on next access
    
    Args:
        medical_data: MedicalHistoryCreate schema containing:
            - conditions: Optional[str] (medical conditions)
            - medications: Optional[str] (current medications)
            - limitations: Optional[str] (physical limitations)
            - notes: Optional[str] (additional medical notes)
        current_user: Authenticated user (injected dependency)
                     Ensures users can only modify their own medical history
        db: Database session (injected dependency)
    
    Returns:
        MedicalHistoryResponse: Updated medical history data
        
    Raises:
        HTTPException 400: If update fails (validation error, database error)
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only modify their own medical history
        - Sensitive medical information requires proper authentication
        
    Note:
        - exclude_none=True ensures only provided fields are updated
        - Cache invalidation ensures agents see updated medical data immediately
        - Partial updates allow flexible medical history management
        - Medical history is critical for safety - updates affect agent recommendations
        
    Example:
        POST /medical/history
        {
            "conditions": "Heart disease, back injury",
            "medications": "Blood pressure medication",
            "limitations": "Avoid high-impact exercises"
        }
        
        Updates only provided fields, preserves existing fields
    """
    try:
        # Update medical history using medical service
        # Service handles create/update logic and cache invalidation
        medical_history = update_medical_history(
            user_id=current_user.id,  # User ID for user-specific medical history
            data=medical_data.dict(exclude_none=True),  # Only include provided fields (partial update)
            db=db  # Database session
        )
        return medical_history  # Return updated medical history
    except Exception as e:
        # Handle update errors
        # Validation errors, database errors, etc.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update medical history: {str(e)}"
        )

