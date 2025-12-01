"""
Physical Fitness Agent - Specialized agent for workout planning and exercise recommendations
"""

from typing import Dict, Any
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.services.medical_service import check_user_exercise_conflicts


class PhysicalFitnessAgent(BaseAgent):
    """Physical Fitness Agent specialized for exercise recommendations and workout planning"""
    
    def __init__(self, user_id: int, db: Session, model_name: str = "gpt-4.1"):
        super().__init__(user_id, db, model_name)
    
    def _get_system_prompt(self) -> str:
        """Get specialized system prompt for physical fitness agent"""
        return """You are a knowledgeable and encouraging Physical Fitness Coach. Your role is to help users with:
        
1. **Exercise Recommendations**: Suggest appropriate exercises based on user preferences and medical history
2. **Workout Planning**: Create structured workout plans (calisthenics, weight lifting, cardio, HIIT, etc.)
3. **Form and Technique**: Provide guidance on proper form and technique
4. **Progression**: Help users progress safely and effectively
5. **Medical Safety**: ALWAYS check medical history before recommending exercises. If an exercise conflicts with a medical condition, warn the user and suggest alternatives.

**CRITICAL: You will receive the user's medical history and fitness preferences in the system message below. USE THIS INFORMATION IMMEDIATELY. Do NOT ask the user for information they have already provided. Reference their specific goals, preferences, and medical conditions in your responses.**

**Important Guidelines:**
- The user's medical history and preferences will be provided to you automatically - USE THEM
- If an exercise conflicts with medical conditions, clearly warn the user and suggest safer alternatives
- Be encouraging but emphasize safety and proper form
- Create workout plans that match the user's experience level and preferences
- Use the create_workout_log tool when recommending or completing workouts
- Reference the user's specific goals and preferences in your recommendations

**Exercise Types You Can Recommend:**
- Calisthenics (push-ups, pull-ups, bodyweight exercises)
- Weight Lifting (free weights, machines)
- Cardio (running, cycling, swimming, etc.)
- HIIT (High-Intensity Interval Training)
- Yoga
- Pilates
- Stretching and flexibility work

Be specific, actionable, and safety-focused in all your recommendations. Personalize your responses based on the user's provided information."""
    
    async def recommend_exercise(self, user_query: str) -> Dict[str, Any]:
        """
        Recommend exercises based on user query.
        Returns response with potential medical conflict warnings.
        """
        # Get agent response
        response = await self.run(user_query)
        
        # Check for exercise mentions and validate against medical history
        warnings = []
        checked_exercises = set()  # Avoid duplicate warnings
        
        # Comprehensive exercise keywords to check (matches medical_service.py conflicts)
        exercise_keywords = [
            "squat", "squats", "deadlift", "deadlifts", "lunge", "lunges",
            "press", "overhead press", "pull-up", "pull-ups", "push-up", "push-ups",
            "running", "run", "jumping", "jump", "jumps", "overhead",
            "heavy lifting", "heavy", "weight", "weights",
            "leg press", "step-up", "step-ups", "bent-over row", "bent-over rows",
            "lateral raise", "lateral raises", "upright row", "upright rows",
            "shoulder press", "shoulder presses", "plank", "planks",
            "handstand", "handstands", "wrist curl", "wrist curls",
            "box jump", "box jumps", "neck bridge", "neck bridges",
            "burpees", "burpee", "hiit", "high intensity", "sprinting", "sprint",
            "circuit training", "max effort", "endurance running", "dips", "dip",
            "plyometrics", "good mornings", "back extensions", "bridges", "headstands",
            "abdominal crunches", "crunches", "lying on back"
        ]
        
        response_lower = response.lower()
        block_warnings = []
        warning_warnings = []
        
        # Check each exercise keyword
        for keyword in exercise_keywords:
            if keyword in response_lower and keyword not in checked_exercises:
                checked_exercises.add(keyword)
                conflict_check = self.check_exercise_safety(keyword)
                if conflict_check.get("has_conflict"):
                    # Group warnings by severity
                    warning_msg = conflict_check.get("message")
                    severity = conflict_check.get("severity", "warning")
                    
                    if warning_msg:
                        if severity == "block":
                            if warning_msg not in block_warnings:
                                block_warnings.append(warning_msg)
                        else:
                            if warning_msg not in warning_warnings:
                                warning_warnings.append(warning_msg)
        
        # Combine warnings (blocks first, then warnings)
        warnings = block_warnings + warning_warnings
        
        return {
            "response": response,
            "warnings": warnings if warnings else None
        }
    
    async def create_workout_plan(self, duration_minutes: int = 30, exercise_type: str = None) -> str:
        """
        Create a structured workout plan for the user.
        """
        query = f"Create a {duration_minutes}-minute workout plan"
        if exercise_type:
            query += f" focused on {exercise_type}"
        query += ". Make sure to check my medical history first and create a plan that's safe for me."
        
        result = await self.recommend_exercise(query)
        return result["response"]

