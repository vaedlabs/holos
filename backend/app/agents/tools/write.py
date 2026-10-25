"""
Write tools: workout, nutrition and mental fitness logs.

Moved unchanged from app/agents/base_agent.py (Plan P2.1).
P2.2 replaces these with async tools.
"""

from langchain_core.tools import BaseTool
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, DBAPIError
from app.models.workout_log import WorkoutLog
from app.models.nutrition_log import NutritionLog
from app.models.mental_fitness_log import MentalFitnessLog
from app.exceptions.agent_exceptions import (
    ToolExecutionError,
    ToolInputValidationError,
    ToolRetryableError,
    is_retryable_tool_error
)
import json
from pydantic import BaseModel, Field


class CreateNutritionLogInput(BaseModel):
    """Input for create_nutrition_log tool"""
    meal_type: str = Field(description="Type of meal: breakfast, lunch, dinner, or snack")
    foods: str = Field(description="Food items as JSON string or plain text")
    calories: float = Field(description="Total calories for the meal")
    macros: str = Field(default="{}", description="Macros as JSON string with protein, carbs, fats (in grams)")
    notes: str = Field(default="", description="Optional notes about the meal")


class CreateNutritionLogTool(BaseTool):
    """Tool to create a nutrition log entry"""
    name: str = "create_nutrition_log"
    description: str = "Create a nutrition log entry for the user. Use this when the user eats a meal, when analyzing food images, or when recommending meal plans. Always log meals with accurate calorie and macro information."
    args_schema: type = CreateNutritionLogInput
    
    user_id: int
    db: Session
    
    def _run(self, meal_type: str, foods: str, calories: float, macros: str = "{}", notes: str = "") -> str:
        """Create nutrition log entry"""
        # P0.4: Input validation
        invalid_fields = []
        if not meal_type or not isinstance(meal_type, str) or not meal_type.strip():
            invalid_fields.append("meal_type")
        if not isinstance(calories, (int, float)) or calories < 0:
            invalid_fields.append("calories")
        if invalid_fields:
            raise ToolInputValidationError(
                self.name,
                f"Invalid input fields: {', '.join(invalid_fields)}",
                invalid_fields
            )
        
        try:
            # Parse foods if it's a JSON string
            try:
                foods_json = json.loads(foods) if foods else {}
            except json.JSONDecodeError:
                foods_json = foods  # Use as-is if not valid JSON
            
            # Parse macros if it's a JSON string
            try:
                macros_json = json.loads(macros) if macros else {}
            except json.JSONDecodeError:
                macros_json = macros  # Use as-is if not valid JSON
            
            nutrition_log = NutritionLog(
                user_id=self.user_id,
                meal_type=meal_type,
                foods=json.dumps(foods_json) if isinstance(foods_json, dict) else foods,
                calories=calories,
                macros=json.dumps(macros_json) if isinstance(macros_json, dict) else macros,
                notes=notes
            )
            
            self.db.add(nutrition_log)
            self.db.commit()
            self.db.refresh(nutrition_log)
            
            return f"Nutrition log created successfully. Log ID: {nutrition_log.id}, Calories: {calories}"
        except (OperationalError, DBAPIError) as e:
            # P0.4: Database errors might be retryable (deadlocks, timeouts)
            self.db.rollback()
            if is_retryable_tool_error(e):
                raise ToolRetryableError(
                    self.name,
                    f"Database error (retryable): {str(e)}",
                    original_error=e
                )
            raise ToolExecutionError(
                self.name,
                f"Database error: {str(e)}",
                original_error=e
            )
        except Exception as e:
            # P0.4: Raise exception instead of returning error string
            self.db.rollback()
            raise ToolExecutionError(
                self.name,
                f"Failed to create nutrition log: {str(e)}",
                original_error=e
            )


class CreateMentalFitnessLogInput(BaseModel):
    """Input for create_mental_fitness_log tool"""
    activity_type: str = Field(description="Type of activity: meditation, mindfulness, journaling, breathing exercises, yoga, etc.")
    duration_minutes: float = Field(description="Duration of activity in minutes")
    mood_before: str = Field(default="", description="Mood or mental state before the activity (scale 1-10 or description)")
    mood_after: str = Field(default="", description="Mood or mental state after the activity (scale 1-10 or description)")
    notes: str = Field(default="", description="Optional notes about the activity")


