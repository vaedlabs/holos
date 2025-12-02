"""
Base Agent - LangChain base agent with essential tools
"""

from typing import Optional, Dict, Any
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy.orm import Session
from app.services.medical_service import get_medical_history, check_user_exercise_conflicts
from app.models.user_preferences import UserPreferences
from app.models.workout_log import WorkoutLog
from app.models.nutrition_log import NutritionLog
from app.models.mental_fitness_log import MentalFitnessLog
from app.models.conversation_message import ConversationMessage
import json
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Modern LangChain approach - use tools bound to LLM directly (no deprecated AgentExecutor)
load_dotenv()


class GetMedicalHistoryInput(BaseModel):
    """Input for get_medical_history tool"""
    query: str = Field(default="", description="Optional query string")


class GetMedicalHistoryTool(BaseTool):
    """Tool to get user's medical history"""
    name: str = "get_medical_history"
    description: str = "Get the user's medical history including conditions, limitations, medications, and notes. Use this to check for any medical restrictions before recommending exercises."
    args_schema: type = GetMedicalHistoryInput
    
    user_id: int
    db: Session
    
    def _run(self, query: str = "") -> str:
        """Get medical history for the user"""
        medical_history = get_medical_history(self.user_id, self.db)
        
        if not medical_history:
            return "No medical history on file for this user."
        
        result = []
        if medical_history.conditions:
            result.append(f"Conditions: {medical_history.conditions}")
        if medical_history.limitations:
            result.append(f"Limitations: {medical_history.limitations}")
        if medical_history.medications:
            result.append(f"Medications: {medical_history.medications}")
        if medical_history.notes:
            result.append(f"Notes: {medical_history.notes}")
        
        return "\n".join(result) if result else "Medical history exists but no details provided."


class GetUserPreferencesInput(BaseModel):
    """Input for get_user_preferences tool"""
    query: str = Field(default="", description="Optional query string")


class GetUserPreferencesTool(BaseTool):
    """Tool to get user's preferences"""
    name: str = "get_user_preferences"
    description: str = "Get the user's fitness preferences including goals, exercise types, activity level, and location. Use this to tailor recommendations to the user's preferences."
    args_schema: type = GetUserPreferencesInput
    
    user_id: int
    db: Session
    
    def _run(self, query: str = "") -> str:
        """Get user preferences"""
        preferences = self.db.query(UserPreferences).filter(
            UserPreferences.user_id == self.user_id
        ).first()
        
        if not preferences:
            return "No preferences set for this user."
        
        result = []
        if preferences.goals:
            result.append(f"Goals: {preferences.goals}")
        if preferences.exercise_types:
            result.append(f"Exercise Types: {preferences.exercise_types}")
        if preferences.activity_level:
            result.append(f"Activity Level: {preferences.activity_level}")
        if preferences.location:
            result.append(f"Location: {preferences.location}")
        if preferences.dietary_restrictions:
            result.append(f"Dietary Restrictions: {preferences.dietary_restrictions}")
        
        return "\n".join(result) if result else "Preferences exist but no details provided."


class WebSearchInput(BaseModel):
    """Input for web_search tool"""
    query: str = Field(description="Search query string")


class WebSearchTool(BaseTool):
    """Tool to search the web for current information"""
    name: str = "web_search"
    description: str = "Search the web for current information, research, or up-to-date data. Use this when you need recent information that might not be in your training data, such as latest fitness trends, nutrition facts, exercise techniques, or health research."
    args_schema: type = WebSearchInput
    
    def _run(self, query: str) -> str:
        """Search the web using Tavily API"""
        try:
            from tavily import TavilyClient
            
            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                return "Error: TAVILY_API_KEY is not set. Web search is unavailable."
            
            client = TavilyClient(api_key=api_key)
            
            # Perform search
            response = client.search(
                query=query,
                search_depth="basic",  # Can be "basic" or "advanced"
                max_results=5  # Limit to 5 results to keep response concise
            )
            
            if not response.get("results"):
                return f"No results found for query: {query}"
            
            # Format results
            formatted_results = []
            for result in response["results"][:5]:  # Limit to 5 results
                title = result.get("title", "No title")
                url = result.get("url", "")
                content = result.get("content", "")
                
                # Truncate content if too long
                if len(content) > 300:
                    content = content[:297] + "..."
                
                formatted_results.append(f"Title: {title}\nURL: {url}\nContent: {content}")
            
            return "\n\n---\n\n".join(formatted_results)
            
        except ImportError:
            return "Error: tavily-python package is not installed. Please install it with: pip install tavily-python"
        except Exception as e:
            return f"Error performing web search: {str(e)}"


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
        except Exception as e:
            self.db.rollback()
            return f"Error creating nutrition log: {str(e)}"


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
        except Exception as e:
            self.db.rollback()
            return f"Error creating mental fitness log: {str(e)}"


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
        except Exception as e:
            self.db.rollback()
            return f"Error creating workout log: {str(e)}"


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
        """Retrieve conversation history for the user, optionally filtered by agent type."""
        query = self.db.query(ConversationMessage).filter(
            ConversationMessage.user_id == self.user_id
        )
        if agent_type:
            query = query.filter(ConversationMessage.agent_type == agent_type)
        
        messages = query.order_by(ConversationMessage.created_at.asc()).all()
        
        if not messages:
            return "No conversation history found."
        
        formatted_messages = []
        for msg in messages:
            formatted_messages.append(
                f"Agent: {msg.agent_type} - Role: {msg.role}, Content: {msg.content}"
            )
        return "\n".join(formatted_messages)


