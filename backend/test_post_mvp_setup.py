"""
Test script to verify Post-MVP components (Phases 1-4) are working correctly
Tests: Models, Tools, Agents
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

print("=" * 60)
print("Post-MVP Setup Test - Phases 1-4")
print("=" * 60)

# Test 1: Environment Variables
print("\n[1] Checking environment variables...")
try:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("  ⚠️  python-dotenv not installed, using system environment variables")
        pass
    
    required_vars = [
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "OPENAI_API_KEY"
    ]
    
    optional_vars = [
        "GOOGLE_GEMINI_API_KEY",
        "TAVILY_API_KEY"
    ]
    
    missing_required = []
    for var in required_vars:
        if not os.getenv(var):
            missing_required.append(var)
    
    if missing_required:
        print(f"  ⚠️  Missing required env vars: {', '.join(missing_required)}")
    else:
        print("  ✓ All required environment variables present")
    
    missing_optional = []
    for var in optional_vars:
        if not os.getenv(var):
            missing_optional.append(var)
    
    if missing_optional:
        print(f"  ⚠️  Missing optional env vars (for Phase 2-3): {', '.join(missing_optional)}")
    else:
        print("  ✓ All optional environment variables present")
        
except Exception as e:
    print(f"  ✗ Error loading environment: {e}")
    sys.exit(1)

# Test 2: Database Models
print("\n[2] Testing database models...")
try:
    from app.models import (
        User, MedicalHistory, UserPreferences, WorkoutLog,
        ConversationMessage, NutritionLog, MentalFitnessLog
    )
    print("  ✓ All models imported successfully")
    print(f"    - User, MedicalHistory, UserPreferences, WorkoutLog")
    print(f"    - ConversationMessage, NutritionLog, MentalFitnessLog")
except Exception as e:
    print(f"  ✗ Error importing models: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Base Agent Tools
print("\n[3] Testing base agent tools...")
try:
    from app.agents.base_agent import (
        GetMedicalHistoryTool,
        GetUserPreferencesTool,
        CreateWorkoutLogTool,
        CreateNutritionLogTool,
        CreateMentalFitnessLogTool,
        WebSearchTool
    )
    print("  ✓ All base agent tools imported successfully")
    print(f"    - GetMedicalHistoryTool, GetUserPreferencesTool")
    print(f"    - CreateWorkoutLogTool, CreateNutritionLogTool")
    print(f"    - CreateMentalFitnessLogTool, WebSearchTool")
except Exception as e:
    print(f"  ✗ Error importing base agent tools: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Physical Fitness Agent
print("\n[4] Testing Physical Fitness Agent...")
try:
    from app.agents.physical_fitness_agent import PhysicalFitnessAgent
    print("  ✓ PhysicalFitnessAgent imported successfully")
except Exception as e:
    print(f"  ✗ Error importing PhysicalFitnessAgent: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Nutrition Agent
print("\n[5] Testing Nutrition Agent...")
try:
    from app.agents.nutrition_agent import NutritionAgent
    print("  ✓ NutritionAgent imported successfully")
    
    # Check if Gemini API key is available
    if os.getenv("GOOGLE_GEMINI_API_KEY"):
        print("  ✓ GOOGLE_GEMINI_API_KEY is set")
    else:
        print("  ⚠️  GOOGLE_GEMINI_API_KEY not set (required for Nutrition Agent)")
        
except Exception as e:
    print(f"  ✗ Error importing NutritionAgent: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Mental Fitness Agent
print("\n[6] Testing Mental Fitness Agent...")
try:
    from app.agents.mental_fitness_agent import MentalFitnessAgent
    print("  ✓ MentalFitnessAgent imported successfully")
except Exception as e:
    print(f"  ✗ Error importing MentalFitnessAgent: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Dependencies Check
print("\n[7] Checking Python dependencies...")
dependencies = {
    "langchain": "LangChain",
    "langchain_openai": "LangChain OpenAI",
    "langchain_google_genai": "LangChain Google GenAI",
    "google.generativeai": "Google Generative AI",
    "tavily": "Tavily",
    "PIL": "Pillow",
    "sqlalchemy": "SQLAlchemy",
    "fastapi": "FastAPI",
}

missing_deps = []
for module, name in dependencies.items():
    try:
        __import__(module)
        print(f"  ✓ {name} installed")
    except ImportError:
        print(f"  ✗ {name} NOT installed")
        missing_deps.append(name)

if missing_deps:
    print(f"\n  ⚠️  Missing dependencies: {', '.join(missing_deps)}")
    print("  Install with: pip install -r requirements.txt")

# Test 8: Database Connection (if DATABASE_URL is set)
print("\n[8] Testing database connection...")
try:
    from app.database import engine
    from sqlalchemy import inspect
    
    if os.getenv("DATABASE_URL"):
        # Try to connect
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
                print(f"  ⚠️  Missing tables: {', '.join(missing_tables)}")
                print("  Run migrations: alembic upgrade head")
            else:
                print("  ✓ Database connection successful")
                print(f"  ✓ All expected tables exist ({len(expected_tables)} tables)")
    else:
        print("  ⚠️  DATABASE_URL not set, skipping connection test")
        
except Exception as e:
    print(f"  ⚠️  Database connection test failed: {e}")
    print("  This is OK if database is not set up yet")

# Test 9: Tool Schema Validation
print("\n[9] Testing tool schemas...")
try:
    from app.agents.base_agent import (
        CreateNutritionLogInput,
        CreateMentalFitnessLogInput,
        CreateWorkoutLogInput,
        WebSearchInput
    )
    
    # Test Nutrition Log Input
    nutrition_input = CreateNutritionLogInput(
        meal_type="breakfast",
        foods='{"eggs": 2, "toast": 1}',
        calories=350.0,
        macros='{"protein": 20, "carbs": 30, "fats": 15}'
    )
    print("  ✓ CreateNutritionLogInput schema valid")
    
    # Test Mental Fitness Log Input
    mental_input = CreateMentalFitnessLogInput(
        activity_type="meditation",
        duration_minutes=15.0,
        mood_before="5",
        mood_after="7"
    )
    print("  ✓ CreateMentalFitnessLogInput schema valid")
    
    # Test Web Search Input
    web_input = WebSearchInput(query="test query")
    print("  ✓ WebSearchInput schema valid")
    
except Exception as e:
    print(f"  ✗ Error validating tool schemas: {e}")
    import traceback
    traceback.print_exc()

# Test 10: Agent Instantiation (mock test - no actual DB needed)
print("\n[10] Testing agent class structure...")
try:
    # Check Physical Fitness Agent
    from app.agents.physical_fitness_agent import PhysicalFitnessAgent
    assert hasattr(PhysicalFitnessAgent, 'recommend_exercise')
    assert hasattr(PhysicalFitnessAgent, 'create_workout_plan')
    print("  ✓ PhysicalFitnessAgent has required methods")
    
    # Check Nutrition Agent
    from app.agents.nutrition_agent import NutritionAgent
    assert hasattr(NutritionAgent, 'recommend_meal')
    assert hasattr(NutritionAgent, 'analyze_food_image')
    print("  ✓ NutritionAgent has required methods")
    
    # Check Mental Fitness Agent
    from app.agents.mental_fitness_agent import MentalFitnessAgent
    assert hasattr(MentalFitnessAgent, 'recommend_practice')
    assert hasattr(MentalFitnessAgent, 'create_wellness_plan')
    print("  ✓ MentalFitnessAgent has required methods")
    
except Exception as e:
    print(f"  ✗ Error checking agent structure: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)
print("✓ Core components (models, tools, agents) are properly structured")
print("⚠️  Check environment variables and database setup if needed")
print("⚠️  Install missing dependencies if any were reported")
print("\nIf all tests passed, you're ready for Phase 5: Coordinator Agent!")
print("=" * 60)

