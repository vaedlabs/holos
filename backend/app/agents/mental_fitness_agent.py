"""
Mental Fitness Agent - Specialized agent for mental wellness, mindfulness, and stress management
Uses OpenAI (same as Physical Fitness Agent)
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
import os

from app.agents.base_agent import (
    GetMedicalHistoryTool,
    GetUserPreferencesTool,
    CreateMentalFitnessLogTool,
    WebSearchTool
)
from app.services.medical_service import get_medical_history
from app.models.user_preferences import UserPreferences


class MentalFitnessAgent:
    """Mental Fitness Agent specialized for mindfulness, stress management, and mental wellness"""
    
    def __init__(
        self, 
        user_id: int, 
        db: Session, 
        model_name: str = "gpt-4.1",
        shared_context: Optional[Dict[str, Optional[Dict]]] = None,
        tracer: Optional[Any] = None
    ):
        self.user_id = user_id
        self.db = db
        
        # Store shared context if provided (from ContextManager)
        self._shared_context = shared_context
        
        # Store tracer for observability (optional)
        self.tracer = tracer
        
        # Get API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set in environment variables. "
                "Please set it in your .env file or environment."
            )
        
        # Initialize LLM with API key
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0.7,
            openai_api_key=api_key
        )
        
        # Initialize tools
        self.tools = [
            GetMedicalHistoryTool(user_id=user_id, db=db),
            GetUserPreferencesTool(user_id=user_id, db=db),
            CreateMentalFitnessLogTool(user_id=user_id, db=db),
            WebSearchTool(),  # Web search for mental wellness resources
        ]
        
        # Bind tools to LLM
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Create system message
        self.system_message = self._get_system_prompt()
        
        # Cache user context summary
        self._user_context_summary = None
        self._context_fetched = False
    
    def _get_agent_type(self) -> str:
        """Get agent type identifier"""
        return "mental_fitness"
    
    def _get_system_prompt(self) -> str:
        """
        Get specialized system prompt for mental fitness agent with humanization guidelines.
        Checks cache first, then builds if not cached.
        """
        # Check cache first
        agent_type = self._get_agent_type()
        from app.services.prompt_cache import prompt_cache
        cached_prompt = prompt_cache.get_static_prompt(agent_type)
        if cached_prompt:
            return cached_prompt
        
        # Not cached, build it
        # Use prompt component system
        from app.agents.prompts.mental_fitness_prompt import get_mental_fitness_prompt
        return get_mental_fitness_prompt()

    def _get_user_context_summary(self) -> str:
        """Get minimal summary of user context for mental fitness agent"""
        if self._context_fetched and self._user_context_summary:
            return self._user_context_summary
        
        summary_parts = []
        
        # Use shared context if provided (from ContextManager)
        if self._shared_context:
            # Get medical history from shared context - especially important for mental health
            medical_history = self._shared_context.get("medical_history")
            if medical_history:
                if medical_history.get("conditions"):
                    conditions = medical_history["conditions"].strip()
                    if conditions:
                        if len(conditions) > 50:
                            conditions = conditions[:47] + "..."
                        summary_parts.append(f"Medical: {conditions}")
                
                if medical_history.get("medications"):
                    medications = medical_history["medications"].strip()
                    if medications:
                        if len(medications) > 40:
                            medications = medications[:37] + "..."
                        summary_parts.append(f"Meds: {medications}")
            
            # Get user preferences from shared context
            preferences = self._shared_context.get("preferences")
            if preferences:
                if preferences.get("goals"):
                    goals = preferences["goals"].strip()
                    if goals:
                        if len(goals) > 40:
                            goals = goals[:37] + "..."
                        summary_parts.append(f"Goals: {goals}")
            
            self._user_context_summary = " | ".join(summary_parts) if summary_parts else ""
            self._context_fetched = True
            return self._user_context_summary
        
        # Fallback: Fetch context independently (for backward compatibility)
        # Get medical history - especially important for mental health
        medical_history = get_medical_history(self.user_id, self.db)
        if medical_history:
            if medical_history.conditions:
                conditions = medical_history.conditions.strip()
                if len(conditions) > 50:
                    conditions = conditions[:47] + "..."
                summary_parts.append(f"Medical: {conditions}")
            
            if medical_history.medications:
                medications = medical_history.medications.strip()
                if len(medications) > 40:
                    medications = medications[:37] + "..."
                summary_parts.append(f"Meds: {medications}")
        
        # Get user preferences for activity level and goals
        preferences = self.db.query(UserPreferences).filter(
            UserPreferences.user_id == self.user_id
        ).first()
        
        if preferences:
            if preferences.goals:
                goals = preferences.goals.strip()
                if len(goals) > 40:
                    goals = goals[:37] + "..."
                summary_parts.append(f"Goals: {goals}")
        
        self._user_context_summary = " | ".join(summary_parts) if summary_parts else ""
        self._context_fetched = True
        return self._user_context_summary
    
    def _build_enhanced_system_prompt(self) -> str:
        """
        Build system prompt with enhanced context to reduce tool calls.
        
        Strategy: Include full context in system prompt upfront to reduce tool calls.
        This offsets the cost of larger prompts by reducing tool call tokens.
        
        Returns:
            Enhanced system prompt with full context included
        """
        base_prompt = self.system_message
        
        # Use shared context if available (from ContextManager - already cached)
        if self._shared_context:
            context_parts = []
            
            # Include full medical history if available (especially important for mental health)
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
            preferences = self._shared_context.get("user_preferences")
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
                
                if pref_parts:
                    context_parts.append("## User Preferences\n" + "\n".join(pref_parts))
            
            # Add context section if we have any context
            if context_parts:
                context_section = "\n\n".join(context_parts)
                base_prompt += f"\n\n## User Context (Available Information)\n{context_section}"
                base_prompt += "\n\n**IMPORTANT**: You have full user context above. Only call tools (get_medical_history, get_user_preferences) if you need information NOT provided above or if the context seems outdated. For real-time information (web search, conversation history) or actions (creating logs), use tools as needed."
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
        from app.services.prompt_cache import prompt_cache
        prompt_cache.set_enhanced_prompt(self._get_agent_type(), self.user_id, base_prompt)
        
        return base_prompt
    
    async def recommend_practice(self, user_query: str) -> Dict[str, Any]:
        """
        Main method to handle user queries for mental wellness recommendations
        
        Args:
            user_query: User's text message
        
        Returns:
            Dict with response and warnings
        """
        try:
            # Build enhanced system message with full context to reduce tool calls
            enhanced_system_message = self._build_enhanced_system_prompt()
            
            messages = [
                SystemMessage(content=enhanced_system_message),
                HumanMessage(content=user_query)
            ]
            
            max_iterations = 5
            iteration = 0
            
            while iteration < max_iterations:
                # Get LLM response with potential tool calls
                response = await self.llm_with_tools.ainvoke(messages)
                messages.append(response)
                
                # Check if LLM wants to call tools
                if hasattr(response, 'tool_calls') and response.tool_calls:
                    for tool_call in response.tool_calls:
                        tool_name = tool_call.get('name', '')
                        tool_args = tool_call.get('args', {})
                        tool_call_id = tool_call.get('id', '')
                        
                        # Find and execute the tool
                        tool = next((t for t in self.tools if t.name == tool_name), None)
                        if tool:
                            try:
                                # Execute tool based on type
                                if tool_name == "create_mental_fitness_log":
                                    result = tool._run(**tool_args)
                                elif tool_name == "web_search":
                                    result = tool._run(**tool_args)
                                elif tool_name == "get_medical_history":
                                    result = tool._run(**tool_args)
                                elif tool_name == "get_user_preferences":
                                    result = tool._run(**tool_args)
                                else:
                                    result = tool._run(**tool_args)
                                
                                # Add tool message to conversation
                                messages.append(ToolMessage(
                                    content=result,
                                    tool_call_id=tool_call_id
                                ))
                            except Exception as e:
                                messages.append(ToolMessage(
                                    content=f"Error executing {tool_name}: {str(e)}",
                                    tool_call_id=tool_call_id
                                ))
                    iteration += 1
                    continue
                else:
                    # No more tool calls, return final response
                    final_response = response.content if hasattr(response, 'content') else str(response)
                    return {
                        "response": final_response,
                        "warnings": []
                    }
            
            # Max iterations reached
            final_response = messages[-1].content if hasattr(messages[-1], 'content') else str(messages[-1])
            return {
                "response": final_response,
                "warnings": []
            }
            
        except Exception as e:
            return {
                "response": f"Error processing request: {str(e)}",
                "warnings": [f"Agent error: {str(e)}"]
            }
    
    async def create_wellness_plan(self, focus_area: str = None, duration_minutes: int = 10) -> str:
        """
        Create a structured mental wellness plan for the user.
        
        Args:
            focus_area: Optional focus area (stress, sleep, anxiety, focus, etc.)
            duration_minutes: Duration for daily practice
        
        Returns:
            Wellness plan as string
        """
        query = f"Create a {duration_minutes}-minute daily mental wellness plan"
        if focus_area:
            query += f" focused on {focus_area}"
        query += ". Make sure to check my medical history first and create a plan that's safe and appropriate for me."
        
        result = await self.recommend_practice(query)
        return result["response"]

