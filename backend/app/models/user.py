"""
User model for authentication
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    medical_history = relationship("MedicalHistory", back_populates="user", uselist=False)
    user_preferences = relationship("UserPreferences", back_populates="user", uselist=False)
    workout_logs = relationship("WorkoutLog", back_populates="user")
    nutrition_logs = relationship("NutritionLog", back_populates="user")
    mental_fitness_logs = relationship("MentalFitnessLog", back_populates="user")
    conversation_messages = relationship("ConversationMessage", back_populates="user")
    agent_execution_logs = relationship("AgentExecutionLog", back_populates="user")

