"""
Mental Fitness Log model
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class MentalFitnessLog(Base):
    __tablename__ = "mental_fitness_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Activity details
    activity_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    activity_type = Column(String, nullable=True)  # meditation, mindfulness, journaling, etc.
    duration_minutes = Column(Float, nullable=True)
    mood_before = Column(String, nullable=True)  # Scale or description
    mood_after = Column(String, nullable=True)  # Scale or description
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    user = relationship("User", back_populates="mental_fitness_logs")

