"""
Agent request/response schemas
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class AgentChatRequest(BaseModel):
    """Schema for agent chat request"""
    message: str
    agent_type: str = "physical-fitness"  # physical-fitness, nutrition, mental-fitness
    image_base64: Optional[str] = None  # Optional base64-encoded image for Nutrition Agent


class AgentChatResponse(BaseModel):
    """Schema for agent chat response"""
    response: str
    warnings: Optional[List[str]] = None
    nutrition_analysis: Optional[Dict[str, Any]] = None  # Structured nutrition data from image analysis (Nutrition Agent only)
    steps: Optional[List[str]] = None  # Step-by-step updates from coordinator agent showing what it's doing

