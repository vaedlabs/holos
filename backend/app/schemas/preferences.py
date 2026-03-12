"""
User preferences schemas for request/response validation.

This module defines Pydantic schemas for user preferences endpoints. These schemas
provide request/response validation, serialization, and documentation for managing
user fitness and lifestyle preferences.

Key Features:
- User preferences create/update schema (supports partial updates)
- User preferences response schema (includes all preference fields)
- Field validation for age and gender
- All fields are optional to support incremental preference updates

Validation:
- Age must be between 13 and 120 (inclusive)
- Gender must be one of: 'XX', 'XY', 'other'
- All other fields are optional strings
"""

from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class UserPreferencesCreate(BaseModel):
    """
    User preferences create/update schema for managing user preferences.
    
    This schema validates input data when creating or updating user preferences.
    All fields are optional to support partial updates - users can update individual
    preferences without providing all fields.
    
    Attributes:
        goals: User's fitness goals (JSON string or comma-separated, optional)
        exercise_types: Preferred exercise types (JSON string or comma-separated, optional)
        activity_level: Current activity level (optional)
        location: Geographic location (city, address, or coordinates, optional)
        dietary_restrictions: Dietary restrictions/allergies (JSON string or comma-separated, optional)
        age: User's age (13-120, optional)
        gender: User's gender ('XX', 'XY', 'other', optional)
        lifestyle: Lifestyle category (optional)
        
    Field Formats:
        - goals: "weight_loss,muscle_gain" or JSON array string
        - exercise_types: "calisthenics,cardio" or JSON array string
        - activity_level: "sedentary", "light", "moderate", "active", "very_active"
        - location: "New York, NY" or "40.7128,-74.0060" or full address
        - dietary_restrictions: "gluten_free,vegetarian" or JSON array string
        - lifestyle: "sedentary", "active", "very_active", "athlete"
        
    Validation:
        - Age: Must be between 13 and 120 (inclusive) if provided
        - Gender: Must be 'XX', 'XY', or 'other' if provided
        - All other fields: Optional strings with no format restrictions
        
    Note:
        - All fields are optional to allow partial updates
        - Empty strings are treated as None (no update)
        - Used for both creating new preferences and updating existing ones
        - Validation errors return clear error messages to help users correct input
    """
    goals: Optional[str] = None
    exercise_types: Optional[str] = None
    activity_level: Optional[str] = None
    location: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    lifestyle: Optional[str] = None

    @field_validator('age')
    @classmethod
    def validate_age(cls, v):
        """
        Validate age field - must be between 13 and 120 if provided.
        
        Args:
            v: Age value to validate (can be None)
            
        Returns:
            Validated age value
            
        Raises:
            ValueError: If age is provided but not between 13 and 120
            
        Note:
            - None values are allowed (field is optional)
            - Age range 13-120 covers typical fitness application users
            - Validation ensures age-appropriate recommendations
        """
        if v is not None:
            if not isinstance(v, int) or v < 13 or v > 120:
                raise ValueError('Age must be between 13 and 120')
        return v

    @field_validator('gender')
    @classmethod
    def validate_gender(cls, v):
        """
        Validate gender field - must be one of valid values if provided.
        
        Args:
            v: Gender value to validate (can be None)
            
        Returns:
            Validated gender value
            
        Raises:
            ValueError: If gender is provided but not one of: 'XX', 'XY', 'other'
            
        Valid Values:
            - 'XX': Female
            - 'XY': Male
            - 'other': Other gender identity
            
        Note:
            - None values are allowed (field is optional)
            - Validation ensures consistent gender data format
            - Used for gender-specific recommendations and metabolic calculations
        """
        if v is not None:
            valid_genders = ['XX', 'XY', 'other']
            if v not in valid_genders:
                raise ValueError(f'Gender must be one of: {", ".join(valid_genders)}')
        return v


class UserPreferencesResponse(BaseModel):
    """
    User preferences response schema for returning user preferences data.
    
    This schema defines what preference information is returned to clients.
    Includes all preference fields plus metadata (id, user_id, timestamps).
    
    Attributes:
        id: Preferences record unique identifier (primary key)
        user_id: Foreign key to User model
        goals: User's fitness goals (optional)
        exercise_types: Preferred exercise types (optional)
        activity_level: Current activity level (optional)
        location: Geographic location (optional)
        dietary_restrictions: Dietary restrictions/allergies (optional)
        age: User's age (optional)
        gender: User's gender (optional)
        lifestyle: Lifestyle category (optional)
        created_at: Timestamp when preferences were created
        updated_at: Timestamp when preferences were last updated (optional)
        
    Config:
        from_attributes = True: Allows creating schema from SQLAlchemy model
        This enables automatic conversion from UserPreferences model to response schema
        
    Note:
        - Used in endpoints that return user preferences
        - Automatically serializes datetime to ISO format string
        - Can be created directly from UserPreferences model using from_attributes
        - All preference fields are optional (users may not have set all preferences)
    """
    id: int
    user_id: int
    goals: Optional[str]
    exercise_types: Optional[str]
    activity_level: Optional[str]
    location: Optional[str]
    dietary_restrictions: Optional[str]
    age: Optional[int]
    gender: Optional[str]
    lifestyle: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        # Enable creating schema instance from SQLAlchemy model attributes
        # This allows: UserPreferencesResponse.from_orm(preferences_model_instance)
        from_attributes = True


