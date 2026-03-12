"""
Agent request/response schemas for AI agent interactions.

This module defines Pydantic schemas for agent-related API endpoints. These schemas
provide request/response validation, serialization, and documentation for interactions
with AI agents (Physical Fitness, Nutrition, Mental Fitness, and Coordinator agents).

Key Features:
- Agent chat request schema (supports text and image inputs)
- Agent chat response schema (includes warnings, analysis, and status information)
- Support for degraded mode and fallback information
- Structured nutrition analysis data
- Step-by-step coordinator updates

Agent Types:
- physical-fitness: Physical Fitness Agent
- nutrition: Nutrition Agent (supports image analysis)
- mental-fitness: Mental Fitness Agent
- coordinator: Coordinator Agent (routes queries or creates holistic plans)
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class AgentChatRequest(BaseModel):
    """
    Agent chat request schema for sending queries to AI agents.
    
    This schema validates the input data when a user sends a message to an AI agent.
    Supports both text queries and optional image attachments (for Nutrition Agent).
    
    Attributes:
        message: User's text query or message (required)
        agent_type: Type of agent to handle the query (default: "physical-fitness")
        image_base64: Optional base64-encoded image (for Nutrition Agent food analysis)
        
    Agent Types:
        - "physical-fitness": Physical Fitness Agent (exercise recommendations)
        - "nutrition": Nutrition Agent (meal planning, food analysis with images)
        - "mental-fitness": Mental Fitness Agent (mental wellness guidance)
        - "coordinator": Coordinator Agent (routes queries or creates holistic plans)
        
    Image Support:
        - image_base64: Base64-encoded image string (data URL format)
        - Used by Nutrition Agent for food photo analysis
        - Format: "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
        - Optional - only required for image-based queries
        
    Note:
        - Message is required for all agent interactions
        - Agent type defaults to "physical-fitness" for backward compatibility
        - Image is optional but required for Nutrition Agent image analysis features
    """
    message: str
    agent_type: str = "physical-fitness"  # physical-fitness, nutrition, mental-fitness
    image_base64: Optional[str] = None  # Optional base64-encoded image for Nutrition Agent


class AgentChatResponse(BaseModel):
    """
    Agent chat response schema for returning agent responses to clients.
    
    This schema defines the response format from AI agents. It includes the agent's
    response text, optional warnings, structured data (for Nutrition Agent), and
    status information about the execution.
    
    Attributes:
        response: Agent's text response to the user's query (required)
        warnings: List of warning messages (optional)
        nutrition_analysis: Structured nutrition data from image analysis (Nutrition Agent only)
        steps: Step-by-step updates from coordinator agent (optional)
        degraded: Boolean indicating if degraded functionality was used (default: False)
        fallback_info: Information about model fallbacks or agent failures (optional)
        
    Warnings:
        Warnings can include:
        - Safety warnings (e.g., exercise conflicts with medical conditions)
        - Data quality warnings (e.g., incomplete information)
        - Service degradation warnings (e.g., fallback model used)
        - Timeout warnings (e.g., request took longer than expected)
        
    Nutrition Analysis (Nutrition Agent only):
        Structured data returned when analyzing food images:
        {
            "foods": [
                {"name": "Grilled Chicken", "quantity": "200g", "calories": 330},
                {"name": "Brown Rice", "quantity": "1 cup", "calories": 216}
            ],
            "total_calories": 546,
            "macros": {"protein": 45.5, "carbs": 120.0, "fats": 25.3},
            "meal_type": "lunch",
            "confidence": 0.85
        }
        
    Steps (Coordinator Agent only):
        Step-by-step updates showing what the coordinator is doing:
        [
            "Analyzing query...",
            "Routing to Physical Fitness Agent...",
            "Creating holistic plan combining all three domains..."
        ]
        
    Degraded Mode:
        The degraded flag indicates if fallback models or degraded functionality was used:
        - False: Normal operation with primary models
        - True: Fallback models used or some features unavailable
        
        When degraded=True, check fallback_info for details about what failed.
        
    Fallback Info:
        Information about model fallbacks or agent failures:
        {
            "original_model": "gpt-4.1",
            "fallback_model": "gpt-4o-mini",
            "reason": "Model fallback due to errors",
            "failed_agents": ["nutrition"],  # If coordinator agent
            "successful_agents": ["physical-fitness", "mental-fitness"]
        }
        
    Note:
        - Response is always present (required field)
        - Other fields are optional and depend on agent type and execution context
        - Warnings help users understand limitations or issues
        - Degraded mode and fallback info provide transparency about service quality
    """
    response: str
    warnings: Optional[List[str]] = None
    nutrition_analysis: Optional[Dict[str, Any]] = None  # Structured nutrition data from image analysis (Nutrition Agent only)
    steps: Optional[List[str]] = None  # Step-by-step updates from coordinator agent showing what it's doing
    degraded: bool = False  # P0.3: Indicates if fallback models or degraded functionality was used
    fallback_info: Optional[Dict[str, Any]] = None  # P0.3: Information about which models/agents succeeded/failed

