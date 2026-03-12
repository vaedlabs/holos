"""
Base Agent - LangChain base agent with essential tools.

This module provides the BaseAgent class, which serves as the foundation for all
specialized AI agents in the system. It implements the modern LangChain approach
using tools bound directly to the LLM, avoiding deprecated AgentExecutor patterns.

Key Features:
- Modern LangChain tool binding (tools bound to LLM directly)
- Shared context management (from ContextManager)
- Prompt caching (static and enhanced prompts)
- Tool caching (reduces redundant database queries)
- Retry logic with exponential backoff and model fallback
- Tool retry logic for transient errors
- LLM timeout handling
- Comprehensive error handling
- Observability integration (AgentTracer)

Agent Architecture:
    BaseAgent (this class)
    ├── PhysicalFitnessAgent
    ├── NutritionAgent
    ├── MentalFitnessAgent
    └── CoordinatorAgent

Common Tools (available to all agents):
    - get_medical_history: Retrieve user's medical history
    - get_user_preferences: Retrieve user's fitness preferences
    - create_workout_log: Log completed workouts
    - create_nutrition_log: Log meals and nutrition
    - create_mental_fitness_log: Log mental wellness activities
    - get_conversation_history: Retrieve past conversation messages
    - web_search: Search the web for current information

Context Management:
    - Shared context from ContextManager (medical history + preferences)
    - Context cached per agent instance
    - Enhanced prompts include full context to reduce tool calls
    - Context summary for minimal token usage

Prompt Strategy:
    - Static prompts: Base prompts cached indefinitely (version-based invalidation)
    - Enhanced prompts: Base + user context cached for 5 minutes
    - Includes full context upfront to reduce tool calls
    - Offsets larger prompt cost by reducing tool call tokens
"""

from typing import Optional, Dict, Any
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, DBAPIError
from app.services.medical_service import get_medical_history, check_user_exercise_conflicts
from app.services.tool_cache import tool_cache
from app.services.prompt_cache import prompt_cache
from app.services.llm_retry import retry_llm_call, get_fallback_model
from app.models.user_preferences import UserPreferences
from app.models.workout_log import WorkoutLog
from app.models.nutrition_log import NutritionLog
from app.models.mental_fitness_log import MentalFitnessLog
from app.models.conversation_message import ConversationMessage
from app.exceptions.agent_exceptions import (
    ToolExecutionError,
    ToolInputValidationError,
    ToolRetryableError,
    is_retryable_tool_error
)
import json
import os
import logging
import asyncio
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Logger instance for this module
# Used for logging agent operations, tool calls, and errors
logger = logging.getLogger(__name__)

# Modern LangChain approach - use tools bound to LLM directly (no deprecated AgentExecutor)
# This avoids deprecated patterns and uses the current LangChain best practices
load_dotenv()


class GetMedicalHistoryInput(BaseModel):
    """
    Input schema for get_medical_history tool.
    
    Attributes:
        query: Optional query string (currently unused, reserved for future filtering)
    """
    query: str = Field(default="", description="Optional query string")


class GetMedicalHistoryTool(BaseTool):
    """
    Tool to get user's medical history.
    
    This tool retrieves the user's medical history including conditions, limitations,
    medications, and notes. Used by agents to check for medical restrictions before
    recommending exercises or activities.
    
    Features:
        - Caching: Results are cached to reduce database queries
        - User-specific: Each user has their own cached medical history
        - Safety: Used by Physical Fitness Agent to check exercise safety
        
    Cache Strategy:
        - Cache key includes user_id and query (for future filtering)
        - TTL: 5 minutes (matches user context cache)
        - Reduces redundant database queries across multiple tool calls
    """
    name: str = "get_medical_history"
    description: str = "Get the user's medical history including conditions, limitations, medications, and notes. Use this to check for any medical restrictions before recommending exercises."
    args_schema: type = GetMedicalHistoryInput
    
    # Instance attributes (set during tool initialization)
    user_id: int  # User ID for fetching medical history
    db: Session  # Database session for querying
    
    def _run(self, query: str = "") -> str:
        """
        Get medical history for the user (with caching).
        
        This method retrieves medical history from cache or database, formats it
        for agent consumption, and caches the result for future calls.
        
        Args:
            query: Optional query string (currently unused, reserved for future filtering)
            
        Returns:
            str: Formatted medical history string, or "No medical history on file" if none exists
            
        Cache Flow:
            1. Check cache first (reduces database queries)
            2. If cache miss, fetch from database
            3. Format medical history into readable string
            4. Cache result for future calls
            5. Return formatted result
            
        Format:
            "Conditions: ...\nLimitations: ...\nMedications: ...\nNotes: ..."
            Or "No medical history on file for this user."
            
        Note:
            - Results are cached per user
            - Cache TTL: 5 minutes
            - Used by agents to check exercise safety
        """
        # Check cache first (reduces database queries)
        # Cache key includes user_id and query for precise matching
        cached_result = tool_cache.get("get_medical_history", user_id=self.user_id, query=query)
        if cached_result is not None:
            return cached_result
        
        # Fetch from database (cache miss)
        medical_history = get_medical_history(self.user_id, self.db)
        
        if not medical_history:
            result = "No medical history on file for this user."
        else:
            # Format medical history into readable string
            # Include all available fields
            result_parts = []
            if medical_history.conditions:
                result_parts.append(f"Conditions: {medical_history.conditions}")
            if medical_history.limitations:
                result_parts.append(f"Limitations: {medical_history.limitations}")
            if medical_history.medications:
                result_parts.append(f"Medications: {medical_history.medications}")
            if medical_history.notes:
                result_parts.append(f"Notes: {medical_history.notes}")
            
            # Join parts or provide default message
            result = "\n".join(result_parts) if result_parts else "Medical history exists but no details provided."
        
        # Cache the result for future calls
        # Cache TTL: 5 minutes (matches user context cache)
        tool_cache.set("get_medical_history", result, user_id=self.user_id, query=query)
        return result


