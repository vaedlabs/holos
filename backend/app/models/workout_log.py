"""
Workout Log model
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class WorkoutLog(Base):
    __tablename__ = "workout_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Workout details
    workout_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    exercise_type = Column(String, nullable=True)  # calisthenics, weight_lifting, cardio, etc.
    exercises = Column(Text, nullable=True)  # JSON string with exercise details
    duration_minutes = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    user = relationship("User", back_populates="workout_logs")

