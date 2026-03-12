"""
Agent execution log schemas for observability and debugging.

This module defines Pydantic schemas for agent execution log endpoints. These schemas
provide request/response validation, serialization, and documentation for accessing
agent execution logs used for observability, debugging, and performance monitoring.

Key Features:
- Agent execution log response schema (includes all observability data)
- Paginated list response schema (with page information)
- Support for filtering by agent type
- Structured tool call and warning data

Observability Data:
- Trace ID for request tracking
- Query and response data
- Tool call tracking
- Token usage and performance metrics
- Success/failure status
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class AgentExecutionLogResponse(BaseModel):
    """
    Agent execution log response schema for returning execution log data.
    
    This schema defines what execution log information is returned to clients.
    Includes all observability data including trace ID, query, response, tool calls,
    token usage, and performance metrics.
    
    Attributes:
        id: Execution log unique identifier (primary key)
        trace_id: Unique trace identifier for this execution
        agent_type: Type of agent that executed
        user_id: Foreign key to User model
        query: User's query/input that triggered the agent (optional)
        response: Agent's response text (truncated to 1000 chars, optional)
        warnings: List of warning messages (optional)
        tools_called: List of tools called during execution with inputs/outputs (optional)
        tokens_used: Total tokens consumed during execution
        duration_ms: Execution duration in milliseconds (optional)
        success: Whether execution succeeded
        created_at: Timestamp when execution log was created
        
    Trace ID Format:
        Format: "{agent_type}_{user_id}_{uuid}_{timestamp}"
        Example: "nutrition_123_a1b2c3d4_1704067200000"
        Used for request tracking and debugging
        
    Agent Types:
        - "coordinator": Coordinator Agent
        - "physical-fitness": Physical Fitness Agent
        - "nutrition": Nutrition Agent
        - "mental-fitness": Mental Fitness Agent
        
    Tools Called Format:
        List of dictionaries, each containing:
        {
            "name": "get_medical_history",
            "input": {"query": ""},
            "output": "No medical history on file.",
            "timestamp": "2024-01-01T12:00:00"
        }
        
    Warnings Format:
        List of warning strings:
        [
            "Exercise may conflict with knee injury",
            "Using fallback model due to API errors"
        ]
        
    Performance Metrics:
        - tokens_used: Total tokens consumed (input + output)
        - duration_ms: Total execution time in milliseconds
        - success: Boolean indicating if execution completed successfully
        
    Config:
        from_attributes = True: Allows creating schema from SQLAlchemy model
        This enables automatic conversion from AgentExecutionLog model to response schema
        
    Note:
        - Used in endpoints that return execution logs
        - Automatically serializes datetime to ISO format string
        - Can be created directly from AgentExecutionLog model using from_attributes
        - Response is truncated to 1000 characters to manage storage
        - Used for observability, debugging, and performance analysis
    """
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
        # Enable creating schema instance from SQLAlchemy model attributes
        # This allows: AgentExecutionLogResponse.from_orm(execution_log_model_instance)
        from_attributes = True


class AgentExecutionLogsListResponse(BaseModel):
    """
    Agent execution logs list response schema for paginated execution log lists.
    
    This schema defines the response format when returning multiple execution logs.
    Includes the list of logs, total count, and pagination information.
    
    Attributes:
        logs: List of AgentExecutionLogResponse objects (for current page)
        total: Total number of execution logs matching the query (for pagination)
        page: Current page number (1-indexed)
        page_size: Number of logs per page
        
    Pagination:
        The pagination fields allow clients to:
        - Calculate total pages: ceil(total / page_size)
        - Determine if more pages exist: page < ceil(total / page_size)
        - Navigate between pages
        - Display pagination controls in UI
        
    Filtering:
        Logs can be filtered by:
        - agent_type: Filter by specific agent (e.g., "nutrition")
        - user_id: Automatically filtered to current user
        - date range: Can filter by created_at timestamp
        
    Note:
        - Used in endpoints that return lists of execution logs
        - Supports filtering by agent_type
        - Supports pagination with page and page_size
        - Total count includes all matching logs, not just returned page
        - Logs are ordered by created_at (most recent first)
    """
    logs: List[AgentExecutionLogResponse]
    total: int
    page: int
    page_size: int

