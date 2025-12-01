# Pydantic schemas

from app.schemas.user import UserRegister, UserLogin, UserResponse, Token
from app.schemas.medical import MedicalHistoryCreate, MedicalHistoryResponse
from app.schemas.preferences import UserPreferencesCreate, UserPreferencesResponse
from app.schemas.agents import AgentChatRequest, AgentChatResponse

__all__ = [
    "UserRegister", "UserLogin", "UserResponse", "Token",
    "MedicalHistoryCreate", "MedicalHistoryResponse",
    "UserPreferencesCreate", "UserPreferencesResponse",
    "AgentChatRequest", "AgentChatResponse"
]
