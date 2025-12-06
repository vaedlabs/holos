"""
Schemas for agent execution logs
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class AgentExecutionLogResponse(BaseModel):
    """Response schema for agent execution log"""
    id: int
    trace_id: str
    agent_type: str
    user_id: int
    query: Optional[str] = None
    response: Optional[str] = None
    warnings: Optional[List[str]] = None
    tools_called: Optional[List[Dict[str, Any]]] = None
    tokens_used: int
    duration_ms: Optional[float] = None
    success: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class AgentExecutionLogsListResponse(BaseModel):
    """Response schema for list of agent execution logs"""
    logs: List[AgentExecutionLogResponse]
    total: int
    page: int
    page_size: int

