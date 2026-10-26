"""
Pydantic schemas package.

This module exports all Pydantic validation schemas for request/response models.
Schemas provide type validation, serialization, and API documentation.

Exported Schemas:
    Authentication:
        - UserResponse: User data response
    
    Medical History:
        - MedicalHistoryCreate: Create/update medical history request
        - MedicalHistoryResponse: Medical history response
    
    User Preferences:
        - UserPreferencesCreate: Create/update preferences request
        - UserPreferencesResponse: User preferences response
    
    Agent Interactions:
        - AgentChatRequest: Agent chat request (query, agent_type, etc.)
        - AgentChatResponse: Agent chat response (message, warnings, etc.)

Usage:
    from app.schemas import UserResponse, AgentChatRequest
    
    # Schemas are used by FastAPI for request validation and response serialization
    # Pydantic automatically validates types, formats, and constraints
"""

from app.schemas.user import UserResponse
from app.schemas.medical import MedicalHistoryCreate, MedicalHistoryResponse
from app.schemas.preferences import UserPreferencesCreate, UserPreferencesResponse
from app.schemas.agents import AgentChatRequest, AgentChatResponse

# Export all schemas for convenient importing
# Makes schemas available via: from app.schemas import UserResponse, AgentChatRequest
__all__ = [
    # Authentication schemas
    "UserResponse",  # User data response
    # Medical history schemas
    "MedicalHistoryCreate",  # Create/update medical history request
    "MedicalHistoryResponse",  # Medical history response
    # User preferences schemas
    "UserPreferencesCreate",  # Create/update preferences request
    "UserPreferencesResponse",  # User preferences response
    # Agent interaction schemas
    "AgentChatRequest",  # Agent chat request (query, agent_type, etc.)
    "AgentChatResponse"  # Agent chat response (message, warnings, etc.)
]
