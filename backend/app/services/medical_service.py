"""
Medical Service - medical history retrieval and updates.

The checks of exercises, foods and practices against a person's conditions are in
app/guardrails/ (rules.yaml, catalogue.yaml), which replaced the conflict table that
was here (Plan B.4).
"""

from typing import Optional
from sqlalchemy.orm import Session
from app.models.medical_history import MedicalHistory


def get_medical_history(user_id: int, db: Session) -> Optional[MedicalHistory]:
    """
    Get medical history for a user.
    
    This function retrieves the medical history record for a specific user.
    Returns None if the user has no medical history on file.
    
    Args:
        user_id: User ID to fetch medical history for
        db: Database session for querying
        
    Returns:
        Optional[MedicalHistory]: Medical history record if exists, None otherwise
        
    Note:
        - Returns None if user has no medical history
        - Used by agents to check medical restrictions
    """
    return db.query(MedicalHistory).filter(MedicalHistory.user_id == user_id).first()


def update_medical_history(user_id: int, data: dict, db: Session) -> MedicalHistory:
    """
    Create or update medical history for a user.
    
    This function creates a new medical history record or updates an existing one.
    Supports partial updates (only updates fields provided in data dictionary).
    
    Args:
        user_id: User ID to create/update medical history for
        data: Dictionary with medical history fields:
              - conditions: Medical conditions (optional)
              - limitations: Physical limitations (optional)
              - medications: Current medications (optional)
              - notes: Additional medical notes (optional)
        db: Database session for persistence
        
    Returns:
        MedicalHistory: Created or updated medical history record
        
    Update Logic:
        - If medical history exists: Updates only provided fields (partial update)
        - If medical history doesn't exist: Creates new record with provided fields
        
    Note:
        - Supports partial updates (only updates fields in data)
        - Commits changes to database
    """
    medical_history = get_medical_history(user_id, db)
    
    if medical_history:
        # Update existing medical history record
        # Only update fields that are provided (partial update)
        if "conditions" in data:
            medical_history.conditions = data["conditions"]
        if "limitations" in data:
            medical_history.limitations = data["limitations"]
        if "medications" in data:
            medical_history.medications = data["medications"]
        if "notes" in data:
            medical_history.notes = data["notes"]
    else:
        # Create new medical history record
        medical_history = MedicalHistory(
            user_id=user_id,
            conditions=data.get("conditions"),
            limitations=data.get("limitations"),
            medications=data.get("medications"),
            notes=data.get("notes")
        )
        db.add(medical_history)
    
    # Persist changes to database
    db.commit()
    db.refresh(medical_history)
    return medical_history
