"""
JWT Authentication utilities.

This module provides authentication functionality for the Holos application using
JSON Web Tokens (JWT) for stateless authentication and bcrypt for password hashing.

Key Features:
- JWT token creation and validation
- Password hashing and verification using bcrypt
- Token expiration handling
- Fallback mechanisms for bcrypt compatibility

Security Considerations:
- JWT_SECRET_KEY must be at least 32 characters (validated at startup)
- Passwords are hashed using bcrypt with appropriate salt rounds
- Tokens include expiration time to limit validity period
- Token validation includes signature verification and expiration checks
"""

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# JWT Configuration
# Secret key used to sign and verify JWT tokens
# Must be set via environment variable and validated at startup (minimum 32 characters)
# This should be a strong, randomly generated secret in production
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

# Algorithm used for JWT signing and verification
# HS256 (HMAC-SHA256) is the default and recommended for most use cases
# Other options include RS256 (RSA) for asymmetric signing
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Token expiration time in minutes
# Default is 30 minutes - tokens expire after this duration for security
# Can be overridden per-token by passing expires_delta to create_access_token
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Password hashing context
# Uses bcrypt algorithm for password hashing
# CryptContext provides a unified interface for password hashing with fallback support
# "deprecated="auto"" allows automatic handling of deprecated hash formats
# This configuration helps avoid bcrypt version compatibility issues
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.
    
    This function securely compares a plain text password with a bcrypt hash.
    Uses passlib's CryptContext for verification, with a fallback to direct
    bcrypt if passlib fails (for compatibility with different bcrypt versions).
    
    Args:
        plain_password: The plain text password to verify
        hashed_password: The bcrypt hash to compare against
        
    Returns:
        bool: True if the password matches the hash, False otherwise
        
    Raises:
        ValueError: If password verification fails due to an unexpected error
        
    Note:
        The function uses constant-time comparison internally to prevent
        timing attacks. The fallback to direct bcrypt helps with compatibility
        issues between different versions of the bcrypt library.
    """
    try:
        # Primary method: use passlib's CryptContext
        # This handles various hash formats and provides a unified interface
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        # Fallback: try direct bcrypt if passlib fails
        # This handles compatibility issues with different bcrypt library versions
        # Some environments may have bcrypt installed but passlib may have issues
        try:
            import bcrypt
            # Direct bcrypt comparison - encode strings to bytes as required
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            # If both methods fail, raise an error with context
            raise ValueError(f"Password verification failed: {e}")


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    This function creates a secure bcrypt hash of a password. The hash includes
    a randomly generated salt, making it secure against rainbow table attacks.
    Uses passlib's CryptContext with a fallback to direct bcrypt for compatibility.
    
    Args:
        password: The plain text password to hash
        
    Returns:
        str: The bcrypt hash of the password (includes salt and algorithm info)
        
    Raises:
        ValueError: If password hashing fails due to an unexpected error
        
    Note:
        - Bcrypt has a 72-byte limit on password length. Longer passwords are truncated.
        - The hash uses 12 rounds by default (good balance between security and performance)
        - Each hash includes a unique salt, so the same password produces different hashes
        - The returned hash can be stored directly in the database
    """
    # Ensure password is not longer than 72 bytes (bcrypt limit)
    # Bcrypt only uses the first 72 bytes of a password, so longer passwords
    # are effectively truncated. We truncate explicitly to avoid confusion.
    if len(password.encode('utf-8')) > 72:
        password = password[:72]
    
    try:
        # Primary method: use passlib's CryptContext
        # Automatically handles salt generation and hash formatting
        return pwd_context.hash(password)
    except Exception as e:
        # Fallback: use direct bcrypt if passlib fails
        # This handles compatibility issues with different bcrypt library versions
        try:
            import bcrypt
            # Generate a salt with 12 rounds (good balance of security and performance)
            salt = bcrypt.gensalt(rounds=12)
            # Hash the password with the salt
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            # Decode bytes to string for storage
            return hashed.decode('utf-8')
        except Exception:
            # If both methods fail, raise an error with context
            raise ValueError(f"Password hashing failed: {e}")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    This function creates a JSON Web Token containing user data and an expiration time.
    The token is signed with the JWT_SECRET_KEY to prevent tampering.
    
    Args:
        data: Dictionary containing claims to include in the token (e.g., user_id, username)
        expires_delta: Optional custom expiration time. If not provided, uses
            JWT_ACCESS_TOKEN_EXPIRE_MINUTES from configuration.
            
    Returns:
        str: Encoded JWT token string that can be sent to the client
        
    Raises:
        ValueError: If JWT_SECRET_KEY is not configured
        
    Example:
        token = create_access_token(data={"user_id": 1, "username": "john"})
        # Token expires in 30 minutes (default) or custom time if expires_delta provided
        
    Note:
        The token includes an "exp" (expiration) claim that is automatically
        validated when decoding. Tokens should be stored securely on the client
        (e.g., in httpOnly cookies or secure storage).
    """
    # Validate that JWT_SECRET_KEY is configured
    # This should have been validated at startup, but check here as a safety measure
    if not JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY is not configured. Please set it in environment variables.")
    
    # Create a copy of the data to avoid modifying the original dictionary
    to_encode = data.copy()
    
    # Calculate expiration time
    # Use custom expiration if provided, otherwise use default from configuration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Add expiration claim to the token payload
    # The "exp" claim is a standard JWT claim that indicates when the token expires
    to_encode.update({"exp": expire})
    
    # Encode the token using the secret key and algorithm
    # The token is signed to prevent tampering
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT access token.
    
    This function decodes a JWT token and validates its signature and expiration.
    Returns None if the token is invalid, expired, or malformed.
    
    Args:
        token: The JWT token string to decode and validate
        
    Returns:
        Optional[dict]: The decoded token payload (claims) if valid, None otherwise.
            The payload typically contains user information like user_id, username, etc.
            
    Note:
        This function performs several validations:
        - Verifies the token signature using JWT_SECRET_KEY
        - Checks that the token hasn't expired (validates "exp" claim)
        - Validates the algorithm matches JWT_ALGORITHM
        - Handles common token format issues (whitespace, quotes)
        
        Returns None (rather than raising exceptions) to allow callers to handle
        invalid tokens gracefully (e.g., redirect to login).
    """
    # Validate that JWT_SECRET_KEY is configured
    if not JWT_SECRET_KEY:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("JWT_SECRET_KEY is not configured. Cannot decode tokens.")
        return None
    
    # Handle empty or None tokens
    if not token:
        return None
    
    # Clean token - remove any whitespace or quotes
    # Tokens may come from headers or cookies with extra formatting
    # This handles common cases where tokens are wrapped in quotes or have whitespace
    token = token.strip().strip('"').strip("'")
    
    try:
        # Decode and validate the token
        # jwt.decode automatically validates:
        # - Signature (prevents tampering)
        # - Expiration (checks "exp" claim)
        # - Algorithm (ensures correct algorithm was used)
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        # JWT-specific errors (expired, invalid signature, wrong algorithm, etc.)
        # Log the error for debugging but don't expose details to prevent information leakage
        import logging
        logger = logging.getLogger(__name__)
        # Log token preview (first 30 chars) for debugging without exposing full token
        logger.warning(f"JWT decode error: {e}, token preview: {token[:30] if len(token) > 30 else token}...")
        return None
    except Exception as e:
        # Unexpected errors (shouldn't happen, but handle gracefully)
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error decoding token: {e}")
        return None