class GetUserPreferencesInput(BaseModel):
    """
    Input schema for get_user_preferences tool.
    
    Attributes:
        query: Optional query string (currently unused, reserved for future filtering)
    """
    query: str = Field(default="", description="Optional query string")


class GetUserPreferencesTool(BaseTool):
    """
    Tool to get user's preferences.
    
    This tool retrieves the user's fitness preferences including goals, exercise
    types, activity level, location, and dietary restrictions. Used by agents to
    tailor recommendations to user preferences.
    
    Features:
        - Caching: Results are cached to reduce database queries
        - User-specific: Each user has their own cached preferences
        - Personalization: Used by all agents to personalize recommendations
        
    Cache Strategy:
        - Cache key includes user_id and query (for future filtering)
        - TTL: 5 minutes (matches user context cache)
        - Reduces redundant database queries across multiple tool calls
    """
    name: str = "get_user_preferences"
    description: str = "Get the user's fitness preferences including goals, exercise types, activity level, and location. Use this to tailor recommendations to the user's preferences."
    args_schema: type = GetUserPreferencesInput
    
    # Instance attributes (set during tool initialization)
    user_id: int  # User ID for fetching preferences
    db: Session  # Database session for querying
    
    def _run(self, query: str = "") -> str:
        """
        Get user preferences (with caching).
        
        This method retrieves user preferences from cache or database, formats them
        for agent consumption, and caches the result for future calls.
        
        Args:
            query: Optional query string (currently unused, reserved for future filtering)
            
        Returns:
            str: Formatted preferences string, or "No preferences set" if none exist
            
        Cache Flow:
            1. Check cache first (reduces database queries)
            2. If cache miss, fetch from database
            3. Format preferences into readable string
            4. Cache result for future calls
            5. Return formatted result
            
        Format:
            "Goals: ...\nExercise Types: ...\nActivity Level: ...\nLocation: ...\nDietary Restrictions: ..."
            Or "No preferences set for this user."
            
        Note:
            - Results are cached per user
            - Cache TTL: 5 minutes
            - Used by all agents for personalization
        """
        # Check cache first (reduces database queries)
        # Cache key includes user_id and query for precise matching
        cached_result = tool_cache.get("get_user_preferences", user_id=self.user_id, query=query)
        if cached_result is not None:
            return cached_result
        
        # Fetch from database (cache miss)
        preferences = self.db.query(UserPreferences).filter(
            UserPreferences.user_id == self.user_id
        ).first()
        
        if not preferences:
            result = "No preferences set for this user."
        else:
            # Format preferences into readable string
            # Include all available fields
            result_parts = []
            if preferences.goals:
                result_parts.append(f"Goals: {preferences.goals}")
            if preferences.exercise_types:
                result_parts.append(f"Exercise Types: {preferences.exercise_types}")
            if preferences.activity_level:
                result_parts.append(f"Activity Level: {preferences.activity_level}")
            if preferences.location:
                result_parts.append(f"Location: {preferences.location}")
            if preferences.dietary_restrictions:
                result_parts.append(f"Dietary Restrictions: {preferences.dietary_restrictions}")
            
            # Join parts or provide default message
            result = "\n".join(result_parts) if result_parts else "Preferences exist but no details provided."
        
        # Cache the result for future calls
        # Cache TTL: 5 minutes (matches user context cache)
        tool_cache.set("get_user_preferences", result, user_id=self.user_id, query=query)
        return result


class WebSearchInput(BaseModel):
    """
    Input schema for web_search tool.
    
    Attributes:
        query: Search query string (required)
    """
    query: str = Field(description="Search query string")


