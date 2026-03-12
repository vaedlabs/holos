"""
Log schemas for request/response validation.

This module defines Pydantic schemas for log-related endpoints. These schemas
provide request/response validation, serialization, and documentation for
workout logs, nutrition logs, and mental fitness logs.

Key Features:
- Individual log response schemas (workout, nutrition, mental fitness)
- List response schemas with pagination support (total count)
- Support for optional fields (allows partial log entries)
- Automatic datetime serialization

Log Types:
- Workout logs: Exercise activity records
- Nutrition logs: Meal and nutrition intake records
- Mental fitness logs: Mental wellness activity records
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class WorkoutLogResponse(BaseModel):
    """
    Workout log response schema for returning workout log data.
    
    This schema defines what workout log information is returned to clients.
    Includes all workout fields plus metadata (id, user_id, timestamps).
    
    Attributes:
        id: Workout log unique identifier (primary key)
        user_id: Foreign key to User model
        workout_date: Date and time when workout was performed
        exercise_type: Category of exercise (optional)
        exercises: Structured exercise details in JSON format (optional)
        duration_minutes: Duration of workout in minutes (optional)
        notes: Additional notes about the workout (optional)
        created_at: Timestamp when log entry was created
        updated_at: Timestamp when log entry was last updated (optional)
        
    JSON Format (exercises field):
        The exercises field contains JSON string with structured exercise data:
        {"exercises": [{"name": "Push-ups", "sets": 3, "reps": 15}]}
        
    Config:
        from_attributes = True: Allows creating schema from SQLAlchemy model
        This enables automatic conversion from WorkoutLog model to response schema
        
    Note:
        - Used in endpoints that return workout logs
        - Automatically serializes datetime to ISO format string
        - Can be created directly from WorkoutLog model using from_attributes
        - Most fields are optional to allow flexible log entries
    """
    id: int
    user_id: int
    workout_date: datetime
    exercise_type: Optional[str]
    exercises: Optional[str]
    duration_minutes: Optional[float]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        # Enable creating schema instance from SQLAlchemy model attributes
        # This allows: WorkoutLogResponse.from_orm(workout_log_model_instance)
        from_attributes = True


class WorkoutLogsListResponse(BaseModel):
    """
    Workout logs list response schema for paginated workout log lists.
    
    This schema defines the response format when returning multiple workout logs.
    Includes the list of logs and total count for pagination.
    
    Attributes:
        logs: List of WorkoutLogResponse objects
        total: Total number of workout logs (for pagination)
        
    Pagination:
        The total field allows clients to calculate pagination:
        - Total pages = ceil(total / page_size)
        - Can determine if more pages exist
        - Useful for UI pagination controls
        
    Note:
        - Used in endpoints that return lists of workout logs
        - Supports filtering and pagination
        - Total count includes all matching logs, not just returned page
    """
    logs: List[WorkoutLogResponse]
    total: int


class NutritionLogResponse(BaseModel):
    """
    Nutrition log response schema for returning nutrition log data.
    
    This schema defines what nutrition log information is returned to clients.
    Includes all nutrition fields plus metadata (id, user_id, timestamps).
    
    Attributes:
        id: Nutrition log unique identifier (primary key)
        user_id: Foreign key to User model
        meal_date: Date and time when meal was consumed
        meal_type: Type of meal - breakfast, lunch, dinner, snack (optional)
        foods: Structured food items in JSON format (optional)
        calories: Total calories for the meal (optional)
        macros: Macronutrient breakdown in JSON format (optional)
        notes: Additional notes about the meal (optional)
        created_at: Timestamp when log entry was created
        updated_at: Timestamp when log entry was last updated (optional)
        
    JSON Format (foods field):
        The foods field contains JSON string with structured food data:
        {"foods": [{"name": "Grilled Chicken", "quantity": "200g", "calories": 330}]}
        
    JSON Format (macros field):
        The macros field contains JSON string with macronutrient data:
        {"protein": 45.5, "carbs": 120.0, "fats": 25.3}  // values in grams
        
    Config:
        from_attributes = True: Allows creating schema from SQLAlchemy model
        This enables automatic conversion from NutritionLog model to response schema
        
    Note:
        - Used in endpoints that return nutrition logs
        - Automatically serializes datetime to ISO format string
        - Can be created directly from NutritionLog model using from_attributes
        - Most fields are optional to allow flexible log entries
    """
    id: int
    user_id: int
    meal_date: datetime
    meal_type: Optional[str]
    foods: Optional[str]  # JSON string
    calories: Optional[float]
    macros: Optional[str]  # JSON string
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        # Enable creating schema instance from SQLAlchemy model attributes
        # This allows: NutritionLogResponse.from_orm(nutrition_log_model_instance)
        from_attributes = True


class NutritionLogsListResponse(BaseModel):
    """
    Nutrition logs list response schema for paginated nutrition log lists.
    
    This schema defines the response format when returning multiple nutrition logs.
    Includes the list of logs and total count for pagination.
    
    Attributes:
        logs: List of NutritionLogResponse objects
        total: Total number of nutrition logs (for pagination)
        
    Pagination:
        The total field allows clients to calculate pagination:
        - Total pages = ceil(total / page_size)
        - Can determine if more pages exist
        - Useful for UI pagination controls
        
    Note:
        - Used in endpoints that return lists of nutrition logs
        - Supports filtering and pagination
        - Total count includes all matching logs, not just returned page
    """
    logs: List[NutritionLogResponse]
    total: int


class MentalFitnessLogResponse(BaseModel):
    """
    Mental fitness log response schema for returning mental fitness log data.
    
    This schema defines what mental fitness log information is returned to clients.
    Includes all mental fitness fields plus metadata (id, user_id, timestamps).
    
    Attributes:
        id: Mental fitness log unique identifier (primary key)
        user_id: Foreign key to User model
        activity_date: Date and time when activity was performed
        activity_type: Type of mental wellness activity (optional)
        duration_minutes: Duration of activity in minutes (optional)
        mood_before: User's mood before the activity (optional)
        mood_after: User's mood after the activity (optional)
        notes: Additional notes about the activity (optional)
        created_at: Timestamp when log entry was created
        updated_at: Timestamp when log entry was last updated (optional)
        
    Mood Tracking:
        Mood fields can contain:
        - Numeric scale: "1" to "10" (1 = very low, 10 = very high)
        - Descriptive text: "anxious", "calm", "energized", "relaxed"
        - Combination: "7 - calm and focused"
        
    Config:
        from_attributes = True: Allows creating schema from SQLAlchemy model
        This enables automatic conversion from MentalFitnessLog model to response schema
        
    Note:
        - Used in endpoints that return mental fitness logs
        - Automatically serializes datetime to ISO format string
        - Can be created directly from MentalFitnessLog model using from_attributes
        - Most fields are optional to allow flexible log entries
    """
    id: int
    user_id: int
    activity_date: datetime
    activity_type: Optional[str]
    duration_minutes: Optional[float]
    mood_before: Optional[str]
    mood_after: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        # Enable creating schema instance from SQLAlchemy model attributes
        # This allows: MentalFitnessLogResponse.from_orm(mental_fitness_log_model_instance)
        from_attributes = True


class MentalFitnessLogsListResponse(BaseModel):
    """
    Mental fitness logs list response schema for paginated mental fitness log lists.
    
    This schema defines the response format when returning multiple mental fitness logs.
    Includes the list of logs and total count for pagination.
    
    Attributes:
        logs: List of MentalFitnessLogResponse objects
        total: Total number of mental fitness logs (for pagination)
        
    Pagination:
        The total field allows clients to calculate pagination:
        - Total pages = ceil(total / page_size)
        - Can determine if more pages exist
        - Useful for UI pagination controls
        
    Note:
        - Used in endpoints that return lists of mental fitness logs
        - Supports filtering and pagination
        - Total count includes all matching logs, not just returned page
    """
    logs: List[MentalFitnessLogResponse]
    total: int

