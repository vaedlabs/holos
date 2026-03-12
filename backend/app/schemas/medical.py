"""
Medical history schemas for request/response validation.

This module defines Pydantic schemas for medical history endpoints. These schemas
provide request/response validation, serialization, and documentation for managing
user medical information.

IMPORTANT SAFETY CONSIDERATIONS:
- Medical data is used by AI agents to prevent unsafe exercise/nutrition recommendations
- This data should be kept confidential and secure (HIPAA considerations)
- All fields are optional to allow users to provide information incrementally
- This is NOT a replacement for professional medical advice

Key Features:
- Medical history create/update schema (supports partial updates)
- Medical history response schema (includes all medical fields)
- All fields are optional to support incremental updates
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class MedicalHistoryCreate(BaseModel):
    """
    Medical history create/update schema for managing user medical information.
    
    This schema validates input data when creating or updating medical history.
    All fields are optional to support partial updates - users can update individual
    medical information without providing all fields.
    
    CRITICAL: This data is used by AI agents to prevent recommending unsafe exercises
    or foods. Agents MUST check this data before making recommendations.
    
    Attributes:
        conditions: Medical conditions (JSON string or comma-separated, optional)
        limitations: Physical limitations or restrictions (optional)
        medications: Current medications (optional)
        notes: Additional medical notes or information (optional)
        
    Field Formats:
        - conditions: "diabetes,hypertension" or JSON array string
        - limitations: Free-form text describing physical restrictions
        - medications: Free-form text listing medications and dosages
        - notes: Free-form text for additional medical context
        
    Safety Usage:
        - Physical Fitness Agent checks conditions and limitations before recommending exercises
        - Nutrition Agent checks medications for potential food interactions
        - All agents use this data to avoid harmful recommendations
        
    Note:
        - All fields are optional to allow partial updates
        - Empty strings are treated as None (no update)
        - Used for both creating new medical history and updating existing records
        - Medical information should be kept confidential
        - Users should consult healthcare providers for medical advice
    """
    conditions: Optional[str] = None
    limitations: Optional[str] = None
    medications: Optional[str] = None
    notes: Optional[str] = None


class MedicalHistoryResponse(BaseModel):
    """
    Medical history response schema for returning medical information.
    
    This schema defines what medical information is returned to clients.
    Includes all medical fields plus metadata (id, user_id, timestamps).
    
    CRITICAL: Medical information should be kept confidential. This schema is used
    to return medical data to authenticated users only.
    
    Attributes:
        id: Medical history record unique identifier (primary key)
        user_id: Foreign key to User model
        conditions: Medical conditions (optional)
        limitations: Physical limitations or restrictions (optional)
        medications: Current medications (optional)
        notes: Additional medical notes (optional)
        created_at: Timestamp when medical history was created
        updated_at: Timestamp when medical history was last updated (optional)
        
    Security:
        - Only accessible to authenticated users
        - Users can only access their own medical history
        - Medical data should be encrypted in transit (HTTPS)
        
    Config:
        from_attributes = True: Allows creating schema from SQLAlchemy model
        This enables automatic conversion from MedicalHistory model to response schema
        
    Note:
        - Used in endpoints that return medical history
        - Automatically serializes datetime to ISO format string
        - Can be created directly from MedicalHistory model using from_attributes
        - All medical fields are optional (users may not have provided all information)
    """
    id: int
    user_id: int
    conditions: Optional[str]
    limitations: Optional[str]
    medications: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        # Enable creating schema instance from SQLAlchemy model attributes
        # This allows: MedicalHistoryResponse.from_orm(medical_history_model_instance)
        from_attributes = True

