"""
FastAPI dependencies
"""

from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import decode_access_token
from app.models.user import User
import os

# HTTP Bearer token scheme
# auto_error=False allows us to handle missing tokens gracefully
security = HTTPBearer(auto_error=False)

# Database dependency
def get_database() -> Generator[Session, None, None]:
    """
    Dependency for getting database session.
    Usage in routes: db: Session = Depends(get_database)
    """
    yield from get_db()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_database)
) -> User:
    """
    Dependency to get the current authenticated user.
    Validates JWT token and returns the user.
    Usage in routes: current_user: User = Depends(get_current_user)
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # Clean token - remove any whitespace or quotes that might have been added
    if token:
        token = token.strip().strip('"').strip("'")
    
    # Debug logging (only in development)
    import logging
    logger = logging.getLogger(__name__)
    if os.getenv("ENVIRONMENT", "development") == "development":
        logger.info(f"Received token: {token[:30] if token and len(token) > 30 else token}...")
        logger.info(f"Token length: {len(token) if token else 0}")
    
    payload = decode_access_token(token)
    
    if payload is None:
        logger.warning("Token decode failed - token may be invalid, expired, or signed with different secret")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - invalid or expired token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id_str = payload.get("sub")
    if user_id_str is None:
        logger.warning(f"Token payload missing 'sub': {payload}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - missing user ID",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Convert string user_id back to int
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
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user

