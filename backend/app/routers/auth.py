"""
Authentication routes
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

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_database)):
    """
    Register a new user
    """
    # Check if user with email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username already exists
    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        password_hash=hashed_password,
        is_active=True
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User registration failed"
        )


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: Session = Depends(get_database)):
    """
    Login user and return JWT token
    """
    # Find user by email
    user = db.query(User).filter(User.email == credentials.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    # Create access token
    # Note: 'sub' must be a string for python-jose
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.delete("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Delete the current user's account and all associated data.
    This action is irreversible.
    """
    try:
        user_id = current_user.id
        
        # 1. Delete conversation messages and associated images
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == user_id
        ).all()
        
        # Delete associated image files
        UPLOADS_DIR = Path("uploads/images")
        for msg in messages:
            if msg.image_path:
                image_file = UPLOADS_DIR / msg.image_path.split('/')[-1]
                if image_file.exists():
                    try:
                        image_file.unlink()
                    except:
                        pass  # Continue even if image deletion fails
        
        db.query(ConversationMessage).filter(
            ConversationMessage.user_id == user_id
        ).delete()
        
        # 2. Delete workout logs
        db.query(WorkoutLog).filter(
            WorkoutLog.user_id == user_id
        ).delete()
        
        # 3. Delete nutrition logs
        db.query(NutritionLog).filter(
            NutritionLog.user_id == user_id
        ).delete()
        
        # 4. Delete mental fitness logs
        db.query(MentalFitnessLog).filter(
            MentalFitnessLog.user_id == user_id
        ).delete()
        
        # 5. Delete medical history
        db.query(MedicalHistory).filter(
            MedicalHistory.user_id == user_id
        ).delete()
        
        # 6. Delete user preferences
        db.query(UserPreferences).filter(
            UserPreferences.user_id == user_id
        ).delete()
        
        # 7. Delete user account
        db.query(User).filter(User.id == user_id).delete()
        
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting account: {str(e)}"
        )

