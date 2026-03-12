"""
Quick test script to verify backend setup
Run this to test if everything is configured correctly
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test if all imports work"""
    print("Testing imports...")
    try:
        from app.main import app
        print("✓ FastAPI app imports successfully")
        
        from app.database import Base, engine, get_db
        print("✓ Database imports successfully")
        
        from app.models import User, MedicalHistory, UserPreferences, WorkoutLog, NutritionLog, MentalFitnessLog
        print("✓ Models import successfully")
        
        from app.auth import verify_password, get_password_hash, create_access_token
        print("✓ Auth utilities import successfully")
        
        from app.services.medical_service import get_medical_history, check_exercise_conflict
        print("✓ Medical service imports successfully")
        
        # Test base agent import (may fail if LangChain structure is different)
        try:
            from app.agents.base_agent import BaseAgent
            print("✓ Base agent imports successfully")
        except ImportError as e:
            print(f"⚠ Base agent import warning: {e}")
            print("  This may be due to LangChain version differences. Agent functionality may be limited.")
        
        from app.routers.auth import router
        print("✓ Auth router imports successfully")
        
        return True
    except Exception as e:
        print(f"✗ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_connection():
    """Test database connection"""
    print("\nTesting database connection...")
    try:
        from app.database import engine
        from sqlalchemy import text
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("  Make sure PostgreSQL is running and DATABASE_URL is set correctly")
        return False

def test_models():
    """Test model creation"""
    print("\nTesting models...")
    try:
        from app.models import User, MedicalHistory, UserPreferences, WorkoutLog
        
        # Check if models have required attributes
        assert hasattr(User, 'email')
        assert hasattr(User, 'password_hash')
        assert hasattr(MedicalHistory, 'conditions')
        assert hasattr(UserPreferences, 'goals')
        assert hasattr(WorkoutLog, 'exercise_type')
        
        print("✓ All models have required attributes")
        return True
    except Exception as e:
        print(f"✗ Model test failed: {e}")
        return False

def test_auth_functions():
    """Test auth utility functions"""
    print("\nTesting auth functions...")
    try:
        from app.auth import get_password_hash, verify_password
        
        # Test password hashing (use short password to avoid bcrypt 72-byte limit)
        password = "test123"
        hashed = get_password_hash(password)
        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$2")  # bcrypt hash should start with $2
        
        # Test verification
        assert verify_password(password, hashed) == True
        assert verify_password("wrong_password", hashed) == False
        
        print("✓ Password hashing and verification work correctly")
        return True
    except Exception as e:
        print(f"✗ Auth function test failed: {e}")
        print("  Try: pip install --upgrade bcrypt passlib[bcrypt]")
        import traceback
        traceback.print_exc()
        return False

def test_medical_service():
    """Test medical service functions"""
    print("\nTesting medical service...")
    try:
        from app.services.medical_service import check_exercise_conflict, get_conflicting_exercises
        
        # Test conflict detection
        assert check_exercise_conflict("knee injury", "squats") == True
        assert check_exercise_conflict("knee injury", "swimming") == False
        assert check_exercise_conflict("back pain", "deadlifts") == True
        
        # Test conflicting exercises list
        conflicts = get_conflicting_exercises("knee injury, back pain")
        assert "squats" in conflicts
        assert "deadlifts" in conflicts
        
        print("✓ Medical service conflict detection works correctly")
        return True
    except Exception as e:
        print(f"✗ Medical service test failed: {e}")
        return False

def test_environment_variables():
    """Test environment variables"""
    print("\nTesting environment variables...")
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    
    required_vars = {
        "DATABASE_URL": os.getenv("DATABASE_URL"),
        "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
    }
    
    all_set = True
    for var_name, var_value in required_vars.items():
        if var_value:
            print(f"✓ {var_name} is set")
        else:
            print(f"✗ {var_name} is not set (using default or will fail)")
            if var_name == "OPENAI_API_KEY":
                print("  Warning: OpenAI API key is required for agents to work")
            all_set = False
    
    return all_set

def main():
    """Run all tests"""
    print("=" * 50)
    print("Holos Backend Setup Test")
    print("=" * 50)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("Environment Variables", test_environment_variables()))
    results.append(("Models", test_models()))
    results.append(("Auth Functions", test_auth_functions()))
    results.append(("Medical Service", test_medical_service()))
    results.append(("Database Connection", test_database_connection()))
    
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Backend is ready to use.")
        print("\nNext steps:")
        print("1. Run database migrations: alembic upgrade head")
        print("2. Start the server: uvicorn app.main:app --reload")
        print("3. Test API endpoints at http://localhost:8000/docs")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

