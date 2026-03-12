"""
Database models package.

This module exports all SQLAlchemy ORM models for the Holos application.
Models define database tables, relationships, and constraints.

Exported Models:
    - User: User accounts and authentication
    - MedicalHistory: Medical conditions and exercise conflicts
    - UserPreferences: Fitness and wellness preferences (goals, demographics)
    - WorkoutLog: Exercise tracking and workout history
    - NutritionLog: Meal tracking and nutrition history
    - MentalFitnessLog: Wellness activity tracking (meditation, stress management)
    - ConversationMessage: Chat history between users and AI agents
    - AgentExecutionLog: Agent execution traces (observability, debugging)

Usage:
    from app.models import User, WorkoutLog
    
    # Models are used by SQLAlchemy for database operations
    # Imported here to ensure they're registered with Base.metadata
    # (required for Alembic migrations and create_all())
"""

from app.models.user import User
from app.models.medical_history import MedicalHistory
from app.models.user_preferences import UserPreferences
from app.models.workout_log import WorkoutLog
from app.models.nutrition_log import NutritionLog
from app.models.mental_fitness_log import MentalFitnessLog
from app.models.conversation_message import ConversationMessage
from app.models.agent_execution_log import AgentExecutionLog

# Export all models for convenient importing
# Makes models available via: from app.models import User, WorkoutLog
__all__ = [
    "User",  # User accounts and authentication
    "MedicalHistory",  # Medical conditions and exercise conflicts
    "UserPreferences",  # Fitness and wellness preferences
    "WorkoutLog",  # Exercise tracking
    "NutritionLog",  # Meal tracking
    "MentalFitnessLog",  # Wellness activity tracking
    "ConversationMessage",  # Chat history
    "AgentExecutionLog"  # Agent execution traces
]
