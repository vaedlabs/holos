"""
Read tools: medical history, preferences and conversation history.

Moved unchanged from app/agents/base_agent.py (Plan P2.1).
P2.2 replaces these with async tools.
"""

from typing import Optional
from langchain_core.tools import BaseTool
from sqlalchemy.orm import Session
from app.services.medical_service import get_medical_history
from app.services.tool_cache import tool_cache
from app.models.user_preferences import UserPreferences
from app.models.conversation_message import ConversationMessage
from pydantic import BaseModel, Field


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