class WebSearchTool(BaseTool):
    """
    Tool to search the web for current information.
    
    This tool uses the Tavily API to search the web for current information,
    research, or up-to-date data. Used by agents when they need recent information
    that might not be in their training data.
    
    Features:
        - Caching: Successful results are cached (1 hour TTL)
        - Global caching: Not user-specific (same query = same result for all users)
        - Error handling: Graceful degradation if API key not set
        - Result formatting: Formats results for easy agent consumption
        
    Use Cases:
        - Latest fitness trends and research
        - Current nutrition facts and guidelines
        - Recent exercise techniques and best practices
        - Up-to-date health information
        
    Cache Strategy:
        - Cache key includes only query (not user_id)
        - TTL: 1 hour (web search results don't change frequently)
        - Only successful results are cached (errors are not cached)
        
    Note:
        - Requires TAVILY_API_KEY environment variable (optional)
        - Application continues to work without web search
        - Returns error message if API key not set or search fails
    """
    name: str = "web_search"
    description: str = "Search the web for current information, research, or up-to-date data. Returns links (URLs) and query-relevant content extracts from websites. Use this when you need recent information that might not be in your training data, such as latest fitness trends, nutrition facts, exercise techniques, or health research. You will receive relevant content extracts (not full pages) along with URLs for reference."
    args_schema: type = WebSearchInput
    
    def _run(self, query: str) -> str:
        """
        Search the web using Tavily API (with caching).
        
        This method performs a web search using the Tavily API, formats results
        for agent consumption, and caches successful results.
        
        Args:
            query: Search query string
            
        Returns:
            str: Formatted search results or error message
            
        Search Configuration:
            - search_depth: "advanced" (extracts query-relevant sections, not generic summaries)
            - max_results: 4 results (manages total token count)
            - chunks_per_source: 2 (balance between detail and token usage)
            - Content limit: ~2000 chars per result (~8000-10000 tokens total)
            - Smart truncation: Cuts at sentence boundaries when needed
            
        Result Format:
            "Title: ...\nURL: ...\nContent: [query-relevant extracts]...\n\n---\n\n..."
            Includes URL and query-relevant content extracts (not full pages to avoid token limits)
            Or error message if search fails
            
        Cache Strategy:
            - Only successful results are cached (errors are not cached)
            - Cache TTL: 1 hour (web search results don't change frequently)
            - Global cache (not user-specific)
            
        Error Handling:
            - Missing API key: Returns informative error message
            - Import error: Returns installation instructions
            - API errors: Returns error message (not cached)
            
        Note:
            - Requires TAVILY_API_KEY environment variable (optional)
            - Application continues to work without web search
        """
        # Check cache first (web_search doesn't have user_id - global cache)
        # Same query returns same result for all users
        cached_result = tool_cache.get("web_search", query=query)
        if cached_result is not None:
            return cached_result
        
        # Perform search using Tavily API
        try:
            from tavily import TavilyClient
            
            # Get API key from environment
            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                # API key not set - return informative error message
                # Application continues to work without web search
                result = (
                    "Error: TAVILY_API_KEY is not set. Web search is unavailable. "
                    "Please set TAVILY_API_KEY in your environment variables to enable web search functionality. "
                    "This is an optional feature - the application will continue to work without it."
                )
            else:
                # Initialize Tavily client and perform search
                client = TavilyClient(api_key=api_key)
                
                # Perform advanced search for query-relevant content extraction
                # Advanced depth: Extracts query-specific sections (better than basic summaries)
                # chunks_per_source: 2 chunks per source (balance between detail and token usage)
                # Max 4 results: Keeps total token count manageable (~8000-10000 tokens max)
                # Note: Not using include_raw_content to avoid massive token usage
                response = client.search(
                    query=query,
                    search_depth="advanced",  # Advanced for query-specific content extraction
                    max_results=4,  # Limit to 4 results to manage total token count
                    chunks_per_source=2  # 2 relevant chunks per source (balance detail vs tokens)
                )
                
                if not response.get("results"):
                    result = f"No results found for query: {query}"
                else:
                    # Format results with intelligent content limits
                    # Target: ~2000-2500 chars per result = ~8000-10000 tokens total
                    formatted_results = []
                    MAX_CONTENT_PER_RESULT = 2000  # Characters per result (not tokens, but close proxy)
                    
                    for result_item in response["results"][:4]:  # Limit to 4 results
                        title = result_item.get("title", "No title")
                        url = result_item.get("url", "")
                        content = result_item.get("content", "")  # Query-relevant extracted content
                        
                        # Build result with URL prominently displayed
                        result_parts = [
                            f"Title: {title}",
                            f"URL: {url}",
                        ]
                        
                        # Include content (query-relevant extracts from advanced search)
                        # Truncate if too long to manage token usage
                        if content:
                            if len(content) > MAX_CONTENT_PER_RESULT:
                                # Truncate but keep it meaningful - try to cut at sentence boundary
                                truncated = content[:MAX_CONTENT_PER_RESULT]
                                # Try to find last sentence boundary
                                last_period = truncated.rfind('. ')
                                last_newline = truncated.rfind('\n')
                                cut_point = max(last_period, last_newline)
                                if cut_point > MAX_CONTENT_PER_RESULT * 0.8:  # Only if we keep most content
                                    content = truncated[:cut_point + 1] + f"\n\n[Content truncated - see full article at: {url}]"
                                else:
                                    content = truncated + f"...\n\n[Content truncated - see full article at: {url}]"
                            
                            result_parts.append(f"Content:\n{content}")
                        else:
                            result_parts.append("Content: No content available")
                        
                        formatted_results.append("\n".join(result_parts))
                    
                    # Join results with separator
                    result = "\n\n---\n\n".join(formatted_results)
            
        except ImportError:
            # Tavily package not installed - return installation instructions
            result = "Error: tavily-python package is not installed. Please install it with: pip install tavily-python"
        except Exception as e:
            # Other errors (API errors, network issues, etc.)
            result = f"Error performing web search: {str(e)}"
        
        # Cache the result (only cache successful results, not errors)
        # Errors are not cached so they can be retried
        if not result.startswith("Error"):
            tool_cache.set("web_search", result, query=query)
        
        return result


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


class GetConversationHistoryInput(BaseModel):
    """Input for GetConversationHistoryTool"""
    agent_type: Optional[str] = Field(default=None, description="Optional agent type to filter conversation history (e.g., 'physical-fitness', 'nutrition', 'mental-fitness', 'coordinator'). If not provided, returns all conversation history.")


class GetConversationHistoryTool(BaseTool):
    """Tool to retrieve the user's conversation history with the AI agents."""
    name: str = "get_conversation_history"
    description: str = "Retrieve the user's past conversation messages. Can filter by a specific agent type to get relevant context. Returns a list of messages with role, content, and agent_type."
    args_schema: type = GetConversationHistoryInput

    user_id: int
    db: Session

    def _run(self, agent_type: Optional[str] = None) -> str:
        """Retrieve conversation history for the user, optionally filtered by agent type (with caching)."""
        # Check cache first
        cached_result = tool_cache.get("get_conversation_history", user_id=self.user_id, agent_type=agent_type)
        if cached_result is not None:
            return cached_result
        
        # Fetch from database
        query = self.db.query(ConversationMessage).filter(
            ConversationMessage.user_id == self.user_id
        )
        if agent_type:
            query = query.filter(ConversationMessage.agent_type == agent_type)
        
        messages = query.order_by(ConversationMessage.created_at.asc()).all()
        
        if not messages:
            result = "No conversation history found."
        else:
            formatted_messages = []
            for msg in messages:
                formatted_messages.append(
                    f"Agent: {msg.agent_type} - Role: {msg.role}, Content: {msg.content}"
                )
            result = "\n".join(formatted_messages)
        
        # Cache the result
        tool_cache.set("get_conversation_history", result, user_id=self.user_id, agent_type=agent_type)
        return result


