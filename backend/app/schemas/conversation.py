"""
Conversation message schemas
"""

from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class ConversationMessageCreate(BaseModel):
    """Schema for creating a conversation message"""
    role: str  # 'user' or 'assistant'
    content: str
    warnings: Optional[List[str]] = None
    image_path: Optional[str] = None  # Path to stored image
    agent_type: Optional[str] = 'coordinator'  # 'physical-fitness', 'nutrition', 'mental-fitness', 'coordinator'


class ConversationMessageResponse(BaseModel):
    """Schema for conversation message response"""
    id: int
    role: str
    content: str
    warnings: Optional[List[str]] = None
    image_path: Optional[str] = None  # Path to stored image
    agent_type: str  # 'physical-fitness', 'nutrition', 'mental-fitness', 'coordinator'
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationHistoryResponse(BaseModel):
    """Schema for conversation history response"""
    messages: List[ConversationMessageResponse]

