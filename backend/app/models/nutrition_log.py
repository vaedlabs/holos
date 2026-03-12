"""
Nutrition Log model for tracking user meals and nutrition intake.

This module defines the NutritionLog model, which stores records of user meals
and nutritional intake. The model has a many-to-one relationship with the User model,
allowing users to log multiple meals over time.

Key Features:
- Meal type categorization (breakfast, lunch, dinner, snack)
- Structured food items (JSON format)
- Calorie tracking
- Macronutrient tracking (protein, carbs, fats)
- Meal date and timestamp tracking
- Notes for additional meal information
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class NutritionLog(Base):
    """
    Nutrition Log model storing user meal and nutrition intake records.
    
    This model stores individual meal entries completed by users. Each log entry
    represents a single meal with details about foods consumed, calories, and
    macronutrients. The model has a many-to-one relationship with User model.
    
    Attributes:
        id: Primary key, auto-incrementing integer
        user_id: Foreign key to User model (required)
        meal_date: Date and time when meal was consumed (timezone-aware)
        meal_type: Type of meal (breakfast, lunch, dinner, snack)
        foods: Structured food items in JSON format
        calories: Total calories for the meal (Float for decimal precision)
        macros: Macronutrient breakdown in JSON format (protein, carbs, fats in grams)
        notes: Additional notes about the meal (free-form text)
        created_at: Timestamp when log entry was created
        updated_at: Timestamp when log entry was last updated
        
    Relationships:
        user: Many-to-one relationship with User model
        
    JSON Format (foods field):
        The foods field stores structured data as JSON string. Example format:
        {
            "foods": [
                {
                    "name": "Grilled Chicken Breast",
                    "quantity": "200g",
                    "calories": 330
                },
                {
                    "name": "Brown Rice",
                    "quantity": "1 cup",
                    "calories": 216
                },
                {
                    "name": "Steamed Broccoli",
                    "quantity": "150g",
                    "calories": 50
                }
            ]
        }
        
        Or simpler format (from image analysis):
        {
            "foods": [
                {"name": "Pizza Slice", "quantity": "1 slice"},
                {"name": "Caesar Salad", "quantity": "1 bowl"}
            ]
        }
        
    JSON Format (macros field):
        The macros field stores macronutrient breakdown as JSON string:
        {
            "protein": 45.5,  // grams
            "carbs": 120.0,   // grams
            "fats": 25.3      // grams
        }
        
    Note:
        - Multiple nutrition logs can exist per user (many-to-one relationship)
        - Meal type helps categorize meals for analysis and recommendations
        - JSON format allows flexible food data structure
        - Calories can be fractional (e.g., 250.5 calories)
        - Macros are stored in grams for precision
        - Meal date defaults to current time but can be set to past dates
        - Used by Nutrition Agent to track dietary patterns and provide recommendations
    """
    __tablename__ = "nutrition_logs"

    # Primary key - auto-incrementing integer
    # Indexed for fast lookups by ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key to User model
    # Many-to-one relationship (each user can have multiple nutrition logs)
    # Required field - cannot be null
    # Indexed for fast queries filtering by user
    # Cascade delete: if user is deleted, nutrition logs are also deleted
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Meal date and time - when the meal was consumed
    # Timezone-aware DateTime for accurate time tracking across timezones
    # Defaults to current time when log entry is created
    # Can be set to past dates for logging meals retroactively
    # Required field - cannot be null
    meal_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Meal type - category of the meal
    # Values: "breakfast", "lunch", "dinner", "snack"
    # Used for categorizing meals and generating statistics
    # Helps agents understand user's eating patterns and meal timing
    # Nullable to allow flexibility, but recommended for better tracking
    meal_type = Column(String, nullable=True)  # breakfast, lunch, dinner, snack
    
    # Foods - structured details of foods consumed
    # Format: JSON string containing array of food objects
    # Each food object can include: name, quantity, calories, etc.
    # Flexible JSON structure allows different food types to have different fields
    # Example: {"foods": [{"name": "Grilled Chicken", "quantity": "200g", "calories": 330}]}
    # Used by Nutrition Agent to analyze dietary patterns and provide recommendations
    # Can be populated from image analysis (Gemini Vision API) or manual entry
    # Nullable to allow simple meal logs without detailed food breakdown
    foods = Column(Text, nullable=True)  # JSON string with food items and details
    
    # Calories - total calories for the meal
    # Float type allows decimal precision (e.g., 250.5 calories)
    # Used for tracking daily calorie intake and generating statistics
    # Helps agents understand user's calorie consumption patterns
    # Can be calculated from foods or entered directly
    # Nullable to allow meals without calorie tracking
    calories = Column(Float, nullable=True)  # Total calories
    
    # Macros - macronutrient breakdown (protein, carbs, fats)
    # Format: JSON string containing macronutrient values in grams
    # Example: {"protein": 45.5, "carbs": 120.0, "fats": 25.3}
    # Used for tracking macronutrient intake and generating statistics
    # Helps agents understand user's nutritional balance
    # Can be calculated from foods or entered directly
    # Values are stored in grams for precision
    # Nullable to allow meals without macro tracking
    macros = Column(Text, nullable=True)  # JSON string with protein, carbs, fats
    
    # Notes - additional information about the meal
    # Format: Free-form text for any additional context
    # Examples: "Felt satisfied", "Post-workout meal", "Restaurant meal"
    # Provides flexibility for users to add context to their meals
    # Used by agents to understand meal context and user feedback
    # Nullable to allow meals without notes
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
    # Many-to-one relationship (each user can have multiple nutrition logs)
    # Access via: nutrition_log.user (returns User object)
    # Back-populates with User.nutrition_logs (returns list of NutritionLog objects)
    user = relationship("User", back_populates="nutrition_logs")

