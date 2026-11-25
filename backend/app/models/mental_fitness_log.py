"""
Mental Fitness Log model for tracking user mental wellness activities.

This module defines the MentalFitnessLog model, which stores records of user
mental wellness activities such as meditation, mindfulness, journaling, and
breathing exercises. The model has a many-to-one relationship with the User model,
allowing users to log multiple mental fitness activities over time.

Key Features:
- Activity type categorization
- Duration tracking
- Activity date and timestamp tracking
- Notes for additional activity information
"""

from sqlalchemy import JSON, Column, Integer, String, Text, ForeignKey, DateTime, Float, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class MentalFitnessLog(Base):
    """
    Mental Fitness Log model storing user mental wellness activity records.
    
    This model stores individual mental wellness activities completed by users.
    Each log entry represents a single activity session with details about the
    activity type and duration. The model has a many-to-one
    relationship with User model.
    
    Attributes:
        id: Primary key, auto-incrementing integer
        user_id: Foreign key to User model (required)
        activity_date: Date and time when activity was performed (timezone-aware)
        activity_type: Type of mental wellness activity
        duration_minutes: Duration of activity in minutes (Float for partial minutes)
        notes: Additional notes about the activity (free-form text)
        created_at: Timestamp when log entry was created
        updated_at: Timestamp when log entry was last updated
        
    Relationships:
        user: Many-to-one relationship with User model
        
    Activity Types:
        Common activity types include:
        - "meditation": Meditation sessions
        - "mindfulness": Mindfulness practices
        - "journaling": Journaling activities
        - "breathing_exercises": Breathing exercises
        - "yoga": Yoga sessions (mental wellness focus)
        - "gratitude_practice": Gratitude exercises
        - "stress_management": Stress management activities
        
    Note:
        - Multiple mental fitness logs can exist per user (many-to-one relationship)
        - Activity type helps categorize activities for analysis and recommendations
        - Duration can be fractional (e.g., 15.5 minutes)
        - Activity date defaults to current time but can be set to past dates
        - Used by Mental Fitness Agent to track patterns and provide recommendations
    """
    __tablename__ = "mental_fitness_logs"
    # Composite index from migration cd5e821b7af6 (user-scoped, date-ordered queries)
    __table_args__ = (Index("idx_mental_fitness_log_user_date", "user_id", "activity_date"),)

    # Primary key - auto-incrementing integer
    # Indexed for fast lookups by ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key to User model
    # Many-to-one relationship (each user can have multiple mental fitness logs)
    # Required field - cannot be null
    # Indexed for fast queries filtering by user
    # Cascade delete: if user is deleted, mental fitness logs are also deleted
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Activity date and time - when the activity was performed
    # Timezone-aware DateTime for accurate time tracking across timezones
    # Defaults to current time when log entry is created
    # Can be set to past dates for logging activities retroactively
    # Required field - cannot be null
    activity_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Activity type - category of the mental wellness activity
    # Examples: "meditation", "mindfulness", "journaling", "breathing_exercises", "yoga"
    # Used for categorizing activities and generating statistics
    # Helps agents understand user's mental wellness preferences and patterns
    # Nullable to allow flexibility, but recommended for better tracking
    activity_type = Column(String, nullable=True)  # meditation, mindfulness, journaling, etc.
    
    # Duration - length of activity in minutes
    # Float type allows fractional minutes (e.g., 15.5 minutes)
    # Used for tracking activity volume and generating statistics
    # Helps agents understand user's commitment to mental wellness practices
    # Nullable to allow activities without duration tracking
    duration_minutes = Column(Float, nullable=True)
    
    # Notes - additional information about the activity
    # Format: Free-form text for any additional context
    # Examples: "Felt more focused", "Difficult to concentrate", "Best session this week"
    # Provides flexibility for users to add context to their activities
    # Used by agents to understand activity context and user feedback
    # Nullable to allow activities without notes
    notes = Column(Text, nullable=True)

    # What in the entry conflicted with the profile when it was logged, and whether the
    # person left it out: a list of WriteWarning (Plan C.17, Part E #45). Null: none
    warnings = Column(JSON, nullable=True)
    
    # Log entry creation timestamp
    # Automatically set to current time when log entry is created
    # Timezone-aware DateTime for accurate time tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Log entry last update timestamp
    # Automatically updated to current time whenever log entry is modified
    # Timezone-aware DateTime for accurate time tracking
    # Only updates on actual changes (onupdate=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to User model
    # Many-to-one relationship (each user can have multiple mental fitness logs)
    # Access via: mental_fitness_log.user (returns User object)
    # Back-populates with User.mental_fitness_logs (returns list of MentalFitnessLog objects)
    user = relationship("User", back_populates="mental_fitness_logs")

