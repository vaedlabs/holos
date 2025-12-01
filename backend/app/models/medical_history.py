"""
Medical History model
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class MedicalHistory(Base):
    __tablename__ = "medical_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Medical information
    conditions = Column(Text, nullable=True)  # JSON string or comma-separated
    limitations = Column(Text, nullable=True)  # Physical limitations
    medications = Column(Text, nullable=True)  # Current medications
    notes = Column(Text, nullable=True)  # Additional notes
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    user = relationship("User", back_populates="medical_history")

