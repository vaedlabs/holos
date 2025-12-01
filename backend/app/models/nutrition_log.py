"""
Nutrition Log model
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class NutritionLog(Base):
    __tablename__ = "nutrition_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Meal details
    meal_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    meal_type = Column(String, nullable=True)  # breakfast, lunch, dinner, snack
    foods = Column(Text, nullable=True)  # JSON string with food items and details
    calories = Column(Float, nullable=True)  # Total calories
    macros = Column(Text, nullable=True)  # JSON string with protein, carbs, fats
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    user = relationship("User", back_populates="nutrition_logs")

