"""
Workout Log model for tracking user exercise activities.

This module defines the WorkoutLog model, which stores records of user workouts
and exercise activities. The model has a many-to-one relationship with the User model,
allowing users to log multiple workout sessions over time.

Key Features:
- Exercise type categorization
- Structured exercise details (JSON format)
- Duration tracking
- Workout date and timestamp tracking
- Notes for additional workout information
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class WorkoutLog(Base):
    """
    Workout Log model storing user exercise activity records.
    
    This model stores individual workout sessions completed by users. Each log entry
    represents a single workout session with details about exercises performed,
    duration, and type. The model has a many-to-one relationship with User model.
    
    Attributes:
        id: Primary key, auto-incrementing integer
        user_id: Foreign key to User model (required)
        workout_date: Date and time when workout was performed (timezone-aware)
        exercise_type: Category of exercise (calisthenics, weight_lifting, cardio, etc.)
        exercises: Structured exercise details in JSON format
        duration_minutes: Duration of workout in minutes (Float for partial minutes)
        notes: Additional notes about the workout (free-form text)
        created_at: Timestamp when log entry was created
        updated_at: Timestamp when log entry was last updated
        
    Relationships:
        user: Many-to-one relationship with User model
        
    JSON Format (exercises field):
        The exercises field stores structured data as JSON string. Example format:
        {
            "exercises": [
                {
                    "name": "Push-ups",
                    "sets": 3,
                    "reps": 15,
                    "weight": null,
                    "rest_seconds": 60
                },
                {
                    "name": "Squats",
                    "sets": 3,
                    "reps": 20,
                    "weight": null,
                    "rest_seconds": 90
                }
            ]
        }
        
        Or simpler format:
        {
            "exercises": [
                {"name": "Running", "distance_km": 5.0, "pace_min_per_km": 6.0},
                {"name": "Stretching", "duration_minutes": 10}
            ]
        }
        
    Note:
        - Multiple workout logs can exist per user (many-to-one relationship)
        - Exercise type helps categorize workouts for analysis and recommendations
        - JSON format allows flexible exercise data structure
        - Duration can be fractional (e.g., 30.5 minutes)
        - Workout date defaults to current time but can be set to past dates
    """
    __tablename__ = "workout_logs"

    # Primary key - auto-incrementing integer
    # Indexed for fast lookups by ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key to User model
    # Many-to-one relationship (each user can have multiple workout logs)
    # Required field - cannot be null
    # Indexed for fast queries filtering by user
    # Cascade delete: if user is deleted, workout logs are also deleted
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Workout date and time - when the workout was performed
    # Timezone-aware DateTime for accurate time tracking across timezones
    # Defaults to current time when log entry is created
    # Can be set to past dates for logging workouts retroactively
    # Required field - cannot be null
    workout_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Exercise type - category of the workout
    # Examples: "calisthenics", "weight_lifting", "cardio", "yoga", "swimming", "running"
    # Used for categorizing workouts and generating statistics
    # Helps agents understand user's exercise preferences and patterns
    # Nullable to allow flexibility, but recommended for better tracking
    exercise_type = Column(String, nullable=True)  # calisthenics, weight_lifting, cardio, etc.
    
    # Exercises - structured details of exercises performed
    # Format: JSON string containing array of exercise objects
    # Each exercise object can include: name, sets, reps, weight, rest_seconds, etc.
    # Flexible JSON structure allows different exercise types to have different fields
    # Example: {"exercises": [{"name": "Push-ups", "sets": 3, "reps": 15}]}
    # Used by agents to analyze workout patterns and provide recommendations
    # Nullable to allow simple workout logs without detailed exercise breakdown
    exercises = Column(Text, nullable=True)  # JSON string with exercise details
    
    # Duration - length of workout in minutes
    # Float type allows fractional minutes (e.g., 30.5 minutes)
    # Used for tracking workout volume and generating statistics
    # Helps agents understand user's activity level and workout intensity
    # Nullable to allow workouts without duration tracking
    duration_minutes = Column(Float, nullable=True)
    
    # Notes - additional information about the workout
    # Format: Free-form text for any additional context
    # Examples: "Felt strong today", "Increased weight", "Post-workout fatigue"
    # Provides flexibility for users to add context to their workouts
    # Used by agents to understand workout context and user feedback
    # Nullable to allow workouts without notes
    notes = Column(Text, nullable=True)
    
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
    # Many-to-one relationship (each user can have multiple workout logs)
    # Access via: workout_log.user (returns User object)
    # Back-populates with User.workout_logs (returns list of WorkoutLog objects)
    user = relationship("User", back_populates="workout_logs")

