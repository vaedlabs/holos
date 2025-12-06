"""
User Preferences model
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Fitness goals
    goals = Column(Text, nullable=True)  # JSON string or comma-separated goals
    
    # Dietary restrictions
    dietary_restrictions = Column(Text, nullable=True)  # JSON string or comma-separated
    
    # Location
    location = Column(String, nullable=True)  # City, address, or coordinates
    
    # Exercise preferences
    exercise_types = Column(Text, nullable=True)  # JSON string or comma-separated: calisthenics, weight_lifting, cardio, etc.
    
    # Activity level
    activity_level = Column(String, nullable=True)  # sedentary, light, moderate, active, very_active
    
    # Demographics
    age = Column(Integer, nullable=True)  # User's age (13-120)
    gender = Column(String, nullable=True)  # XX, XY, other, or null
    lifestyle = Column(String, nullable=True)  # sedentary, active, very_active, athlete (can overlap with activity_level but provides more context)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    user = relationship("User", back_populates="user_preferences")

