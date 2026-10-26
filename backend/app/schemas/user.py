"""The user as the API returns it (no password hash). Login and invite requests are
defined next to their routes in app/routers/auth.py (Plan C.6, C.18).
"""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserResponse(BaseModel):
    """
    User response schema for returning user data in API responses.
    
    This schema defines what user information is returned to clients.
    Sensitive data like password_hash is never included in responses.
    
    Attributes:
        id: User's unique identifier (primary key)
        email: User's email address
        username: User's username
        is_active: Whether the user account is active
        created_at: Timestamp when user account was created
        
    Security:
        - password_hash is NEVER included in responses
        - Only non-sensitive user information is exposed
        
    Config:
        from_attributes = True: Allows creating schema from SQLAlchemy model
        This enables automatic conversion from User model to UserResponse schema
        
    Note:
        - Used in endpoints that return user information
        - Automatically serializes datetime to ISO format string
        - Can be created directly from User model using from_attributes
    """
    id: int
    email: str
    username: str
    is_active: bool
    created_at: datetime

    class Config:
        # Enable creating schema instance from SQLAlchemy model attributes
        # This allows: UserResponse.from_orm(user_model_instance)
        from_attributes = True
