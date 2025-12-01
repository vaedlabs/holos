"""
Medical history schemas
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class MedicalHistoryCreate(BaseModel):
    """Schema for creating/updating medical history"""
    conditions: Optional[str] = None
    limitations: Optional[str] = None
    medications: Optional[str] = None
    notes: Optional[str] = None


class MedicalHistoryResponse(BaseModel):
    """Schema for medical history response"""
    id: int
    user_id: int
    conditions: Optional[str]
    limitations: Optional[str]
    medications: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

