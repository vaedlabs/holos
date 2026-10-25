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

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
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

# bcrypt only reads the first 72 bytes of a password
BCRYPT_MAX_BYTES = 72


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a bcrypt hash.

    Accepts hashes made by passlib (same $2b$ format). The password is cut to
    72 bytes because older accounts were hashed from a cut password, and
    bcrypt 5 raises on longer input instead of ignoring the extra bytes.

    Args:
        plain_password: The plain text password to verify
        hashed_password: The bcrypt hash to compare against

    Returns:
        bool: True if the password matches the hash, False otherwise
              (including when the stored hash is malformed)
    """
    password_bytes = plain_password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt (12 rounds, random salt).

    Args:
        password: The plain text password to hash

    Returns:
        str: The bcrypt hash of the password (includes salt and algorithm info)

    Raises:
        ValueError: If the password is longer than 72 bytes. Bcrypt would
            silently ignore the extra bytes, so we reject it and the user
            gets a clear error at registration time.
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_BYTES:
        raise ValueError("Password is too long. Please use 72 characters or fewer.")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


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
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
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

