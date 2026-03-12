"""
User schemas for request/response validation.

This module defines Pydantic schemas for user-related API endpoints. These schemas
provide request/response validation, serialization, and documentation for the
authentication and user management endpoints.

Key Features:
- User registration schema (email, username, password)
- User login schema (email, password)
- User response schema (excludes sensitive data like password_hash)
- Token response schema (JWT access token)

Security Considerations:
- Password fields are never included in response schemas
- EmailStr validation ensures proper email format
- Token schema includes token type for proper authentication header format
"""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    """
    User registration schema for creating new user accounts.
    
    This schema validates the input data when a new user registers. All fields
    are required and validated before user creation.
    
    Attributes:
        email: User's email address (validated as proper email format)
        username: User's chosen username (must be unique)
        password: User's password (will be hashed before storage)
        
    Validation:
        - Email must be valid email format (EmailStr validation)
        - Username must be non-empty string
        - Password must be non-empty string
        
    Note:
        - Password is never stored in plain text - it's hashed using bcrypt
        - Email and username uniqueness is enforced at the database level
        - Password should meet security requirements (length, complexity) in frontend
    """
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    """
    User login schema for authenticating existing users.
    
    This schema validates the input data when a user attempts to log in.
    Both fields are required for authentication.
    
    Attributes:
        email: User's email address (used to identify the user)
        password: User's password (verified against stored hash)
        
    Validation:
        - Email must be valid email format (EmailStr validation)
        - Password must be non-empty string
        
    Note:
        - Email is used to look up the user account
        - Password is verified against the stored bcrypt hash
        - On successful authentication, a JWT token is returned
    """
    email: EmailStr
    password: str


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


class Token(BaseModel):
    """
    Token response schema for JWT authentication.
    
    This schema defines the response format when a user successfully authenticates.
    It includes the JWT access token and token type for proper authentication.
    
    Attributes:
        access_token: JWT access token string (used in Authorization header)
        token_type: Token type, defaults to "bearer" (OAuth 2.0 standard)
        
    Usage:
        The access_token should be included in subsequent API requests as:
        Authorization: Bearer <access_token>
        
    Note:
        - Token type is always "bearer" for JWT tokens
        - Access token expires after configured time (default: 30 minutes)
        - Token is signed with JWT_SECRET_KEY to prevent tampering
    """
    access_token: str
    token_type: str = "bearer"  # OAuth 2.0 standard token type

