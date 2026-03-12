"""
Conversation message schemas for request/response validation.

This module defines Pydantic schemas for conversation-related endpoints. These schemas
provide request/response validation, serialization, and documentation for managing
conversation messages between users and AI agents.

Key Features:
- Conversation message create schema (for storing messages)
- Conversation message response schema (for returning messages)
- Conversation history response schema (for returning multiple messages)
- Support for image attachments and warnings
- Agent type filtering support

Agent Types:
- physical-fitness: Physical Fitness Agent
- nutrition: Nutrition Agent
- mental-fitness: Mental Fitness Agent
- coordinator: Coordinator Agent
"""

from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class ConversationMessageCreate(BaseModel):
    """
    Conversation message create schema for storing conversation messages.
    
    This schema validates input data when creating a new conversation message.
    Used to store both user messages and agent responses in the conversation history.
    
    Attributes:
        role: Message role - 'user' or 'assistant' (required)
        content: Message content/text (required)
        warnings: List of warning messages (optional)
        image_path: Path to stored image file if message includes image (optional)
        agent_type: Type of agent that handled/responded to the message (optional, default: 'coordinator')
        
    Message Roles:
        - "user": Message sent by the user (input/query)
        - "assistant": Message sent by the AI agent (response)
        
    Agent Types:
        - "physical-fitness": Physical Fitness Agent
        - "nutrition": Nutrition Agent
        - "mental-fitness": Mental Fitness Agent
        - "coordinator": Coordinator Agent (default)
        
    Image Support:
        - image_path: Relative path from uploads directory (e.g., "images/user123_food.jpg")
        - Used for image-based interactions (e.g., food photo analysis)
        - Images are stored on disk and served statically via /uploads endpoint
        
    Warnings:
        Warnings can include:
        - Safety warnings (e.g., exercise conflicts with medical conditions)
        - Data quality warnings (e.g., incomplete information)
        - Service degradation warnings (e.g., fallback model used)
        
    Note:
        - Role and content are required fields
        - Agent type defaults to 'coordinator' for backward compatibility
        - Image path is optional (only for image-based messages)
        - Warnings are optional (only present if there are warnings)
    """
    role: str  # 'user' or 'assistant'
    content: str
    warnings: Optional[List[str]] = None
    image_path: Optional[str] = None  # Path to stored image
    agent_type: Optional[str] = 'coordinator'  # 'physical-fitness', 'nutrition', 'mental-fitness', 'coordinator'


class ConversationMessageResponse(BaseModel):
    """
    Conversation message response schema for returning conversation message data.
    
    This schema defines what conversation message information is returned to clients.
    Includes all message fields plus metadata (id, created_at).
    
    Attributes:
        id: Message unique identifier (primary key)
        role: Message role - 'user' or 'assistant'
        content: Message content/text
        warnings: List of warning messages (optional)
        image_path: Path to stored image file if message includes image (optional)
        agent_type: Type of agent that handled/responded to the message
        created_at: Timestamp when message was created
        
    Message Roles:
        - "user": Message sent by the user
        - "assistant": Message sent by the AI agent
        
    Agent Types:
        - "physical-fitness": Physical Fitness Agent
        - "nutrition": Nutrition Agent
        - "mental-fitness": Mental Fitness Agent
        - "coordinator": Coordinator Agent
        
    Config:
        from_attributes = True: Allows creating schema from SQLAlchemy model
        This enables automatic conversion from ConversationMessage model to response schema
        
    Note:
        - Used in endpoints that return conversation messages
        - Automatically serializes datetime to ISO format string
        - Can be created directly from ConversationMessage model using from_attributes
        - Messages are ordered by created_at timestamp for conversation flow
    """
    id: int
    role: str
    content: str
    warnings: Optional[List[str]] = None
    image_path: Optional[str] = None  # Path to stored image
    agent_type: str  # 'physical-fitness', 'nutrition', 'mental-fitness', 'coordinator'
    created_at: datetime

    class Config:
        # Enable creating schema instance from SQLAlchemy model attributes
        # This allows: ConversationMessageResponse.from_orm(message_model_instance)
        from_attributes = True


class ConversationHistoryResponse(BaseModel):
    """
    Conversation history response schema for returning multiple conversation messages.
    
    This schema defines the response format when returning conversation history.
    Includes a list of messages ordered by creation time.
    
    Attributes:
        messages: List of ConversationMessageResponse objects (ordered by created_at)
        
    Message Ordering:
        Messages are ordered by created_at timestamp (ascending) to maintain
        conversation flow. The first message is the oldest, the last is the most recent.
        
    Filtering:
        Messages can be filtered by agent_type to show only relevant conversation history:
        - Filter by specific agent (e.g., "nutrition") to see only nutrition conversations
        - No filter returns all conversation messages
        
    Note:
        - Used in endpoints that return conversation history
        - Supports filtering by agent_type
        - Messages are automatically ordered chronologically
        - Empty list if no messages exist
    """
    messages: List[ConversationMessageResponse]

