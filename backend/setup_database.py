"""
Database setup script - Creates initial database schema.

This script initializes the database by creating all tables defined in SQLAlchemy
models. It's used for initial setup and development environments. For production,
use Alembic migrations instead (alembic upgrade head).

Initialization Process:
    1. Load environment variables (.env file)
    2. Check database connection (PostgreSQL must be running)
    3. Create all tables from SQLAlchemy models
    4. Verify setup completion

Usage:
    python setup_database.py

Prerequisites:
    - PostgreSQL database running
    - DATABASE_URL set in .env file
    - Virtual environment activated
    - Dependencies installed (pip install -r requirements.txt)

Note:
    This script uses SQLAlchemy's create_all() which creates tables based on
    current model definitions. It does NOT handle migrations or schema changes.
    For schema changes, use Alembic migrations:
        alembic revision --autogenerate -m "description"
        alembic upgrade head

Models Created:
    - users (authentication, user accounts)
    - user_preferences (fitness/wellness preferences)
    - medical_history (medical conditions, exercise conflicts)
    - workout_logs (exercise tracking)
    - nutrition_logs (meal tracking)
    - mental_fitness_logs (wellness activity tracking)
    - conversation_messages (chat history)
    - agent_execution_logs (agent observability)
"""

import os
import sys
from sqlalchemy import create_engine, text
from app.database import Base, engine
# Import models to ensure they're registered with Base.metadata
# Without imports, create_all() won't know which tables to create
from app.models import User, MedicalHistory, UserPreferences, WorkoutLog, NutritionLog, MentalFitnessLog, ConversationMessage
from dotenv import load_dotenv

# Load environment variables from .env file
# Required for DATABASE_URL configuration
load_dotenv()

def create_tables():
    """
    Create all database tables from SQLAlchemy models.
    
    Uses Base.metadata.create_all() to create tables based on model definitions.
    This is a one-time setup operation - subsequent runs won't recreate existing
    tables (idempotent operation).
    
    Returns:
        bool: True if tables created successfully, False otherwise
        
    Note:
        - Creates tables only if they don't exist (idempotent)
        - Does NOT handle migrations or schema changes
        - For production, use Alembic migrations instead
    """
    print("Creating database tables...")
    try:
        # Create all tables defined in SQLAlchemy models
        # Base.metadata contains all table definitions from imported models
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created successfully!")
        return True
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False

def check_database_connection():
    """
    Check if database connection is working.
    
    Performs a simple query (SELECT 1) to verify PostgreSQL is accessible
    and DATABASE_URL is correctly configured. This prevents attempting table
    creation on an invalid connection.
    
    Returns:
        bool: True if connection successful, False otherwise
        
    Error Handling:
        - Catches connection errors (database not running, wrong URL, etc.)
        - Provides helpful error message with troubleshooting steps
    """
    print("Checking database connection...")
    try:
        # Test connection with simple query
        # If this succeeds, database is accessible and credentials are correct
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))  # Simple connectivity test
            print("✓ Database connection successful!")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("  Make sure PostgreSQL is running and DATABASE_URL is correct in .env")
        return False

def main():
    """
    Main setup function - orchestrates database initialization.
    
    Execution Flow:
        1. Check database connection (fail fast if connection invalid)
        2. Create all tables (if connection successful)
        3. Provide next steps (start backend server)
        
    Exit Codes:
        - 0: Success (tables created)
        - 1: Failure (connection error or table creation error)
    """
    print("=" * 50)
    print("Holos Database Setup")
    print("=" * 50)
    
    # Step 1: Verify database connection before attempting table creation
    # Fail fast if connection is invalid (saves time and provides clear error)
    if not check_database_connection():
        print("\nPlease fix the database connection issue and try again.")
        sys.exit(1)  # Exit with error code
    
    # Step 2: Create tables if connection is valid
    if create_tables():
        print("\n✓ Database setup complete!")
        print("\nYou can now start the backend server:")
        print("  uvicorn app.main:app --reload")
    else:
        print("\n✗ Database setup failed. Please check the errors above.")
        sys.exit(1)  # Exit with error code

if __name__ == "__main__":
    main()