class CreateMentalFitnessLogTool(BaseTool):
    """Tool to create a mental fitness log entry"""
    name: str = "create_mental_fitness_log"
    description: str = "Create a mental fitness log entry for the user. Use this when the user completes a mental wellness activity (meditation, mindfulness, journaling, etc.) or when recommending mental wellness practices."
    args_schema: type = CreateMentalFitnessLogInput
    
    user_id: int
    db: Session
    
    def _run(self, activity_type: str, duration_minutes: float, mood_before: str = "", mood_after: str = "", notes: str = "") -> str:
        """Create mental fitness log entry"""
        # P0.4: Input validation
        invalid_fields = []
        if not activity_type or not isinstance(activity_type, str) or not activity_type.strip():
            invalid_fields.append("activity_type")
        if not isinstance(duration_minutes, (int, float)) or duration_minutes < 0:
            invalid_fields.append("duration_minutes")
        if invalid_fields:
            raise ToolInputValidationError(
                self.name,
                f"Invalid input fields: {', '.join(invalid_fields)}",
                invalid_fields
            )
        
        try:
            mental_fitness_log = MentalFitnessLog(
                user_id=self.user_id,
                activity_type=activity_type,
                duration_minutes=duration_minutes,
                mood_before=mood_before,
                mood_after=mood_after,
                notes=notes
            )
            
            self.db.add(mental_fitness_log)
            self.db.commit()
            self.db.refresh(mental_fitness_log)
            
            return f"Mental fitness log created successfully. Log ID: {mental_fitness_log.id}, Activity: {activity_type}, Duration: {duration_minutes} minutes"
        except (OperationalError, DBAPIError) as e:
            # P0.4: Database errors might be retryable (deadlocks, timeouts)
            self.db.rollback()
            if is_retryable_tool_error(e):
                raise ToolRetryableError(
                    self.name,
                    f"Database error (retryable): {str(e)}",
                    original_error=e
                )
            raise ToolExecutionError(
                self.name,
                f"Database error: {str(e)}",
                original_error=e
            )
        except Exception as e:
            # P0.4: Raise exception instead of returning error string
            self.db.rollback()
            raise ToolExecutionError(
                self.name,
                f"Failed to create mental fitness log: {str(e)}",
                original_error=e
            )


class CreateWorkoutLogInput(BaseModel):
    """Input for create_workout_log tool"""
    exercise_type: str = Field(description="Type of exercise (e.g., calisthenics, weight_lifting, cardio)")
    exercises: str = Field(description="Exercise details as JSON string or plain text")
    duration_minutes: float = Field(description="Duration of workout in minutes")
    notes: str = Field(default="", description="Optional notes about the workout")


class CreateWorkoutLogTool(BaseTool):
    """Tool to create a workout log entry"""
    name: str = "create_workout_log"
    description: str = "Create a workout log entry for the user. Use this when the user completes a workout or when recommending a workout plan."
    args_schema: type = CreateWorkoutLogInput
    
    user_id: int
    db: Session
    
    def _run(self, exercise_type: str, exercises: str, duration_minutes: float, notes: str = "") -> str:
        """Create workout log entry"""
        # P0.4: Input validation
        invalid_fields = []
        if not exercise_type or not isinstance(exercise_type, str) or not exercise_type.strip():
            invalid_fields.append("exercise_type")
        if not isinstance(duration_minutes, (int, float)) or duration_minutes < 0:
            invalid_fields.append("duration_minutes")
        if invalid_fields:
            raise ToolInputValidationError(
                self.name,
                f"Invalid input fields: {', '.join(invalid_fields)}",
                invalid_fields
            )
        
        try:
            # Parse exercises if it's a JSON string
            try:
                exercises_json = json.loads(exercises) if exercises else {}
            except json.JSONDecodeError:
                exercises_json = exercises  # Use as-is if not valid JSON
            
            workout_log = WorkoutLog(
                user_id=self.user_id,
                exercise_type=exercise_type,
                exercises=json.dumps(exercises_json) if isinstance(exercises_json, dict) else exercises,
                duration_minutes=duration_minutes,
                notes=notes
            )
            
            self.db.add(workout_log)
            self.db.commit()
            self.db.refresh(workout_log)
            
            return f"Workout log created successfully. Log ID: {workout_log.id}"
        except (OperationalError, DBAPIError) as e:
            # P0.4: Database errors might be retryable (deadlocks, timeouts)
            self.db.rollback()
            if is_retryable_tool_error(e):
                raise ToolRetryableError(
                    self.name,
                    f"Database error (retryable): {str(e)}",
                    original_error=e
                )
            raise ToolExecutionError(
                self.name,
                f"Database error: {str(e)}",
                original_error=e
            )
        except Exception as e:
            # P0.4: Raise exception instead of returning error string
            self.db.rollback()
            raise ToolExecutionError(
                self.name,
                f"Failed to create workout log: {str(e)}",
                original_error=e
            )
