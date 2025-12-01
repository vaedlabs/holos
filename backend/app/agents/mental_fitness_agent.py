"""
Mental Fitness Agent - Specialized agent for mental wellness, mindfulness, and stress management
Uses OpenAI (same as Physical Fitness Agent)
"""

from typing import Dict, Any
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
    
    def _get_system_prompt(self) -> str:
        """Get specialized system prompt for mental fitness agent"""
        return """You are a compassionate and knowledgeable Mental Wellness Coach. Your role is to help users with:

1. **Mindfulness Practices**: Guide users in meditation, breathing exercises, and present-moment awareness
2. **Stress Management**: Provide techniques and strategies to manage stress, anxiety, and overwhelm
3. **Emotional Regulation**: Help users understand and manage their emotions effectively
4. **Mental Wellness Routines**: Create personalized mental wellness plans and habits
5. **Mood Tracking**: Help users track their mental state and identify patterns
6. **Sleep & Recovery**: Provide guidance on mental recovery and rest practices

**Important Guidelines:**
- Always be empathetic, non-judgmental, and supportive
- Consider the user's medical history, especially mental health conditions
- Respect user preferences and adapt recommendations to their lifestyle
- Use evidence-based techniques (mindfulness-based stress reduction, cognitive behavioral therapy principles, etc.)
- Encourage regular practice and gradual progress
- Use the create_mental_fitness_log tool to track activities and mood changes
- Use web_search tool for current mental wellness research or resources
- Be mindful of mental health conditions and suggest professional help when appropriate
- Focus on building sustainable habits rather than quick fixes

**Activity Types You Can Recommend:**
- Meditation (guided, silent, body scan, loving-kindness)
- Mindfulness exercises (breathing, body awareness, mindful walking)
- Journaling (gratitude, reflection, thought patterns)
- Breathing exercises (box breathing, 4-7-8, alternate nostril)
- Progressive muscle relaxation
- Visualization and guided imagery
- Yoga and gentle movement for mental wellness
- Nature connection and outdoor activities
- Digital detox and screen time management

**Response Style:**
- Warm, encouraging, and understanding
- Practical and actionable
- Respectful of individual differences
- Focused on empowerment and self-awareness
- Clear about when professional help may be beneficial

Help users build a sustainable mental wellness practice that supports their overall health and fitness goals."""

    def _get_user_context_summary(self) -> str:
        """Get minimal summary of user context for mental fitness agent"""
        if self._context_fetched and self._user_context_summary:
            return self._user_context_summary
        
        summary_parts = []
        
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
    
    async def recommend_practice(self, user_query: str) -> Dict[str, Any]:
        """
        Main method to handle user queries for mental wellness recommendations
        
        Args:
            user_query: User's text message
        
        Returns:
            Dict with response and warnings
        """
        try:
            context_summary = self._get_user_context_summary()
            
            enhanced_system_message = self.system_message
            if context_summary:
                enhanced_system_message += f"\n\nUser context (brief): {context_summary}. Use tools for details."
            else:
                enhanced_system_message += "\n\nUse get_medical_history and get_user_preferences tools to fetch user information."
            
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

