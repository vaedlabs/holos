"""
Agent interaction routes
"""

import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from fastapi import Query
from sqlalchemy import desc
from typing import Optional
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.models.agent_execution_log import AgentExecutionLog
from app.agents.physical_fitness_agent import PhysicalFitnessAgent
from app.agents.nutrition_agent import NutritionAgent
from app.agents.mental_fitness_agent import MentalFitnessAgent
from app.agents.coordinator_agent import CoordinatorAgent
from app.schemas.agents import AgentChatRequest, AgentChatResponse
from app.schemas.agent_logs import AgentExecutionLogResponse, AgentExecutionLogsListResponse
from app.services.agent_tracer import AgentTracer

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/physical-fitness/chat", response_model=AgentChatResponse)
async def chat_with_physical_fitness_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Physical Fitness Agent.
    The agent will check medical history and preferences before responding.
    """
    # Create tracer for observability
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="physical-fitness",
        user_id=current_user.id,
        query=request.message,
        image_base64=request.image_base64
    )
    
    try:
        # Initialize agent for current user with tracer
        agent = PhysicalFitnessAgent(user_id=current_user.id, db=db, tracer=tracer)
        
        # Get response with potential warnings
        result = await agent.recommend_exercise(request.message)
        
        # End trace
        tracer.end_trace(
            response=result["response"],
            warnings=result.get("warnings"),
            success=True
        )
        
        return AgentChatResponse(
            response=result["response"],
            warnings=result.get("warnings"),
            nutrition_analysis=None  # Physical fitness agent doesn't provide nutrition analysis
        )
    except Exception as e:
        # Log error and end trace
        tracer.end_trace(
            response=f"Error: {str(e)}",
            warnings=None,
            success=False,
            error=str(e)
        )
        raise


@router.post("/nutrition/chat", response_model=AgentChatResponse)
async def chat_with_nutrition_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Nutrition Agent.
    Supports both text queries and image-based food analysis.
    If image_base64 is provided, the agent will analyze the food image.
    """
    # Create tracer for observability
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="nutrition",
        user_id=current_user.id,
        query=request.message,
        image_base64=request.image_base64
    )
    
    try:
        # Initialize agent for current user with tracer
        agent = NutritionAgent(user_id=current_user.id, db=db, tracer=tracer)
        
        # Get response (handles both text and image)
        result = await agent.recommend_meal(
            user_input=request.message,
            image_base64=request.image_base64
        )
        
        # End trace
        tracer.end_trace(
            response=result["response"],
            warnings=result.get("warnings"),
            success=True
        )
        
        return AgentChatResponse(
            response=result["response"],
            warnings=result.get("warnings"),
            nutrition_analysis=result.get("nutrition_analysis")  # Nutrition agent provides structured analysis
        )
    except Exception as e:
        # Log error and end trace
        tracer.end_trace(
            response=f"Error: {str(e)}",
            warnings=None,
            success=False,
            error=str(e)
        )
        raise