class BaseAgent:
    """
    Base agent class with common functionality.
    
    This class serves as the foundation for all specialized AI agents in the system.
    It implements the modern LangChain approach using tools bound directly to the LLM,
    avoiding deprecated AgentExecutor patterns.
    
    Key Features:
        - Modern LangChain tool binding (tools bound to LLM directly)
        - Shared context management (from ContextManager)
        - Prompt caching (static and enhanced prompts)
        - Tool caching (reduces redundant database queries)
        - Retry logic with exponential backoff and model fallback
        - Tool retry logic for transient errors
        - LLM timeout handling
        - Comprehensive error handling
        - Observability integration (AgentTracer)
        
    Agent Lifecycle:
        1. Initialization: Set up LLM, tools, and prompts
        2. Context Enhancement: Build enhanced prompt with user context
        3. Execution: Run agent with user input (tool calling loop)
        4. Tool Execution: Execute tools with retry logic
        5. Response: Return final response to user
        
    Tool Execution Flow:
        1. LLM decides to call tool(s)
        2. Tools are executed with retry logic
        3. Tool results are added to message history
        4. LLM processes tool results and generates response
        5. Repeat until no more tool calls or max iterations reached
        
    Attributes:
        user_id: User ID for user-specific operations
        db: Database session for querying user data
        model_name: LLM model name (e.g., "gpt-4.1")
        _shared_context: Shared user context from ContextManager (optional)
        tracer: AgentTracer instance for observability (optional)
        llm_timeout: Timeout for LLM calls in seconds (default: 60s)
        llm: ChatOpenAI instance (primary LLM)
        tools: List of tools available to the agent
        llm_with_tools: LLM with tools bound (for tool calling)
        agent_type: Agent type identifier (for caching)
        system_message: Base system prompt (cached)
        _user_context_summary: Cached user context summary (minimal token usage)
        _context_fetched: Flag indicating if context has been fetched
    """
    
    def __init__(
        self, 
        user_id: int, 
        db: Session, 
        model_name: str = "gpt-4.1",
        shared_context: Optional[Dict[str, Optional[Dict]]] = None,
        tracer: Optional[Any] = None,  # AgentTracer instance (optional)
        llm_timeout: float = 60.0  # P1.1: Timeout for LLM calls in seconds (default: 60s)
    ):
        """
        Initialize BaseAgent with user context and configuration.
        
        Args:
            user_id: User ID for user-specific operations
            db: Database session for querying user data
            model_name: LLM model name (default: "gpt-4.1")
            shared_context: Shared user context from ContextManager (optional)
                          If provided, avoids redundant database queries
            tracer: AgentTracer instance for observability (optional)
                   Used for logging agent execution, tool calls, and token usage
            llm_timeout: Timeout for LLM calls in seconds (default: 60s)
                        Prevents hanging on slow API responses
                        
        Initialization Steps:
            1. Store user_id, db, and configuration
            2. Store shared context and tracer
            3. Initialize LLM with API key
            4. Initialize tools (medical history, preferences, logs, web search, conversation)
            5. Bind tools to LLM (modern LangChain approach)
            6. Get agent type for caching
            7. Build and cache system prompt
            8. Initialize context caching
            
        Note:
            - Raises ValueError if OPENAI_API_KEY is not set
            - Tools are initialized with user_id and db
            - System prompt is cached for future use
            - Shared context reduces redundant database queries
        """
        # Store user and database references
        self.user_id = user_id  # User ID for user-specific operations
        self.db = db  # Database session for querying user data
        
        # Store shared context if provided (from ContextManager)
        # Shared context includes medical history and preferences
        # Reduces redundant database queries across multiple agents
        self._shared_context = shared_context
        
        # Store tracer for observability (optional)
        # Used for logging agent execution, tool calls, and token usage
        self.tracer = tracer
        
        # Store model name for retry fallback logic
        # Used by retry logic to fallback to cheaper models on errors
        self.model_name = model_name
        
        # P1.1: Store LLM timeout configuration
        # Prevents hanging on slow API responses
        self.llm_timeout = llm_timeout
        
        # Get API key from environment
        # Required for OpenAI API access
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set in environment variables. "
                "Please set it in your .env file or environment."
            )
        
        # Initialize LLM with API key
        # ChatOpenAI automatically reads from OPENAI_API_KEY env var, but we can also pass it explicitly
        # Temperature: 0.7 (balanced creativity and consistency)
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0.7,  # Balanced creativity and consistency
            openai_api_key=api_key  # LangChain uses 'openai_api_key' parameter
        )
        
        # Initialize tools available to all agents
        # Tools are initialized with user_id and db for user-specific operations
        self.tools = [
            GetMedicalHistoryTool(user_id=user_id, db=db),  # Get user's medical history
            GetUserPreferencesTool(user_id=user_id, db=db),  # Get user's preferences
            CreateWorkoutLogTool(user_id=user_id, db=db),  # Create workout log entries
            WebSearchTool(),  # Web search tool (no user_id or db needed - global)
            GetConversationHistoryTool(user_id=user_id, db=db),  # Get conversation history
        ]
        
        # Bind tools to LLM for modern LangChain approach
        # This enables the LLM to call tools during conversation
        # Modern approach: tools bound directly to LLM (no deprecated AgentExecutor)
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Get agent type for caching (default to class name, can be overridden)
        # Used for prompt caching and identification
        self.agent_type = self._get_agent_type()
        
        # Create system message (with caching)
        # Checks cache first, builds if not cached
        self.system_message = self._get_system_prompt()
        
        # Allow child agents to inject additional personality traits
        # Child agents can override _get_personality_traits() to add specific traits
        # Personality traits are appended to base prompt
        personality_traits = self._get_personality_traits()
        if personality_traits:
            self.system_message += f"\n\n## Additional Personality Traits\n{personality_traits}"
        
        # Cache the static base prompt (after adding personality traits)
        # Static prompts are cached indefinitely (version-based invalidation)
        prompt_cache.set_static_prompt(self.agent_type, self.system_message)
        
        # Cache user context summary (fetched once per agent instance)
        # If shared_context is provided, we'll use it instead of fetching
        # Context summary is minimal (max 150 chars) to reduce token usage
        self._user_context_summary = None  # Cached user context summary
        self._context_fetched = False  # Flag indicating if context has been fetched
    
    def _get_agent_type(self) -> str:
        """
        Get agent type identifier for caching.
        Override in child classes if needed.
        
        Returns:
            Agent type string (e.g., 'physical_fitness', 'nutrition', 'mental_fitness', 'coordinator')
        """
        # Default: use class name, convert to snake_case
        class_name = self.__class__.__name__
        # Convert CamelCase to snake_case
        import re
        snake_case = re.sub(r'(?<!^)(?=[A-Z])', '_', class_name).lower()
        # Remove 'agent' suffix if present
        if snake_case.endswith('_agent'):
            snake_case = snake_case[:-6]
        return snake_case
    
    def _get_system_prompt(self) -> str:
        """
        Get system prompt for the agent with humanization guidelines.
        Checks cache first, then builds if not cached.
        """
        # Check cache first
        agent_type = self._get_agent_type()
        cached_prompt = prompt_cache.get_static_prompt(agent_type)
        if cached_prompt:
            return cached_prompt
        
        # Not cached, build it
        # Use base humanization from prompt components
        from app.agents.prompts.base_humanization import BASE_HUMANIZATION
        return BASE_HUMANIZATION
    
    def _get_personality_traits(self) -> str:
        """
        Override this method in child agents to add specific personality traits.
        Returns additional personality guidelines that will be appended to the base prompt.
        
        Example:
            return \"\"\"
            - Be especially motivational and energetic
            - Use active voice: \"Let's crush this workout!\" not \"Workouts should be performed\"
            - Celebrate small wins enthusiastically
            \"\"\"
        """
        return ""
    
    def check_exercise_safety(self, exercise: str) -> Dict[str, Any]:
        """Check if an exercise is safe for the user based on medical history"""
        return check_user_exercise_conflicts(self.user_id, exercise, self.db)
    
    def _get_user_context_summary(self) -> str:
        """
        Get a minimal summary of user context (cached per agent instance).
        Returns a very brief summary to minimize token usage.
        Only includes essential info - agent should use tools for details.
        
        Uses shared_context if provided (from ContextManager), otherwise fetches independently.
        """
        if self._context_fetched and self._user_context_summary:
            return self._user_context_summary
        
        # Use shared context if provided (from ContextManager)
        if self._shared_context:
            summary_parts = []
            
            # Get medical history from shared context
            medical_history = self._shared_context.get("medical_history")
            if medical_history and medical_history.get("conditions"):
                conditions = medical_history["conditions"].strip()
                if conditions:
                    if len(conditions) > 60:
                        conditions = conditions[:57] + "..."
                    summary_parts.append(f"M:{conditions}")
            
            # Get user preferences from shared context
            preferences = self._shared_context.get("preferences")
            if preferences:
                pref_items = []
                if preferences.get("goals") and preferences["goals"].strip():
                    goals = preferences["goals"].strip()
                    if len(goals) > 50:
                        goals = goals[:47] + "..."
                    pref_items.append(goals)
                if preferences.get("exercise_types") and preferences["exercise_types"].strip():
                    pref_items.append(preferences["exercise_types"].strip()[:20])
                
                if pref_items:
                    summary_parts.append("|".join(pref_items[:2]))  # Max 2 items
            
            # Cache the summary (max 150 chars total)
            if summary_parts:
                self._user_context_summary = " ".join(summary_parts)[:150]
            else:
                self._user_context_summary = None
            
            self._context_fetched = True
            return self._user_context_summary
        
        # Fallback: Fetch context independently (for backward compatibility)
        summary_parts = []
        
        # Get medical history - only include if there are actual conditions (max 60 chars)
        medical_history = get_medical_history(self.user_id, self.db)
        if medical_history and medical_history.conditions and medical_history.conditions.strip():
            conditions = medical_history.conditions.strip()
            if len(conditions) > 60:
                conditions = conditions[:57] + "..."
            summary_parts.append(f"M:{conditions}")
        
        # Get user preferences - only key info (max 90 chars)
        preferences = self.db.query(UserPreferences).filter(
            UserPreferences.user_id == self.user_id
        ).first()
        if preferences:
            pref_items = []
            if preferences.goals and preferences.goals.strip():
                goals = preferences.goals.strip()
                if len(goals) > 50:
                    goals = goals[:47] + "..."
                pref_items.append(goals)
            if preferences.exercise_types and preferences.exercise_types.strip():
                pref_items.append(preferences.exercise_types.strip()[:20])
            
            if pref_items:
                summary_parts.append("|".join(pref_items[:2]))  # Max 2 items
        
        # Cache the summary (max 150 chars total)
        if summary_parts:
            self._user_context_summary = " ".join(summary_parts)[:150]
        else:
            self._user_context_summary = None  # No context available
        
        self._context_fetched = True
        return self._user_context_summary
    
    def _build_enhanced_system_prompt(self) -> str:
        """
        Build system prompt with enhanced context to reduce tool calls.
        Child agents can override this for custom behavior.
        
        Strategy: Include full context in system prompt upfront to reduce tool calls.
        This offsets the cost of larger prompts by reducing tool call tokens.
        
        Returns:
            Enhanced system prompt with full context included
        """
        base_prompt = self.system_message
        
        # Use shared context if available (from ContextManager - already cached)
        if self._shared_context:
            context_parts = []
            
            # Include full medical history if available
            medical_history = self._shared_context.get("medical_history")
            if medical_history:
                medical_parts = []
                if medical_history.get("conditions"):
                    medical_parts.append(f"Medical Conditions: {medical_history['conditions']}")
                if medical_history.get("limitations"):
                    medical_parts.append(f"Physical Limitations: {medical_history['limitations']}")
                if medical_history.get("medications"):
                    medical_parts.append(f"Medications: {medical_history['medications']}")
                if medical_history.get("notes"):
                    medical_parts.append(f"Medical Notes: {medical_history['notes']}")
                
                if medical_parts:
                    context_parts.append("## Medical History\n" + "\n".join(medical_parts))
            
            # Include full user preferences if available
            preferences = self._shared_context.get("preferences")
            if preferences:
                pref_parts = []
                if preferences.get("goals"):
                    pref_parts.append(f"Fitness Goals: {preferences['goals']}")
                if preferences.get("exercise_types"):
                    pref_parts.append(f"Preferred Exercise Types: {preferences['exercise_types']}")
                if preferences.get("dietary_restrictions"):
                    pref_parts.append(f"Dietary Restrictions: {preferences['dietary_restrictions']}")
                if preferences.get("activity_level"):
                    pref_parts.append(f"Activity Level: {preferences['activity_level']}")
                if preferences.get("lifestyle"):
                    pref_parts.append(f"Lifestyle: {preferences['lifestyle']}")
                if preferences.get("age"):
                    pref_parts.append(f"Age: {preferences['age']}")
                if preferences.get("gender"):
                    pref_parts.append(f"Gender: {preferences['gender']}")
                if preferences.get("location"):
                    pref_parts.append(f"Location: {preferences['location']}")
                
                if pref_parts:
                    context_parts.append("## User Preferences\n" + "\n".join(pref_parts))
            
            # Add context section if we have any context
            if context_parts:
                context_section = "\n\n".join(context_parts)
                base_prompt += f"\n\n## User Context (Available Information)\n{context_section}"
                base_prompt += "\n\n**IMPORTANT**: You have full user context above. Only call tools (get_medical_history, get_user_preferences) if you need information NOT provided above or if the context seems outdated. For real-time information (web search) or actions (creating logs), use tools as needed."
            else:
                base_prompt += "\n\n**Note**: No user context available. Use get_medical_history and get_user_preferences tools to fetch user information when needed."
        else:
            # Fallback: Use brief summary if shared context not available
            context_summary = self._get_user_context_summary()
            if context_summary:
                base_prompt += f"\n\nUser context (brief): {context_summary}. Use tools for details."
            else:
                base_prompt += "\n\nUse get_medical_history and get_user_preferences tools to fetch user information."
        
        # Cache the enhanced prompt before returning
        prompt_cache.set_enhanced_prompt(self._get_agent_type(), self.user_id, base_prompt)
        
        return base_prompt
    
    def _append_web_search_links(self, response: str, web_search_urls: list) -> str:
        """
        Append formatted web search links at the end of the response.
        
        Formats URLs collected from web_search tool calls and appends them
        at the end of the agent's response in the specified format.
        
        Args:
            response: Agent's response text
            web_search_urls: List of (title, url) tuples from web_search calls
            
        Returns:
            Response with links section appended (if any URLs were found)
        """
        if not web_search_urls:
            return response
        
        # Format links section as specified: "1. <name of link URL>"
        links_section = "\n\n---\n\nLinks Referred\n\n"
        
        for idx, (title, url) in enumerate(web_search_urls, start=1):
            # Format: "1. Title URL" (name of link followed by URL)
            link_name = title if title else url
            links_section += f"{idx}. {link_name} {url}\n"
        
        links_section += "\n---"
        
        return response + links_section
    
    async def run(self, user_input: str) -> str:
        """
        Run the agent with user input using modern LangChain approach.
        
        This is the main entry point for agent execution. It implements a tool-calling
        loop where the LLM can call tools, receive results, and continue the conversation
        until a final response is generated.
        
        Execution Flow:
            1. Build enhanced system prompt with full user context
            2. Initialize message history with system and user messages
            3. Loop (max 5 iterations):
               a. Get LLM response (with retry logic and timeout)
               b. Check if LLM wants to call tools
               c. Execute tools with retry logic
               d. Add tool results to message history
               e. Continue loop or return final response
            4. Return final response
        
        Tool Calling Loop:
            - LLM decides to call tool(s) based on user input
            - Tools are executed with retry logic for transient errors
            - Tool results are added to message history
            - LLM processes tool results and generates response
            - Loop continues until no more tool calls or max iterations reached
        
        Args:
            user_input: User's input query/message
            
        Returns:
            str: Agent's final response to the user
            
        Error Handling:
            - API key errors: Returns informative error message
            - Timeout errors: Logs timeout and raises user-friendly error
            - Tool errors: Handled with retry logic and error messages
            - Model fallback: Automatically falls back to cheaper model on errors
            
        Note:
            - Uses modern LangChain approach (no deprecated AgentExecutor)
            - Includes full context upfront to reduce tool calls
            - Implements retry logic with exponential backoff
            - Supports model fallback for degraded service handling
            - Maximum 5 iterations to prevent infinite loops
        """
        try:
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
            
            # Check if API key is set
            # Required for OpenAI API access
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return "Error: OpenAI API key is not configured. Please set OPENAI_API_KEY in your environment variables."
            
            # Build enhanced system message with full context to reduce tool calls
            # Strategy: Include more context upfront to reduce tool calls, offsetting larger prompt cost
            # Enhanced prompt includes full medical history and preferences
            enhanced_system_message = self._build_enhanced_system_prompt()
            
            # Load recent conversation history for context
            # This allows agents to recall previous messages in the conversation
            conversation_messages = []
            try:
                # Get recent conversation history for this agent type (last 20 messages)
                # This provides context for follow-up questions and maintains conversation flow
                agent_type = self._get_agent_type()
                history_query = self.db.query(ConversationMessage).filter(
                    ConversationMessage.user_id == self.user_id,
                    ConversationMessage.agent_type == agent_type
                ).order_by(ConversationMessage.created_at.desc()).limit(20).all()
                
                # Reverse to get chronological order (oldest first)
                history_query.reverse()
                
                # Convert conversation history to LangChain messages
                for msg in history_query:
                    if msg.role == 'user':
                        conversation_messages.append(HumanMessage(content=msg.content))
                    elif msg.role == 'assistant':
                        conversation_messages.append(AIMessage(content=msg.content))
            except Exception as e:
                # If loading history fails, log but continue without it
                # Don't block agent execution if history loading fails
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to load conversation history: {e}")
            
            # Build messages with enhanced system prompt and conversation history
            # System message includes full user context
            # Conversation history provides context from previous messages
            # Human message contains user's current input
            messages = [
                SystemMessage(content=enhanced_system_message),  # Enhanced system prompt with context
            ]
            # Add conversation history before current message
            messages.extend(conversation_messages)
            # Add current user input
            messages.append(HumanMessage(content=user_input))  # User's current input query
            
            # Maximum iterations to prevent infinite loops
            # Prevents agent from getting stuck in tool-calling loops
            max_iterations = 5  # Prevent infinite loops
            iteration = 0
            
            # P0.3: Track original model name to detect fallback usage
            # Used to detect if model fallback occurred during execution
            original_model_name = self.model_name
            self._used_fallback_model = False  # Flag indicating if fallback was used
            self._fallback_info = None  # Fallback information (original model, fallback model, reason)
            
            # Track URLs from web_search tool calls for formatting at end
            # URLs will be extracted from web_search tool results and appended at end of response
            web_search_urls = []  # List of (title, url) tuples from web_search calls
            
            # Tool-calling loop: Continue until no more tool calls or max iterations reached
            while iteration < max_iterations:
                iteration += 1
                
                # Get LLM response with tools (with retry logic and timeout)
                # Wrapped in async function for retry logic
                async def invoke_llm():
                    """
                    Invoke LLM with timeout protection.
                    
                    This function wraps the LLM call with timeout protection to prevent
                    hanging on slow API responses.
                    """
                    # P1.1: Add timeout to LLM call
                    # Prevents hanging on slow API responses
                    try:
                        return await asyncio.wait_for(
                            self.llm_with_tools.ainvoke(messages),  # LLM call with tools bound
                            timeout=self.llm_timeout  # Timeout in seconds
                        )
                    except asyncio.TimeoutError:
                        # P1.1: Log timeout and raise user-friendly error
                        timeout_msg = f"LLM call timed out after {self.llm_timeout} seconds"
                        logger.warning(timeout_msg)
                        if self.tracer:
                            self.tracer.log_timeout(self.llm_timeout, "LLM call")
                        raise TimeoutError(f"Request timed out after {self.llm_timeout} seconds. Please try again with a simpler query.")
                
                def update_openai_model(new_model: str):
                    """
                    Update OpenAI model if fallback is needed.
                    
                    This function updates the LLM instance to use a fallback model
                    when the primary model fails. Used by retry logic for model fallback.
                    
                    Args:
                        new_model: Fallback model name (e.g., "gpt-3.5-turbo")
                    """
                    # Create new LLM instance with fallback model
                    self.llm = ChatOpenAI(
                        model=new_model,
                        temperature=0.7,  # Same temperature as original
                        openai_api_key=os.getenv("OPENAI_API_KEY")
                    )
                    # Re-bind tools to new LLM instance
                    self.llm_with_tools = self.llm.bind_tools(self.tools)
                    self.model_name = new_model
                    # P0.3: Track fallback usage
                    self._used_fallback_model = True
                    self._fallback_info = {
                        "original_model": original_model_name,
                        "fallback_model": new_model,
                        "reason": "Model fallback due to errors"
                    }
                    logger.info(f"Fell back to model: {new_model}")
                
                # Call LLM with retry logic and timeout protection
                # Retry logic handles transient errors with exponential backoff
                # Model fallback handles persistent errors by switching to cheaper model
                response = await retry_llm_call(
                    func=invoke_llm,  # LLM invocation function
                    max_retries=3,  # Maximum retry attempts
                    initial_delay=1.0,  # Initial delay before retry (seconds)
                    max_delay=60.0,  # Maximum delay cap (seconds)
                    tracer=self.tracer,  # Tracer for logging retries and token usage
                    model_name=self.model_name,  # Current model name (for fallback)
                    update_model_fn=update_openai_model if self.model_name else None,  # Model update function
                    service_name="openai",  # Service name for circuit breaker
                )
                messages.append(response)  # Add LLM response to message history
                
                # Check if LLM wants to call tools
                # Tool calls are indicated by response.tool_calls attribute
                if hasattr(response, 'tool_calls') and response.tool_calls and len(response.tool_calls) > 0:
                    # Execute tool calls
                    # LLM can call multiple tools in parallel
                    for tool_call in response.tool_calls:
                        tool_name = tool_call.get("name", "")  # Tool name (e.g., "get_medical_history")
                        tool_input = tool_call.get("args", {})  # Tool input arguments
                        tool_call_id = tool_call.get("id", "")  # Tool call ID for matching results
                        
                        # Find and execute the tool
                        # Search through available tools to find matching tool
                        tool_result = None
                        for tool in self.tools:
                            if tool.name == tool_name:
                                # P0.4: Retry logic for transient tool errors
                                # Tools can fail due to transient errors (database deadlocks, timeouts)
                                # Retry logic handles these errors with exponential backoff
                                max_tool_retries = 3  # Maximum retry attempts
                                tool_retry_delay = 0.1  # Initial retry delay (seconds)
                                
                                # Retry loop: Attempt tool execution with retry logic
                                for tool_attempt in range(max_tool_retries + 1):
                                    try:
                                        # Log tool call if tracer is available
                                        # Logs tool name, input, and output for observability
                                        if self.tracer:
                                            self.tracer.log_tool_call(
                                                tool_name=tool_name,
                                                tool_input=tool_input,
                                                tool_output=""  # Will update after execution
                                            )
                                        
                                        # Execute tool with input arguments
                                        # Tool execution may raise exceptions for errors
                                        tool_result = tool._run(**tool_input)
                                        
                                        # Extract URLs from web_search tool results
                                        # URLs will be formatted and appended at end of response
                                        if tool_name == "web_search" and tool_result:
                                            import re
                                            # Extract URLs from web_search result format: "Title: ...\nURL: <url>\n..."
                                            # Pattern matches "URL: <url>" lines
                                            url_pattern = r'URL:\s*(https?://[^\s\n]+)'
                                            title_url_pattern = r'Title:\s*([^\n]+)\nURL:\s*(https?://[^\s\n]+)'
                                            
                                            # Try to extract title-URL pairs first (more accurate)
                                            matches = re.findall(title_url_pattern, str(tool_result))
                                            for title, url in matches:
                                                if url not in [u for _, u in web_search_urls]:  # Avoid duplicates
                                                    web_search_urls.append((title.strip(), url))
                                            
                                            # Fallback: extract URLs without titles if pattern didn't match
                                            if not matches:
                                                urls = re.findall(url_pattern, str(tool_result))
                                                for url in urls:
                                                    if url not in [u for _, u in web_search_urls]:  # Avoid duplicates
                                                        web_search_urls.append(("", url))
                                        
                                        # Update tracer with actual output
                                        # Replaces empty output with actual tool result
                                        if self.tracer:
                                            # Re-log with actual output (last tool call)
                                            if self.tracer.current_trace and self.tracer.current_trace.get("tools_called"):
                                                self.tracer.current_trace["tools_called"][-1]["output"] = str(tool_result)[:500]
                                        
                                        break  # Success, exit retry loop
                                    
                                    except ToolRetryableError as e:
                                        # P0.4: Retryable errors - retry with exponential backoff
                                        # Retryable errors: Database deadlocks, timeouts, transient failures
                                        if tool_attempt < max_tool_retries:
                                            # Calculate wait time with exponential backoff
                                            wait_time = tool_retry_delay * (2 ** tool_attempt)
                                            logger.warning(
                                                f"Tool {tool_name} retryable error (attempt {tool_attempt + 1}/{max_tool_retries + 1}): {e}. "
                                                f"Retrying in {wait_time}s..."
                                            )
                                            if self.tracer:
                                                self.tracer.log_warning(
                                                    f"Tool {tool_name} retryable error, retrying (attempt {tool_attempt + 1}/{max_tool_retries + 1})"
                                                )
                                            await asyncio.sleep(wait_time)
                                            continue  # Retry tool execution
                                        else:
                                            # Max retries exhausted, convert to non-retryable error
                                            logger.error(f"Tool {tool_name} failed after {max_tool_retries + 1} retries: {e}")
                                            if self.tracer:
                                                self.tracer.log_warning(f"Tool {tool_name} failed after {max_tool_retries + 1} retries")
                                            tool_result = f"Error executing {tool_name}: {str(e)}"
                                            break  # Exit retry loop with error
                                    
                                    except (ToolInputValidationError, ToolExecutionError) as e:
                                        # P0.4: Non-retryable tool errors - log and return error message
                                        # Non-retryable errors: Invalid input, permanent failures
                                        logger.error(f"Tool {tool_name} error: {e}")
                                        if self.tracer:
                                            # Log with appropriate severity
                                            if isinstance(e, ToolInputValidationError):
                                                self.tracer.log_warning(f"Tool {tool_name} input validation error: {e}")
                                            else:
                                                self.tracer.log_warning(f"Tool {tool_name} execution error: {e}")
                                        tool_result = f"Error executing {tool_name}: {str(e)}"
                                        break  # Exit retry loop with error
                                    
                                    except Exception as e:
                                        # P0.4: Unexpected errors - wrap in ToolExecutionError
                                        # Unexpected errors: Should not occur, but handled gracefully
                                        logger.error(f"Tool {tool_name} unexpected error: {e}", exc_info=True)
                                        if self.tracer:
                                            self.tracer.log_warning(f"Tool {tool_name} unexpected error: {str(e)}")
                                        tool_result = f"Error executing {tool_name}: {str(e)}"
                                        break  # Exit retry loop with error
                                
                                break  # Tool found and executed (or failed)
                        
                        # Handle case where tool is not found
                        if tool_result is None:
                            tool_result = f"Tool {tool_name} not found"
                            if self.tracer:
                                self.tracer.log_warning(f"Tool {tool_name} not found")
                        
                        # Add tool result as ToolMessage
                        # ToolMessage links result to tool call via tool_call_id
                        messages.append(ToolMessage(
                            content=str(tool_result),  # Tool result as string
                            tool_call_id=tool_call_id  # Link to original tool call
                        ))
                else:
                    # No tool calls, return the final response
                    # LLM has generated final response without needing more tools
                    final_response = response.content if hasattr(response, 'content') else str(response)
                    # Append web search URLs at the end if any were collected
                    return self._append_web_search_links(final_response, web_search_urls)
            
            # If we've reached max iterations, return the last response
            # Prevents infinite loops by returning last response after max iterations
            last_response = messages[-1]
            final_response = last_response.content if hasattr(last_response, 'content') else str(last_response)
            # Append web search URLs at the end if any were collected
            return self._append_web_search_links(final_response, web_search_urls)
            
        except Exception as e:
            error_msg = str(e)
            # Handle specific OpenAI API errors
            if "insufficient_quota" in error_msg or "429" in error_msg:
                return (
                    "I'm sorry, but there's an issue with the OpenAI API quota. "
                    "Please check your OpenAI account:\n"
                    "1. Ensure billing is set up at https://platform.openai.com/account/billing\n"
                    "2. Add credits to your account\n"
                    "3. Verify your API key is correct\n\n"
                    "Note: Even GPT-4o-mini requires billing/credits. "
                    "It's very affordable (~$0.15 per 1M input tokens)."
                )
            elif "api_key" in error_msg.lower() or "authentication" in error_msg.lower() or "bearer" in error_msg.lower() or "missing" in error_msg.lower():
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    return (
                        "Error: OpenAI API key is missing. "
                        "Please set OPENAI_API_KEY in your .env file in the backend directory.\n\n"
                        "Steps:\n"
                        "1. Create a .env file in the backend/ directory if it doesn't exist\n"
                        "2. Add: OPENAI_API_KEY=sk-your-actual-api-key\n"
                        "3. Get your API key from: https://platform.openai.com/api-keys\n"
                        "4. Restart the backend server"
                    )
                else:
                    return (
                        "Error: OpenAI API authentication failed. "
                        f"The API key appears to be set (length: {len(api_key)}), but authentication is failing.\n\n"
                        "Please verify:\n"
                        "1. Your API key is correct (starts with 'sk-')\n"
                        "2. Your API key is active at https://platform.openai.com/api-keys\n"
                        "3. You have billing set up at https://platform.openai.com/account/billing\n"
                        "4. The .env file is in the backend/ directory and is being loaded correctly"
                    )
            else:
                import traceback
                traceback.print_exc()
                return f"Error: {error_msg}"

