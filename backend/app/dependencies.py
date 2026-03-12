"""
FastAPI dependencies for dependency injection.

This module provides reusable dependencies that can be injected into route handlers
using FastAPI's dependency injection system. Dependencies handle common concerns
like database sessions and user authentication.

Key Dependencies:
- get_database: Provides database session for route handlers
- get_current_user: Validates JWT token and returns authenticated user

Usage:
    @app.get("/protected")
    def protected_route(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_database)
    ):
        # Use current_user and db here
        pass
"""

from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import decode_access_token
from app.models.user import User
import os

# HTTP Bearer token scheme for extracting JWT tokens from Authorization header
# auto_error=False: Don't automatically raise 403 if token is missing
# This allows us to handle missing tokens gracefully and return custom error messages
# The token is expected in the format: "Authorization: Bearer <token>"
security = HTTPBearer(auto_error=False)

# Database dependency
def get_database() -> Generator[Session, None, None]:
    """
    Dependency function for getting database session.
    
    This is a wrapper around get_db() that provides a database session to route handlers.
    The session is automatically created at the start of the request and closed after
    the route handler completes, ensuring proper resource cleanup.
    
    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_database)):
            return db.query(User).all()
    
    Yields:
        Session: SQLAlchemy database session instance
        
    Note:
        This function uses FastAPI's dependency injection system. The session is
        automatically managed - created when the route handler starts and closed
        when it finishes (even if an exception occurs).
    """
    # Delegate to get_db() from database module
    # This maintains a single source of truth for database session creation
    yield from get_db()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_database)
) -> User:
    """
    Dependency function to get the current authenticated user.
    
    This dependency validates the JWT token from the Authorization header and returns
    the corresponding User object. It performs several security checks:
    1. Verifies token is present
    2. Validates token signature and expiration
    3. Extracts user ID from token payload
    4. Fetches user from database
    5. Checks user is active
    
    Usage:
        @app.get("/profile")
        def get_profile(current_user: User = Depends(get_current_user)):
            return {"username": current_user.username}
    
    Args:
        credentials: HTTPBearer credentials extracted from Authorization header
        db: Database session (injected by FastAPI)
        
    Returns:
        User: The authenticated user object
        
    Raises:
        HTTPException: 401 Unauthorized if:
            - No token provided
            - Token is invalid or expired
            - User ID is missing from token
            - User not found in database
        HTTPException: 403 Forbidden if user account is inactive
        
    Note:
        The token should be sent in the Authorization header as:
        "Authorization: Bearer <token>"
        
        The token payload must contain a "sub" (subject) claim with the user ID.
        This is typically set when creating the token in the login endpoint.
    """
    # Check if credentials (token) were provided
    # HTTPBearer with auto_error=False returns None if token is missing
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},  # Tells client to use Bearer auth
        )
    
    # Extract the token string from credentials
    token = credentials.credentials
    
    # Clean token - remove any whitespace or quotes that might have been added
    # Some clients or proxies may add extra formatting
    if token:
        token = token.strip().strip('"').strip("'")
    
    # Debug logging (only in development)
    # Log token preview for debugging without exposing full token
    import logging
    logger = logging.getLogger(__name__)
    if os.getenv("ENVIRONMENT", "development") == "development":
        logger.info(f"Received token: {token[:30] if token and len(token) > 30 else token}...")
        logger.info(f"Token length: {len(token) if token else 0}")
    
    # Decode and validate the JWT token
    # This checks signature, expiration, and algorithm
    payload = decode_access_token(token)
    
    # If token is invalid, expired, or malformed, decode_access_token returns None
    if payload is None:
        logger.warning("Token decode failed - token may be invalid, expired, or signed with different secret")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - invalid or expired token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract user ID from token payload
    # JWT standard uses "sub" (subject) claim for user identification
    user_id_str = payload.get("sub")
    if user_id_str is None:
        logger.warning(f"Token payload missing 'sub': {payload}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - missing user ID",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Convert string user_id back to int
    # JWT payload values are typically strings, but we need an integer for database lookup
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        logger.warning(f"Invalid user_id format in token: {user_id_str}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - invalid user ID format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug(f"Token validated for user_id: {user_id}")
    
    # Fetch user from database using the user_id from token
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        # User ID in token doesn't exist in database (user may have been deleted)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user account is active
    # Inactive users cannot access protected endpoints
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,  # 403 instead of 401 since user exists but is disabled
            detail="Inactive user"
        )
    
    # Return the authenticated user object
    # This user object is now available in the route handler
    return user

