"""
Agent request/response schemas
"""

from pydantic import BaseModel
from typing import Optional, List


class AgentChatRequest(BaseModel):
    """Schema for agent chat request"""
    message: str
    agent_type: str = "physical-fitness"  # For MVP, only physical-fitness


class AgentChatResponse(BaseModel):
    """Schema for agent chat response"""
    response: str
    warnings: Optional[List[str]] = None

