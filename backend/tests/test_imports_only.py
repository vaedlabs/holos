"""
Simple import test - checks if all Post-MVP components can be imported
Run this to verify code structure is correct
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

print("=" * 60)
print("Post-MVP Import Test - Phases 1-4")
print("=" * 60)

errors = []

# Test 1: Models
print("\n[1] Testing models...")
try:
    from app.models import (
        User, MedicalHistory, UserPreferences, WorkoutLog,
        ConversationMessage, NutritionLog, MentalFitnessLog
    )
    print("  ✓ All models imported")
except Exception as e:
    print(f"  ✗ Model import failed: {e}")
    errors.append("Models")

# Test 2: Base Agent Tools
print("\n[2] Testing base agent tools...")
try:
    from app.agents.base_agent import (
        GetMedicalHistoryTool,
        GetUserPreferencesTool,
        CreateWorkoutLogTool,
        CreateNutritionLogTool,
        CreateMentalFitnessLogTool,
        WebSearchTool
    )
    print("  ✓ All tools imported")
except Exception as e:
    print(f"  ✗ Tool import failed: {e}")
    errors.append("Tools")

# Test 3: Agents
print("\n[3] Testing agents...")
try:
    from app.agents.physical_fitness_agent import PhysicalFitnessAgent
    print("  ✓ PhysicalFitnessAgent imported")
except Exception as e:
    print(f"  ✗ PhysicalFitnessAgent import failed: {e}")
    errors.append("PhysicalFitnessAgent")

try:
    from app.agents.nutrition_agent import NutritionAgent
    print("  ✓ NutritionAgent imported")
except Exception as e:
    print(f"  ✗ NutritionAgent import failed: {e}")
    errors.append("NutritionAgent")

try:
    from app.agents.mental_fitness_agent import MentalFitnessAgent
    print("  ✓ MentalFitnessAgent imported")
except Exception as e:
    print(f"  ✗ MentalFitnessAgent import failed: {e}")
    errors.append("MentalFitnessAgent")

# Test 4: Agent Methods
print("\n[4] Testing agent methods...")
try:
    from app.agents.physical_fitness_agent import PhysicalFitnessAgent
    assert hasattr(PhysicalFitnessAgent, 'recommend_exercise')
    assert hasattr(PhysicalFitnessAgent, 'create_workout_plan')
    print("  ✓ PhysicalFitnessAgent methods OK")
except Exception as e:
    print(f"  ✗ PhysicalFitnessAgent methods check failed: {e}")
    errors.append("PhysicalFitnessAgent methods")

try:
    from app.agents.nutrition_agent import NutritionAgent
    assert hasattr(NutritionAgent, 'recommend_meal')
    assert hasattr(NutritionAgent, 'analyze_food_image')
    print("  ✓ NutritionAgent methods OK")
except Exception as e:
    print(f"  ✗ NutritionAgent methods check failed: {e}")
    errors.append("NutritionAgent methods")

try:
    from app.agents.mental_fitness_agent import MentalFitnessAgent
    assert hasattr(MentalFitnessAgent, 'recommend_practice')
    assert hasattr(MentalFitnessAgent, 'create_wellness_plan')
    print("  ✓ MentalFitnessAgent methods OK")
except Exception as e:
    print(f"  ✗ MentalFitnessAgent methods check failed: {e}")
    errors.append("MentalFitnessAgent methods")

# Summary
print("\n" + "=" * 60)
if not errors:
    print("✓ All imports successful!")
    print("\nNext: Test with actual database and API keys")
    print("Run: python test_setup.py (for full integration test)")
else:
    print(f"✗ {len(errors)} import error(s) found:")
    for error in errors:
        print(f"  - {error}")
print("=" * 60)

