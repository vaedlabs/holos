"""
User Preferences model for storing user fitness and lifestyle preferences.

This module defines the UserPreferences model, which stores user-specific preferences
and demographic information used by AI agents to provide personalized recommendations.
The model has a one-to-one relationship with the User model.

Key Features:
- Fitness goals and exercise preferences
- Dietary restrictions and location information
- Activity level and lifestyle information
- Demographic data (age, gender)
- Timestamp tracking for preferences updates
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class UserPreferences(Base):
    """
    User Preferences model storing user fitness and lifestyle preferences.
    
    This model stores all user-specific information that AI agents use to provide
    personalized recommendations. Each user has exactly one preferences record
    (one-to-one relationship with User model).
    
    Attributes:
        id: Primary key, auto-incrementing integer
        user_id: Foreign key to User model (unique, one-to-one relationship)
        goals: User's fitness goals (JSON string or comma-separated)
        dietary_restrictions: Dietary restrictions/allergies (JSON string or comma-separated)
        location: User's location (city, address, or coordinates) for geographic recommendations
        exercise_types: Preferred exercise types (JSON string or comma-separated)
        activity_level: Current activity level (sedentary, light, moderate, active, very_active)
        age: User's age (13-120, nullable)
        gender: User's gender (XX, XY, other, or null)
        lifestyle: Lifestyle category (sedentary, active, very_active, athlete)
        created_at: Timestamp when preferences were created
        updated_at: Timestamp when preferences were last updated
        
    Relationships:
        user: One-to-one relationship with User model
        
    Note:
        - Most fields are nullable to allow partial preference updates
        - Text fields (goals, dietary_restrictions, exercise_types) can store JSON or plain text
        - Location is used for geographic food recommendations and exercise suggestions
        - Activity level and lifestyle can overlap but provide different context
        - Demographic fields help agents provide age and gender-appropriate recommendations
    """
    __tablename__ = "user_preferences"

    # Primary key - auto-incrementing integer
    # Indexed for fast lookups by ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key to User model
    # Unique constraint ensures one preferences record per user (one-to-one relationship)
    # Required field - cannot be null
    # Cascade delete: if user is deleted, preferences are also deleted
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Fitness goals - user's fitness objectives
    # Format: JSON string (e.g., ["weight_loss", "muscle_gain"]) or comma-separated text
    # Examples: "weight_loss", "muscle_gain", "endurance", "flexibility", "general_fitness"
    # Used by agents to tailor workout and nutrition recommendations
    # Nullable to allow users to set preferences incrementally
    goals = Column(Text, nullable=True)  # JSON string or comma-separated goals
    
    # Dietary restrictions - allergies, intolerances, or dietary choices
    # Format: JSON string (e.g., ["gluten_free", "vegetarian"]) or comma-separated text
    # Examples: "gluten_free", "dairy_free", "vegetarian", "vegan", "nut_allergy"
    # Used by Nutrition Agent to avoid recommending restricted foods
    # Nullable to allow users without restrictions
    dietary_restrictions = Column(Text, nullable=True)  # JSON string or comma-separated
    
    # Location - user's geographic location
    # Format: City name, full address, or coordinates (latitude, longitude)
    # Examples: "New York, NY", "123 Main St, Los Angeles, CA", "40.7128,-74.0060"
    # Used for geographic food recommendations (local cuisine, seasonal produce)
    # Also used for location-based exercise suggestions (outdoor activities, gyms)
    # Nullable to allow users who prefer not to share location
    location = Column(String, nullable=True)  # City, address, or coordinates
    
    # Exercise preferences - types of exercises user enjoys or prefers
    # Format: JSON string (e.g., ["calisthenics", "cardio"]) or comma-separated text
    # Examples: "calisthenics", "weight_lifting", "cardio", "yoga", "swimming", "running"
    # Used by Physical Fitness Agent to recommend preferred exercise types
    # Nullable to allow users to discover new exercise types
    exercise_types = Column(Text, nullable=True)  # JSON string or comma-separated: calisthenics, weight_lifting, cardio, etc.
    
    # Activity level - user's current activity level
    # Values: "sedentary", "light", "moderate", "active", "very_active"
    # Used to calculate appropriate calorie intake and workout intensity
    # Helps agents understand user's current fitness baseline
    # Nullable to allow users to skip this information
    activity_level = Column(String, nullable=True)  # sedentary, light, moderate, active, very_active
    
    # Demographics - user's age
    # Range: 13-120 (typical age range for fitness applications)
    # Used for age-appropriate recommendations (e.g., safe exercise intensity for seniors)
    # Also used for calculating metabolic rate and nutritional needs
    # Nullable to allow users who prefer not to share age
    age = Column(Integer, nullable=True)  # User's age (13-120)
    
    # Demographics - user's gender
    # Values: "XX" (female), "XY" (male), "other", or null
    # Used for gender-specific recommendations (e.g., hormonal considerations)
    # Also used for calculating metabolic rate and nutritional needs
    # Nullable to allow users who prefer not to share gender
    gender = Column(String, nullable=True)  # XX, XY, other, or null
    
    # Lifestyle - user's lifestyle category
    # Values: "sedentary", "active", "very_active", "athlete"
    # Provides additional context beyond activity_level
    # Can overlap with activity_level but offers more nuanced categorization
    # Example: Someone with "moderate" activity_level but "athlete" lifestyle
    #   might need more specialized training recommendations
    # Nullable to allow users to skip this information
    lifestyle = Column(String, nullable=True)  # sedentary, active, very_active, athlete (can overlap with activity_level but provides more context)
    
    # Preferences creation timestamp
    # Automatically set to current time when preferences record is created
    # Timezone-aware DateTime for accurate time tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Preferences last update timestamp
    # Automatically updated to current time whenever preferences are modified
    # Timezone-aware DateTime for accurate time tracking
    # Only updates on actual changes (onupdate=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to User model
    # One-to-one relationship (each user has exactly one preferences record)
    # Access via: preferences.user (returns User object)
    # Back-populates with User.user_preferences
    user = relationship("User", back_populates="user_preferences")

