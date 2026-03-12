"""
Medical History model for storing user medical information.

This module defines the MedicalHistory model, which stores medical information
that is critical for ensuring safe exercise and nutrition recommendations.
The model has a one-to-one relationship with the User model.

IMPORTANT SAFETY CONSIDERATIONS:
- This data is used by AI agents to avoid recommending unsafe exercises or foods
- Medical information should be kept confidential and secure
- Agents check this data before recommending exercises to prevent injuries
- This is NOT a replacement for professional medical advice

Key Features:
- Medical conditions and physical limitations
- Current medications
- Additional medical notes
- Timestamp tracking for medical history updates
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class MedicalHistory(Base):
    """
    Medical History model storing user medical information for safety.
    
    This model stores medical information that AI agents use to provide safe
    exercise and nutrition recommendations. Each user has exactly one medical
    history record (one-to-one relationship with User model).
    
    CRITICAL: This data is used to prevent recommending exercises or foods that
    could be harmful based on the user's medical conditions, limitations, or medications.
    
    Attributes:
        id: Primary key, auto-incrementing integer
        user_id: Foreign key to User model (unique, one-to-one relationship)
        conditions: Medical conditions (JSON string or comma-separated)
        limitations: Physical limitations or restrictions (Text)
        medications: Current medications (Text)
        notes: Additional medical notes or information (Text)
        created_at: Timestamp when medical history was created
        updated_at: Timestamp when medical history was last updated
        
    Relationships:
        user: One-to-one relationship with User model
        
    Safety Usage:
        - Physical Fitness Agent checks conditions and limitations before recommending exercises
        - Nutrition Agent checks medications for potential food interactions
        - All agents use this data to avoid harmful recommendations
        - This is a safety feature, NOT medical diagnosis or treatment
        
    Note:
        - All fields are nullable to allow users to provide information incrementally
        - Medical information should be kept confidential (HIPAA considerations)
        - Users should consult healthcare providers for medical advice
        - This data helps agents provide safer recommendations but does not replace medical consultation
    """
    __tablename__ = "medical_history"

    # Primary key - auto-incrementing integer
    # Indexed for fast lookups by ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign key to User model
    # Unique constraint ensures one medical history record per user (one-to-one relationship)
    # Required field - cannot be null
    # Cascade delete: if user is deleted, medical history is also deleted
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Medical conditions - user's known medical conditions
    # Format: JSON string (e.g., ["diabetes", "hypertension"]) or comma-separated text
    # Examples: "diabetes", "hypertension", "heart_disease", "asthma", "arthritis"
    # Used by Physical Fitness Agent to avoid recommending unsafe exercises
    # Used by Nutrition Agent to avoid recommending foods that could worsen conditions
    # CRITICAL: Agents MUST check this before recommending exercises
    # Nullable to allow users who prefer not to share or have no conditions
    conditions = Column(Text, nullable=True)  # JSON string or comma-separated
    
    # Physical limitations - restrictions on physical activity
    # Format: Free-form text describing physical limitations
    # Examples: "knee injury", "lower back pain", "shoulder mobility issues", "no high-impact exercises"
    # Used by Physical Fitness Agent to avoid recommending exercises that could cause injury
    # CRITICAL: Agents MUST check this before recommending exercises
    # Nullable to allow users without physical limitations
    limitations = Column(Text, nullable=True)  # Physical limitations
    
    # Current medications - medications user is currently taking
    # Format: Free-form text listing medications
    # Examples: "metformin 500mg twice daily", "lisinopril 10mg daily", "aspirin 81mg"
    # Used by Nutrition Agent to check for potential food-drug interactions
    # Used by Physical Fitness Agent to understand exercise capacity
    # CRITICAL: Some medications affect exercise tolerance or require dietary restrictions
    # Nullable to allow users who prefer not to share or are not taking medications
    medications = Column(Text, nullable=True)  # Current medications
    
    # Additional medical notes - any other relevant medical information
    # Format: Free-form text for additional context
    # Examples: "Recent surgery recovery", "Pregnancy", "Post-rehabilitation"
    # Used by all agents to provide context-aware recommendations
    # Provides flexibility for users to add important medical context
    # Nullable to allow users without additional notes
    notes = Column(Text, nullable=True)  # Additional notes
    
    # Medical history creation timestamp
    # Automatically set to current time when medical history record is created
    # Timezone-aware DateTime for accurate time tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Medical history last update timestamp
    # Automatically updated to current time whenever medical history is modified
    # Timezone-aware DateTime for accurate time tracking
    # Only updates on actual changes (onupdate=func.now())
    # Important for tracking when medical information was last updated
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to User model
    # One-to-one relationship (each user has exactly one medical history record)
    # Access via: medical_history.user (returns User object)
    # Back-populates with User.medical_history
    user = relationship("User", back_populates="medical_history")

