"""The old agents' execution logs (GET /agents/execution-logs), until P4.12 drops
them with `agent_execution_logs`. The chat endpoints moved to routers/chat.py (P4.7).
"""


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_database
from app.models.agent_execution_log import AgentExecutionLog
from app.models.user import User
from app.schemas.agent_logs import AgentExecutionLogsListResponse
from app.schemas.conversation import AgentType

# FastAPI router for agent interaction endpoints
# Prefix: /agents (all routes will be prefixed with /agents)
# Tags: ["agents"] (for API documentation grouping)
router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/execution-logs", response_model=AgentExecutionLogsListResponse)
async def get_agent_execution_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    agent_type: AgentType | None = Query(default=None, description="Filter by agent type (coordinator, physical-fitness, nutrition, mental-fitness)"),
    limit: int | None = Query(default=50, ge=1, le=100, description="Maximum number of logs to return"),
    offset: int | None = Query(default=0, ge=0, description="Number of logs to skip")
):
    """
    Get agent execution logs for the current user.
    
    This endpoint retrieves agent execution logs for debugging, performance monitoring,
    and observability. Logs include agent type, query, response, tool calls, token
    usage, performance metrics, and execution status.
    
    Log Information:
        - Agent type (coordinator, physical-fitness, nutrition, mental-fitness)
        - User query and image (if provided)
        - Agent response and warnings
        - Tool calls and results
        - Token usage (input, output, total)
        - Performance metrics (execution time, latency)
        - Execution status (success, failure, error details)
    
    Filtering and Pagination:
        - Filter by agent type (optional)
        - Pagination with limit and offset
        - Ordered by most recent first (created_at DESC)
        - Returns total count for pagination UI
    
    Args:
        current_user: Authenticated user (injected dependency)
                     Users can only access their own execution logs
        db: Database session (injected dependency)
        agent_type: Optional[str] - Filter by agent type:
                    - "coordinator": Coordinator agent logs
                    - "physical-fitness": Physical Fitness agent logs
                    - "nutrition": Nutrition agent logs
                    - "mental-fitness": Mental Fitness agent logs
        limit: Optional[int] - Maximum number of logs to return (1-100, default: 50)
        offset: Optional[int] - Number of logs to skip for pagination (default: 0)
    
    Returns:
        AgentExecutionLogsListResponse containing:
            - logs: List[AgentExecutionLog] (list of execution logs)
            - total: int (total number of logs matching filter)
            - page: int (current page number)
            - page_size: int (number of logs per page)
            
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only access their own execution logs (filtered by user_id)
        
    Error Handling:
        - Returns 500 error if database query fails
        
    Example:
        GET /agents/execution-logs?agent_type=nutrition&limit=20&offset=0
        
        Returns logs for Nutrition agent, 20 per page, starting from first page
    """
    try:
        # Query agent execution logs for the current user
        # Filter by user_id to ensure users can only access their own logs
        logs_query = db.query(AgentExecutionLog).filter(
            AgentExecutionLog.user_id == current_user.id  # Security: Only current user's logs
        )
        
        # Filter by agent type if provided
        # Allows filtering logs by specific agent type
        if agent_type:
            logs_query = logs_query.filter(AgentExecutionLog.agent_type == agent_type)
        
        # Order by most recent first
        # Most recent logs appear first (DESC order by created_at)
        logs_query = logs_query.order_by(desc(AgentExecutionLog.created_at))
        
        # Get total count
        # Total count needed for pagination UI (before applying limit/offset)
        total = logs_query.count()
        
        # Apply pagination
        # Skip 'offset' logs and return 'limit' logs
        logs = logs_query.offset(offset).limit(limit).all()
        
        # Return paginated response
        return AgentExecutionLogsListResponse(
            logs=logs,  # List of execution logs
            total=total,  # Total count for pagination
            page=(offset // limit) + 1 if limit > 0 else 1,  # Current page number
            page_size=limit  # Number of logs per page
        )
    except Exception as e:
        # Handle database query errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve agent execution logs: {str(e)}"
        )

