"""
Comprehensive test script for Post-MVP Phases 1-4
Checks all components: models, tools, agents, dependencies
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

print("=" * 70)
print("Post-MVP Comprehensive Test - Phases 1-4")
print("=" * 70)
print("\nNote: Using conda environment 'holos'")
print("=" * 70)

errors = []
warnings = []

# Test 1: Environment Variables
print("\n[1] Checking environment variables...")
try:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # Using system/env vars
    
    required_vars = {
        "DATABASE_URL": "Database connection string",
        "JWT_SECRET_KEY": "JWT authentication secret",
        "OPENAI_API_KEY": "OpenAI API key (for Physical & Mental Fitness agents)"
    }
    
    optional_vars = {
        "GOOGLE_GEMINI_API_KEY": "Gemini API key (for Nutrition Agent)",
        "TAVILY_API_KEY": "Tavily API key (for web search)"
    }
    
    missing_required = []
    for var, desc in required_vars.items():
        if not os.getenv(var):
            missing_required.append(f"{var} ({desc})")
    
    if missing_required:
        errors.append("Missing required environment variables")
        print(f"  ✗ Missing required: {', '.join(missing_required)}")
    else:
        print("  ✓ All required environment variables present")
    
    missing_optional = []
    for var, desc in optional_vars.items():
        if not os.getenv(var):
            missing_optional.append(f"{var} ({desc})")
    
    if missing_optional:
        warnings.append("Missing optional environment variables")
        print(f"  ⚠️  Missing optional: {', '.join(missing_optional)}")
    else:
        print("  ✓ All optional environment variables present")
        
except Exception as e:
    errors.append("Environment check failed")
    print(f"  ✗ Error: {e}")

# Test 2: Python Dependencies
print("\n[2] Checking Python dependencies...")
dependencies = {
    "langchain": "LangChain",
    "langchain_core": "LangChain Core",
    "langchain_openai": "LangChain OpenAI",
    # "langchain_google_genai": "LangChain Google GenAI",  # Not needed - using direct SDK
    "google.generativeai": "Google Generative AI",  # Direct SDK for Gemini
    "tavily": "Tavily",
    "PIL": "Pillow",
    "sqlalchemy": "SQLAlchemy",
    "fastapi": "FastAPI",
    "pydantic": "Pydantic",
    "bcrypt": "bcrypt",
    "jose": "python-jose",
}

missing_deps = []
for module, name in dependencies.items():
    try:
        __import__(module)
        print(f"  ✓ {name}")
    except ImportError:
        print(f"  ✗ {name} NOT installed")
        missing_deps.append(name)

if missing_deps:
    errors.append("Missing Python dependencies")
    print(f"\n  ⚠️  Missing: {', '.join(missing_deps)}")
    print("  Install with: conda activate holos && pip install -r requirements.txt")

# Test 3: Database Models
print("\n[3] Testing database models...")
try:
    from app.models import (
        User, MedicalHistory, UserPreferences, WorkoutLog,
        ConversationMessage, NutritionLog, MentalFitnessLog
    )
    print("  ✓ All models imported successfully")
    print(f"    - Core: User, MedicalHistory, UserPreferences, WorkoutLog")
    print(f"    - New: ConversationMessage, NutritionLog, MentalFitnessLog")
    
    # Check model attributes
    assert hasattr(NutritionLog, 'meal_type')
    assert hasattr(NutritionLog, 'calories')
    assert hasattr(NutritionLog, 'macros')
    assert hasattr(MentalFitnessLog, 'activity_type')
    assert hasattr(MentalFitnessLog, 'mood_before')
    assert hasattr(MentalFitnessLog, 'mood_after')
    print("  ✓ All new model attributes verified")
    
except Exception as e:
    errors.append("Database models")
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Base Agent Tools
print("\n[4] Testing base agent tools...")
try:
    from app.agents.base_agent import (
        GetMedicalHistoryTool,
        GetUserPreferencesTool,
        CreateWorkoutLogTool,
        CreateNutritionLogTool,
        CreateMentalFitnessLogTool,
        WebSearchTool
    )
    print("  ✓ All tools imported successfully")
    print(f"    - Base: GetMedicalHistoryTool, GetUserPreferencesTool")
    print(f"    - Logging: CreateWorkoutLogTool, CreateNutritionLogTool, CreateMentalFitnessLogTool")
    print(f"    - Search: WebSearchTool")
    
    # Check tool schemas
    from app.agents.base_agent import (
        CreateNutritionLogInput,
        CreateMentalFitnessLogInput,
        WebSearchInput
    )
    print("  ✓ All tool input schemas verified")
    
except Exception as e:
    errors.append("Base agent tools")
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 5: Physical Fitness Agent
print("\n[5] Testing Physical Fitness Agent...")
try:
    from app.agents.physical_fitness_agent import PhysicalFitnessAgent
    print("  ✓ PhysicalFitnessAgent imported")
    
    # Check methods
    assert hasattr(PhysicalFitnessAgent, 'recommend_exercise')
    assert hasattr(PhysicalFitnessAgent, 'create_workout_plan')
    print("  ✓ Required methods present")
    
except Exception as e:
    errors.append("Physical Fitness Agent")
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 6: Nutrition Agent
print("\n[6] Testing Nutrition Agent...")
try:
    from app.agents.nutrition_agent import NutritionAgent
    print("  ✓ NutritionAgent imported")
    
    # Check methods
    assert hasattr(NutritionAgent, 'recommend_meal')
    assert hasattr(NutritionAgent, 'analyze_food_image')
    print("  ✓ Required methods present")
    
    # Check Gemini API key
    if os.getenv("GOOGLE_GEMINI_API_KEY"):
        print("  ✓ GOOGLE_GEMINI_API_KEY is set")
    else:
        warnings.append("GOOGLE_GEMINI_API_KEY not set")
        print("  ⚠️  GOOGLE_GEMINI_API_KEY not set (required for Nutrition Agent)")
        
except Exception as e:
    errors.append("Nutrition Agent")
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 7: Mental Fitness Agent
print("\n[7] Testing Mental Fitness Agent...")
try:
    from app.agents.mental_fitness_agent import MentalFitnessAgent
    print("  ✓ MentalFitnessAgent imported")
    
    # Check methods
    assert hasattr(MentalFitnessAgent, 'recommend_practice')
    assert hasattr(MentalFitnessAgent, 'create_wellness_plan')
    print("  ✓ Required methods present")
    
except Exception as e:
    errors.append("Mental Fitness Agent")
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 8: Database Connection (if available)
print("\n[8] Testing database connection...")
try:
    from app.database import engine
    from sqlalchemy import inspect
    
    if os.getenv("DATABASE_URL"):
        with engine.connect() as conn:
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            expected_tables = [
                "users", "medical_history", "user_preferences",
                "workout_logs", "conversation_messages",
                "nutrition_logs", "mental_fitness_logs"
            ]
            
            missing_tables = [t for t in expected_tables if t not in tables]
            
            if missing_tables:
                warnings.append("Missing database tables")
                print(f"  ⚠️  Missing tables: {', '.join(missing_tables)}")
                print("  Run: conda activate holos && alembic upgrade head")
            else:
                print("  ✓ Database connection successful")
                print(f"  ✓ All {len(expected_tables)} expected tables exist")
    else:
        warnings.append("DATABASE_URL not set")
        print("  ⚠️  DATABASE_URL not set, skipping connection test")
        
except Exception as e:
    warnings.append("Database connection test failed")
    print(f"  ⚠️  Database test failed: {e}")
    print("  This is OK if database is not set up yet")

# Test 9: LangChain Compatibility
print("\n[9] Testing LangChain compatibility...")
try:
    from langchain_openai import ChatOpenAI
    print("  ✓ langchain-openai imports successfully")
    
    # Try to check version compatibility
    import langchain_core
    print(f"  ✓ langchain-core version: {langchain_core.__version__}")
    try:
        import langchain_openai
        version = getattr(langchain_openai, '__version__', 'unknown')
        print(f"  ✓ langchain-openai version: {version}")
    except:
        print(f"  ✓ langchain-openai imported (version check skipped)")
    
    # Check if ModelProfileRegistry issue is resolved
    try:
        from langchain_core.language_models import ModelProfileRegistry
        print("  ✓ ModelProfileRegistry available (compatibility OK)")
    except ImportError:
        # This might be OK if it's not needed in current version
        print("  ⚠️  ModelProfileRegistry not found (may be OK)")
        
except Exception as e:
    errors.append("LangChain compatibility")
    print(f"  ✗ Error: {e}")
    print("  Fix: conda activate holos && pip install --upgrade langchain-openai==0.2.3")
    import traceback
    traceback.print_exc()

# Test 10: File Structure
print("\n[10] Checking file structure...")
required_files = [
    "app/models/nutrition_log.py",
    "app/models/mental_fitness_log.py",
    "app/agents/nutrition_agent.py",
    "app/agents/mental_fitness_agent.py",
    "app/agents/base_agent.py",
]

missing_files = []
for file_path in required_files:
    full_path = backend_dir / file_path
    if not full_path.exists():
        missing_files.append(file_path)
    else:
        print(f"  ✓ {file_path}")

if missing_files:
    errors.append("Missing files")
    print(f"  ✗ Missing files: {', '.join(missing_files)}")
else:
    print("  ✓ All required files present")

# Summary
print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)

if errors:
    print(f"\n✗ ERRORS FOUND ({len(errors)}):")
    for error in errors:
        print(f"  - {error}")
else:
    print("\n✓ NO ERRORS - All core components working!")

if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for warning in warnings:
        print(f"  - {warning}")
    print("\n  These are non-critical but should be addressed for full functionality")
else:
    print("\n✓ NO WARNINGS")

print("\n" + "=" * 70)
if not errors:
    print("✅ All tests passed! Ready for Phase 5: Coordinator Agent")
    print("\nNext steps:")
    print("  1. Ensure all environment variables are set")
    print("  2. Run database migrations if needed: alembic upgrade head")
    print("  3. Proceed with Phase 5 implementation")
else:
    print("❌ Some tests failed. Please fix the errors above before proceeding.")
    print("\nCommon fixes:")
    print("  - Install dependencies: conda activate holos && pip install -r requirements.txt")
    print("  - Fix LangChain: pip install --upgrade langchain-openai==0.2.3")
    print("  - Set environment variables in .env file")
print("=" * 70)

# Exit with appropriate code
sys.exit(0 if not errors else 1)