class BaseAgent:
    """Base agent class with common functionality - using modern LangChain approach without deprecated AgentExecutor"""
    
    def __init__(self, user_id: int, db: Session, model_name: str = "gpt-4.1"):
        self.user_id = user_id
        self.db = db
        
        # Get API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set in environment variables. "
                "Please set it in your .env file or environment."
            )
        
        # Initialize LLM with API key
        # ChatOpenAI automatically reads from OPENAI_API_KEY env var, but we can also pass it explicitly
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0.7,
            openai_api_key=api_key  # LangChain uses 'openai_api_key' parameter
        )
        
        # Initialize tools
        self.tools = [
            GetMedicalHistoryTool(user_id=user_id, db=db),
            GetUserPreferencesTool(user_id=user_id, db=db),
            CreateWorkoutLogTool(user_id=user_id, db=db),
            WebSearchTool(),  # Web search tool (no user_id or db needed)
            GetConversationHistoryTool(user_id=user_id, db=db),  # Conversation history tool
        ]
        
        # Bind tools to LLM for modern LangChain approach
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Create system message
        self.system_message = self._get_system_prompt()
        
        # Cache user context summary (fetched once per agent instance)
        self._user_context_summary = None
        self._context_fetched = False
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for the agent"""
        return """You are a helpful fitness assistant. Always check the user's medical history before recommending any exercises. 
        If an exercise conflicts with their medical conditions, warn them and suggest alternatives.
        Use the available tools to get medical history and user preferences to provide personalized recommendations.
        Be encouraging and provide clear, actionable advice."""
    
    def check_exercise_safety(self, exercise: str) -> Dict[str, Any]:
        """Check if an exercise is safe for the user based on medical history"""
        return check_user_exercise_conflicts(self.user_id, exercise, self.db)
    
    def _get_user_context_summary(self) -> str:
        """
        Get a minimal summary of user context (cached per agent instance).
        Returns a very brief summary to minimize token usage.
        Only includes essential info - agent should use tools for details.
        """
        if self._context_fetched and self._user_context_summary:
            return self._user_context_summary
        
        # Fetch context once and create minimal summary (max 150 chars total)
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
    
    async def run(self, user_input: str) -> str:
        """Run the agent with user input using modern LangChain approach (without AgentExecutor)"""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
            
            # Check if API key is set
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return "Error: OpenAI API key is not configured. Please set OPENAI_API_KEY in your environment variables."
            
            # Get minimal context summary (cached, fetched once per agent instance)
            context_summary = self._get_user_context_summary()
            
            # Build system message with minimal context
            # The agent should use tools for detailed information when needed
            enhanced_system_message = self.system_message
            if context_summary:
                # Include only a very brief summary - agent should use tools for details
                enhanced_system_message += f"\n\nUser context (brief): {context_summary}. Use tools for details."
            else:
                enhanced_system_message += "\n\nUse get_medical_history and get_user_preferences tools to fetch user information."
            
            # Build messages with enhanced system prompt
            messages = [
                SystemMessage(content=enhanced_system_message),
                HumanMessage(content=user_input)
            ]
            
            max_iterations = 5  # Prevent infinite loops
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                
                # Get LLM response with tools
                response = await self.llm_with_tools.ainvoke(messages)
                messages.append(response)
                
                # Check if LLM wants to call tools
                if hasattr(response, 'tool_calls') and response.tool_calls and len(response.tool_calls) > 0:
                    # Execute tool calls
                    for tool_call in response.tool_calls:
                        tool_name = tool_call.get("name", "")
                        tool_input = tool_call.get("args", {})
                        tool_call_id = tool_call.get("id", "")
                        
                        # Find and execute the tool
                        tool_result = None
                        for tool in self.tools:
                            if tool.name == tool_name:
                                try:
                                    tool_result = tool._run(**tool_input)
                                    break
                                except Exception as e:
                                    tool_result = f"Error executing {tool_name}: {str(e)}"
                                    break
                        
                        if tool_result is None:
                            tool_result = f"Tool {tool_name} not found"
                        
                        # Add tool result as ToolMessage
                        messages.append(ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_call_id
                        ))
                else:
                    # No tool calls, return the final response
                    return response.content if hasattr(response, 'content') else str(response)
            
            # If we've reached max iterations, return the last response
            last_response = messages[-1]
            return last_response.content if hasattr(last_response, 'content') else str(last_response)
            
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

