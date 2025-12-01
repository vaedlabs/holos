"""
Database setup script - Creates initial migration and runs it
Run this after setting up your virtual environment and installing dependencies
"""

import os
import sys
from sqlalchemy import create_engine, text
from app.database import Base, engine
from app.models import User, MedicalHistory, UserPreferences, WorkoutLog, NutritionLog, MentalFitnessLog, ConversationMessage
from dotenv import load_dotenv

load_dotenv()

def create_tables():
    """Create all database tables"""
    print("Creating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created successfully!")
        return True
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False

def check_database_connection():
    """Check if database connection works"""
    print("Checking database connection...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✓ Database connection successful!")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("  Make sure PostgreSQL is running and DATABASE_URL is correct in .env")
        return False

def main():
    """Main setup function"""
    print("=" * 50)
    print("Holos Database Setup")
    print("=" * 50)
    
    if not check_database_connection():
        print("\nPlease fix the database connection issue and try again.")
        sys.exit(1)
    
    if create_tables():
        print("\n✓ Database setup complete!")
        print("\nYou can now start the backend server:")
        print("  uvicorn app.main:app --reload")
    else:
        print("\n✗ Database setup failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()