@router.post("/mental-fitness/chat", response_model=AgentChatResponse)
async def chat_with_mental_fitness_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Mental Fitness Agent.
    Provides mindfulness, stress management, and mental wellness guidance.
    """
    # Create tracer for observability
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="mental-fitness",
        user_id=current_user.id,
        query=request.message,
        image_base64=request.image_base64
    )
    
    try:
        # Initialize agent for current user with tracer
        agent = MentalFitnessAgent(user_id=current_user.id, db=db, tracer=tracer)
        
        # Get response
        result = await agent.recommend_practice(request.message)
        
        # End trace
        tracer.end_trace(
            response=result["response"],
            warnings=result.get("warnings"),
            success=True
        )
        
        return AgentChatResponse(
            response=result["response"],
            warnings=result.get("warnings"),
            nutrition_analysis=None  # Mental fitness agent doesn't provide nutrition analysis
        )
    except Exception as e:
        # Log error and end trace
        tracer.end_trace(
            response=f"Error: {str(e)}",
            warnings=None,
            success=False,
            error=str(e)
        )
        raise


@router.post("/coordinator/chat/stream")
async def chat_with_coordinator_agent_stream(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Coordinator Agent (streaming version).
    Streams step updates in real-time as they happen, then streams final response.
    Uses Server-Sent Events (SSE) format.
    """
    # Create tracer for observability
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="coordinator",
        user_id=current_user.id,
        query=request.message,
        image_base64=request.image_base64
    )
    
    async def generate():
        try:
            # Initialize coordinator agent for current user with tracer
            agent = CoordinatorAgent(user_id=current_user.id, db=db, tracer=tracer)
            
            response_data = None
            
            # Stream query processing
            async for item in agent.route_query_stream(
                user_query=request.message,
                image_base64=request.image_base64
            ):
                # Log steps to tracer
                if item.get("type") == "step" and tracer:
                    tracer.log_step(item.get("data", ""))
                
                # Capture final response
                if item.get("type") == "response":
                    response_data = item.get("data", {})
                
                # Format as SSE: data: {json}\n\n
                yield f"data: {json.dumps(item)}\n\n"
            
            # End trace after streaming completes
            if response_data:
                tracer.end_trace(
                    response=response_data.get("response", ""),
                    warnings=response_data.get("warnings"),
                    success=True
                )
            else:
                tracer.end_trace(
                    response="Stream completed",
                    warnings=None,
                    success=True
                )
                
        except Exception as e:
            # Log error and end trace
            tracer.end_trace(
                response=f"Error: {str(e)}",
                warnings=None,
                success=False,
                error=str(e)
            )
            # Send error as SSE event
            error_event = {
                "type": "error",
                "data": {"error": f"Coordinator agent error: {str(e)}"}
            }
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering in nginx
        }
    )


@router.post("/coordinator/chat", response_model=AgentChatResponse)
async def chat_with_coordinator_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Coordinator Agent (non-streaming version for backward compatibility).
    Routes queries to appropriate agents or creates holistic plans combining all three domains.
    """
    # Create tracer for observability
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="coordinator",
        user_id=current_user.id,
        query=request.message,
        image_base64=request.image_base64
    )
    
    try:
        # Initialize coordinator agent for current user with tracer
        agent = CoordinatorAgent(user_id=current_user.id, db=db, tracer=tracer)
        
        # Route query or create holistic plan
        result = await agent.route_query(
            user_query=request.message,
            image_base64=request.image_base64
        )
        
        # Log steps to tracer
        if result.get("steps") and tracer:
            for step in result.get("steps", []):
                tracer.log_step(step)
        
        # End trace
        tracer.end_trace(
            response=result["response"],
            warnings=result.get("warnings"),
            success=True
        )
        
        return AgentChatResponse(
            response=result["response"],
            warnings=result.get("warnings"),
            nutrition_analysis=result.get("nutrition_analysis"),
            steps=result.get("steps")
        )
    except Exception as e:
        # Log error and end trace
        tracer.end_trace(
            response=f"Error: {str(e)}",
            warnings=None,
            success=False,
            error=str(e)
        )
        raise


@router.get("/execution-logs", response_model=AgentExecutionLogsListResponse)
async def get_agent_execution_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    agent_type: Optional[str] = Query(default=None, description="Filter by agent type (coordinator, physical-fitness, nutrition, mental-fitness)"),
    limit: Optional[int] = Query(default=50, ge=1, le=100, description="Maximum number of logs to return"),
    offset: Optional[int] = Query(default=0, ge=0, description="Number of logs to skip")
):
    """
    Get agent execution logs for the current user.
    Useful for debugging, performance monitoring, and observability.
    """
    try:
        # Query agent execution logs for the current user
        logs_query = db.query(AgentExecutionLog).filter(
            AgentExecutionLog.user_id == current_user.id
        )
        
        # Filter by agent type if provided
        if agent_type:
            logs_query = logs_query.filter(AgentExecutionLog.agent_type == agent_type)
        
        # Order by most recent first
        logs_query = logs_query.order_by(desc(AgentExecutionLog.created_at))
        
        # Get total count
        total = logs_query.count()
        
        # Apply pagination
        logs = logs_query.offset(offset).limit(limit).all()
        
        return AgentExecutionLogsListResponse(
            logs=logs,
            total=total,
            page=(offset // limit) + 1 if limit > 0 else 1,
            page_size=limit
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve agent execution logs: {str(e)}"
        )

