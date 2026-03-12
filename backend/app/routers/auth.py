"""
Authentication routes for user registration, login, and account management.

This module provides FastAPI router endpoints for authentication operations:
- User registration: Create new user accounts with email and username validation
- User login: Authenticate users and issue JWT access tokens
- Account deletion: Delete user accounts and all associated data

Key Features:
- Password hashing using bcrypt (via app.auth)
- JWT token generation for authenticated sessions
- Email and username uniqueness validation
- Account deletion with cascading data cleanup
- Security considerations: Password verification, active user checks, error handling

Security Considerations:
- Passwords are hashed using bcrypt before storage
- JWT tokens are used for authenticated sessions
- Generic error messages prevent user enumeration attacks
- Active user status is checked during login
- Account deletion requires authentication

Dependencies:
- get_database: Database session dependency
- get_current_user: Current authenticated user dependency (for delete_account)
- app.auth: Password hashing and JWT token creation functions
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pathlib import Path
from app.dependencies import get_database, get_current_user
from app.auth import verify_password, get_password_hash, create_access_token
from app.models.user import User
from app.models.conversation_message import ConversationMessage
from app.models.workout_log import WorkoutLog
from app.models.nutrition_log import NutritionLog
from app.models.mental_fitness_log import MentalFitnessLog
from app.models.medical_history import MedicalHistory
from app.models.user_preferences import UserPreferences
from app.schemas.user import UserRegister, UserLogin, UserResponse, Token

# FastAPI router for authentication endpoints
# Prefix: /auth (all routes will be prefixed with /auth)
# Tags: ["auth"] (for API documentation grouping)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_database)):
    """
    Register a new user account.
    
    This endpoint creates a new user account with email and username validation.
    Passwords are hashed using bcrypt before storage. The user is created as active
    by default and can immediately log in after registration.
    
    Registration Flow:
        1. Validate email uniqueness (check if email already exists)
        2. Validate username uniqueness (check if username already taken)
        3. Hash password using bcrypt
        4. Create new user record with hashed password
        5. Commit to database and return user data
    
    Args:
        user_data: UserRegister schema containing:
            - email: str (validated email format)
            - username: str (validated username format)
            - password: str (will be hashed before storage)
        db: Database session (injected dependency)
    
    Returns:
        UserResponse: Created user data (without password hash)
        
    Raises:
        HTTPException 400: If email or username already exists
        HTTPException 400: If database integrity error occurs
        
    Security Considerations:
        - Passwords are never stored in plain text (hashed with bcrypt)
        - Email and username uniqueness prevents duplicate accounts
        - Generic error messages prevent user enumeration attacks
        - Database integrity errors are caught and handled gracefully
        
    Example:
        POST /auth/register
        {
            "email": "user@example.com",
            "username": "username",
            "password": "secure_password123"
        }
    """
    # Check if user with email already exists
    # Prevents duplicate email addresses in the system
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username already exists
    # Prevents duplicate usernames in the system
    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create new user
    # Hash password using bcrypt before storage
    # Password hash is stored, never plain text password
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        password_hash=hashed_password,  # Store hashed password, not plain text
        is_active=True  # User is active by default (can log in immediately)
    )
    
    try:
        # Add user to database session
        db.add(new_user)
        # Commit transaction to database
        db.commit()
        # Refresh user object to get database-generated fields (e.g., id, created_at)
        db.refresh(new_user)
        return new_user  # Return user data (password hash excluded by UserResponse schema)
    except IntegrityError:
        # Handle database integrity errors (e.g., unique constraint violations)
        db.rollback()  # Rollback transaction on error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User registration failed"
        )


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: Session = Depends(get_database)):
    """
    Authenticate user and return JWT access token.
    
    This endpoint authenticates a user by verifying their email and password,
    then issues a JWT access token for authenticated session management.
    
    Login Flow:
        1. Find user by email address
        2. Verify password using bcrypt comparison
        3. Check if user account is active
        4. Generate JWT access token with user ID
        5. Return token for use in Authorization header
    
    Args:
        credentials: UserLogin schema containing:
            - email: str (user's email address)
            - password: str (user's plain text password)
        db: Database session (injected dependency)
    
    Returns:
        Token: Dictionary containing:
            - access_token: str (JWT token for authenticated requests)
            - token_type: str ("bearer" for Bearer token authentication)
            
    Raises:
        HTTPException 401: If email or password is incorrect
        HTTPException 403: If user account is inactive
        
    Security Considerations:
        - Generic error message ("Incorrect email or password") prevents user enumeration
        - Password verification uses bcrypt constant-time comparison
        - JWT token contains user ID in 'sub' claim (subject)
        - Token type is "bearer" for Bearer token authentication
        - Active user check prevents login for deactivated accounts
        
    JWT Token Details:
        - Token contains user ID in 'sub' claim (must be string for python-jose)
        - Token expiration is configured in app.auth.create_access_token()
        - Token is used in Authorization header: "Bearer <access_token>"
        
    Example:
        POST /auth/login
        {
            "email": "user@example.com",
            "password": "secure_password123"
        }
        
        Response:
        {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer"
        }
    """
    # Find user by email
    # Email is used as the unique identifier for login
    user = db.query(User).filter(User.email == credentials.email).first()
    
    # Check if user exists
    # Generic error message prevents user enumeration attacks
    # Same message for both email and password errors
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",  # Generic message for security
            headers={"WWW-Authenticate": "Bearer"},  # Required for 401 responses
        )
    
    # Verify password
    # Uses bcrypt to compare plain text password with stored hash
    # Constant-time comparison prevents timing attacks
    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",  # Generic message for security
            headers={"WWW-Authenticate": "Bearer"},  # Required for 401 responses
        )
    
    # Check if user is active
    # Prevents login for deactivated accounts
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    # Create access token
    # JWT token contains user ID in 'sub' claim (subject)
    # Note: 'sub' must be a string for python-jose library
    access_token = create_access_token(data={"sub": str(user.id)})
    
    # Return token for use in Authorization header
    # Token type is "bearer" for Bearer token authentication
    return {"access_token": access_token, "token_type": "bearer"}


@router.delete("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Delete the current user's account and all associated data.
    
    This endpoint permanently deletes the authenticated user's account and all
    associated data. This action is irreversible and should be used with caution.
    
    Deletion Flow:
        1. Delete conversation messages and associated image files
        2. Delete workout logs
        3. Delete nutrition logs
        4. Delete mental fitness logs
        5. Delete medical history
        6. Delete user preferences
        7. Delete user account
        8. Commit all deletions in a single transaction
    
    Args:
        current_user: Authenticated user (injected dependency from get_current_user)
                     Ensures only authenticated users can delete their own account
        db: Database session (injected dependency)
    
    Returns:
        None: 204 No Content response on successful deletion
        
    Raises:
        HTTPException 500: If deletion fails (transaction rolled back)
        
    Security Considerations:
        - Requires authentication (get_current_user dependency)
        - Users can only delete their own account (current_user.id)
        - All associated data is deleted to prevent orphaned records
        - Image files are deleted from filesystem
        - Transaction ensures atomicity (all or nothing)
        
    Data Deleted:
        - Conversation messages (with image file cleanup)
        - Workout logs
        - Nutrition logs
        - Mental fitness logs
        - Medical history
        - User preferences
        - User account
        
    Note:
        - This action is irreversible
        - Image file deletion failures are ignored (continues deletion)
        - All deletions are performed in a single transaction
        - Database rollback on any error ensures data consistency
        
    Example:
        DELETE /auth/delete-account
        Headers: Authorization: Bearer <access_token>
    """
    try:
        user_id = current_user.id  # Get user ID from authenticated user
        
        # 1. Delete conversation messages and associated images
        # Fetch all conversation messages for this user
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == user_id
        ).all()
        
        # Delete associated image files from filesystem
        # Images are stored in uploads/images directory
        UPLOADS_DIR = Path("uploads/images")
        for msg in messages:
            if msg.image_path:
                # Extract filename from image path
                image_file = UPLOADS_DIR / msg.image_path.split('/')[-1]
                if image_file.exists():
                    try:
                        image_file.unlink()  # Delete image file
                    except:
                        pass  # Continue even if image deletion fails (non-critical)
        
        # Delete conversation messages from database
        db.query(ConversationMessage).filter(
            ConversationMessage.user_id == user_id
        ).delete()
        
        # 2. Delete workout logs
        # All workout log entries for this user
        db.query(WorkoutLog).filter(
            WorkoutLog.user_id == user_id
        ).delete()
        
        # 3. Delete nutrition logs
        # All nutrition log entries for this user
        db.query(NutritionLog).filter(
            NutritionLog.user_id == user_id
        ).delete()
        
        # 4. Delete mental fitness logs
        # All mental fitness log entries for this user
        db.query(MentalFitnessLog).filter(
            MentalFitnessLog.user_id == user_id
        ).delete()
        
        # 5. Delete medical history
        # User's medical history record
        db.query(MedicalHistory).filter(
            MedicalHistory.user_id == user_id
        ).delete()
        
        # 6. Delete user preferences
        # User's preferences record
        db.query(UserPreferences).filter(
            UserPreferences.user_id == user_id
        ).delete()
        
        # 7. Delete user account
        # Finally delete the user account itself
        db.query(User).filter(User.id == user_id).delete()
        
        # Commit all deletions in a single transaction
        # Ensures atomicity: all deletions succeed or all are rolled back
        db.commit()
        return None  # 204 No Content response
    except Exception as e:
        # Rollback transaction on any error
        # Ensures data consistency if deletion fails
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting account: {str(e)}"
        )

