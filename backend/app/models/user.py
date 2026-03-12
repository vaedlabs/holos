"""
User model for authentication and user management.

This module defines the User model, which is the central entity in the Holos application.
The User model stores authentication credentials and serves as the parent entity for
all user-related data through SQLAlchemy relationships.

Key Features:
- Authentication fields (email, username, password_hash)
- Account status tracking (is_active)
- Timestamp tracking (created_at, updated_at)
- Relationships to all user-related models (medical history, preferences, logs, etc.)
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    """
    User model representing an authenticated user in the Holos application.
    
    This model stores user authentication information and provides relationships
    to all user-related data including medical history, preferences, workout logs,
    nutrition logs, mental fitness logs, conversation messages, and agent execution logs.
    
    Attributes:
        id: Primary key, auto-incrementing integer
        email: User's email address (unique, indexed, required)
        username: User's chosen username (unique, indexed, required)
        password_hash: Bcrypt hash of user's password (required, never stored in plain text)
        is_active: Boolean flag indicating if account is active (default: True)
        created_at: Timestamp when user account was created (auto-set on insert)
        updated_at: Timestamp when user account was last updated (auto-updated on update)
        
    Relationships:
        medical_history: One-to-one relationship with MedicalHistory
        user_preferences: One-to-one relationship with UserPreferences
        workout_logs: One-to-many relationship with WorkoutLog
        nutrition_logs: One-to-many relationship with NutritionLog
        mental_fitness_logs: One-to-many relationship with MentalFitnessLog
        conversation_messages: One-to-many relationship with ConversationMessage
        agent_execution_logs: One-to-many relationship with AgentExecutionLog
    
    Note:
        - Password is never stored in plain text, only the bcrypt hash
        - Email and username are both unique and indexed for fast lookups
        - Inactive users (is_active=False) cannot authenticate but data is preserved
        - Timestamps use timezone-aware DateTime for accurate time tracking
    """
    __tablename__ = "users"

    # Primary key - auto-incrementing integer
    # Indexed for fast lookups by ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Email address - used for login and account identification
    # Unique constraint ensures one account per email
    # Indexed for fast email-based lookups (login, password reset)
    # Required field - cannot be null
    email = Column(String, unique=True, index=True, nullable=False)
    
    # Username - user's chosen display name
    # Unique constraint ensures usernames are unique across the platform
    # Indexed for fast username-based lookups
    # Required field - cannot be null
    username = Column(String, unique=True, index=True, nullable=False)
    
    # Password hash - bcrypt hash of user's password
    # Never store plain text passwords - always hash before storing
    # Required field - cannot be null
    # Format: bcrypt hash string (includes salt and algorithm info)
    password_hash = Column(String, nullable=False)
    
    # Account status flag - indicates if user account is active
    # Defaults to True (active) when account is created
    # Set to False to disable account without deleting data
    # Used by authentication dependency to prevent inactive users from logging in
    is_active = Column(Boolean, default=True)
    
    # Account creation timestamp
    # Automatically set to current time when user record is created
    # Timezone-aware DateTime for accurate time tracking across timezones
    # Uses database server's current time (func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Account last update timestamp
    # Automatically updated to current time whenever user record is modified
    # Timezone-aware DateTime for accurate time tracking
    # Only updates on actual changes (onupdate=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships to other models
    # These provide convenient access to related data through SQLAlchemy ORM
    
    # One-to-one relationship with MedicalHistory
    # Each user has at most one medical history record
    # uselist=False indicates one-to-one relationship (not one-to-many)
    medical_history = relationship("MedicalHistory", back_populates="user", uselist=False)
    
    # One-to-one relationship with UserPreferences
    # Each user has at most one preferences record
    # uselist=False indicates one-to-one relationship
    user_preferences = relationship("UserPreferences", back_populates="user", uselist=False)
    
    # One-to-many relationship with WorkoutLog
    # Each user can have multiple workout log entries
    # Access via: user.workout_logs (returns list of WorkoutLog objects)
    workout_logs = relationship("WorkoutLog", back_populates="user")
    
    # One-to-many relationship with NutritionLog
    # Each user can have multiple nutrition log entries
    # Access via: user.nutrition_logs (returns list of NutritionLog objects)
    nutrition_logs = relationship("NutritionLog", back_populates="user")
    
    # One-to-many relationship with MentalFitnessLog
    # Each user can have multiple mental fitness log entries
    # Access via: user.mental_fitness_logs (returns list of MentalFitnessLog objects)
    mental_fitness_logs = relationship("MentalFitnessLog", back_populates="user")
    
    # One-to-many relationship with ConversationMessage
    # Each user can have multiple conversation messages with AI agents
    # Access via: user.conversation_messages (returns list of ConversationMessage objects)
    conversation_messages = relationship("ConversationMessage", back_populates="user")
    
    # One-to-many relationship with AgentExecutionLog
    # Each user can have multiple agent execution log entries (for observability)
    # Access via: user.agent_execution_logs (returns list of AgentExecutionLog objects)
    agent_execution_logs = relationship("AgentExecutionLog", back_populates="user")

