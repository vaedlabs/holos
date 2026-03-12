"""
Agent interaction routes for AI agent chat endpoints and execution logs.

This module provides FastAPI router endpoints for interacting with AI agents:
- Physical Fitness Agent: Exercise recommendations and workout planning
- Nutrition Agent: Meal recommendations and food image analysis
- Mental Fitness Agent: Mental wellness guidance and mindfulness practices
- Coordinator Agent: Query routing and holistic plan creation (streaming and non-streaming)

Key Features:
- Agent chat endpoints with tracer integration for observability
- Streaming support (Server-Sent Events) for real-time updates
- Execution logs endpoint for debugging and monitoring
- Error handling with tracer logging
- Degraded mode tracking (model fallback information)

Streaming Implementation:
- Uses Server-Sent Events (SSE) for real-time step updates
- Coordinator agent supports streaming for better UX
- Step updates logged to tracer for observability
- Final response streamed after all steps complete

Tracer Integration:
- All endpoints create AgentTracer instances for observability
- Traces include agent type, user ID, query, and image (if provided)
- Tool calls, token usage, and performance metrics tracked
- Traces persisted to database for analysis

Security:
- All endpoints require authentication (get_current_user dependency)
- Users can only access their own execution logs
- Agent initialization uses authenticated user ID

Usage:
    POST /agents/physical-fitness/chat - Chat with Physical Fitness Agent
    POST /agents/nutrition/chat - Chat with Nutrition Agent (supports images)
    POST /agents/mental-fitness/chat - Chat with Mental Fitness Agent
    POST /agents/coordinator/chat/stream - Coordinator Agent (streaming)
    POST /agents/coordinator/chat - Coordinator Agent (non-streaming)
    GET /agents/execution-logs - Get execution logs with filtering and pagination
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

# FastAPI router for agent interaction endpoints
# Prefix: /agents (all routes will be prefixed with /agents)
# Tags: ["agents"] (for API documentation grouping)
router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/physical-fitness/chat", response_model=AgentChatResponse)
async def chat_with_physical_fitness_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Physical Fitness Agent.
    
    This endpoint allows users to interact with the Physical Fitness Agent for
    exercise recommendations, workout planning, and fitness guidance. The agent
    checks medical history and preferences before responding to ensure safe,
    personalized recommendations.
    
    Agent Capabilities:
        - Exercise recommendations based on user preferences and medical history
        - Workout planning (calisthenics, weight lifting, cardio, HIIT, yoga, Pilates)
        - Form and technique guidance
        - Progression strategies
        - Medical safety checks (exercise conflict detection)
    
    Args:
        request: AgentChatRequest containing:
            - message: str (user's query requesting fitness guidance)
            - image_base64: Optional[str] (not used by Physical Fitness Agent)
        current_user: Authenticated user (injected dependency)
        db: Database session (injected dependency)
    
    Returns:
        AgentChatResponse containing:
            - response: str (agent's exercise recommendation)
            - warnings: List[str] or None (safety warnings if conflicts detected)
            - nutrition_analysis: None (not provided by Physical Fitness Agent)
            - degraded: bool (True if fallback model was used)
            - fallback_info: Dict or None (fallback model information)
            
    Observability:
        - Creates AgentTracer for execution tracking
        - Logs agent type, user ID, query, and response
        - Tracks tool calls, token usage, and performance metrics
        - Persists trace to database for analysis
        
    Error Handling:
        - Errors are logged to tracer before re-raising
        - Trace marked as failed with error details
        
    Example:
        POST /agents/physical-fitness/chat
        {
            "message": "What exercises build chest?"
        }
    """
    # Create tracer for observability
    # Tracer tracks agent execution, tool calls, token usage, and performance
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="physical-fitness",  # Agent type identifier
        user_id=current_user.id,  # User ID for user-specific tracking
        query=request.message,  # User's query
        image_base64=request.image_base64  # Image (not used by Physical Fitness Agent)
    )
    
    try:
        # Initialize agent for current user with tracer
        # Agent receives user context (medical history, preferences) automatically
        agent = PhysicalFitnessAgent(user_id=current_user.id, db=db, tracer=tracer)
        
        # Get response with potential warnings
        # Agent checks medical history and preferences before responding
        # Returns response with safety warnings if conflicts detected
        result = await agent.recommend_exercise(request.message)
        
        # End trace with successful completion
        # Logs response, warnings, and marks trace as successful
        tracer.end_trace(
            response=result["response"],  # Agent's response
            warnings=result.get("warnings"),  # Safety warnings (if any)
            success=True  # Mark trace as successful
        )
        
        # Return response with all metadata
        return AgentChatResponse(
            response=result["response"],  # Agent's exercise recommendation
            warnings=result.get("warnings"),  # Safety warnings (if conflicts detected)
            nutrition_analysis=None,  # Physical fitness agent doesn't provide nutrition analysis
            degraded=result.get("degraded", False),  # P0.3: Include degraded flag (True if fallback model used)
            fallback_info=result.get("fallback_info")  # P0.3: Include fallback info (model fallback details)
        )
    except Exception as e:
        # Log error and end trace
        # Errors are logged to tracer before re-raising for proper observability
        tracer.end_trace(
            response=f"Error: {str(e)}",  # Error message
            warnings=None,  # No warnings on error
            success=False,  # Mark trace as failed
            error=str(e)  # Error details
        )
        raise  # Re-raise exception for FastAPI error handling


@router.post("/nutrition/chat", response_model=AgentChatResponse)
async def chat_with_nutrition_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Nutrition Agent.
    
    This endpoint allows users to interact with the Nutrition Agent for meal
    recommendations, dietary guidance, and food image analysis. The agent
    supports both text queries and image-based food analysis using Google Gemini Vision.
    
    Agent Capabilities:
        - Meal recommendations based on dietary preferences and restrictions
        - Food image analysis (calories, macronutrients, portion estimation)
        - Multi-cuisine recognition (Asian, Mediterranean, American, Latin, etc.)
        - Dietary restriction conflict detection
        - Nutritional calculation (protein, carbohydrates, fats)
    
    Image Analysis:
        - If image_base64 is provided, agent analyzes food image using Gemini Vision
        - Extracts dish name, items, portion sizes, calories, and macronutrients
        - Provides structured nutrition_analysis response
        - Automatically logs meals to nutrition log if user intent indicates logging
    
    Args:
        request: AgentChatRequest containing:
            - message: str (user's query requesting nutrition guidance)
            - image_base64: Optional[str] (base64-encoded food image for analysis)
        current_user: Authenticated user (injected dependency)
        db: Database session (injected dependency)
    
    Returns:
        AgentChatResponse containing:
            - response: str (agent's meal recommendation or analysis)
            - warnings: List[str] or None (dietary restriction warnings if conflicts detected)
            - nutrition_analysis: Dict or None (structured nutrition data if image provided)
            - degraded: bool (True if fallback model was used)
            - fallback_info: Dict or None (fallback model information)
            
    Observability:
        - Creates AgentTracer for execution tracking
        - Logs agent type, user ID, query, image (if provided), and response
        - Tracks tool calls, token usage, and performance metrics
        - Persists trace to database for analysis
        
    Error Handling:
        - Errors are logged to tracer before re-raising
        - Trace marked as failed with error details
        
    Example:
        POST /agents/nutrition/chat
        {
            "message": "How many calories are in grilled chicken?",
            "image_base64": null
        }
        
        POST /agents/nutrition/chat (with image)
        {
            "message": "What's in this meal?",
            "image_base64": "data:image/jpeg;base64,..."
        }
    """
    # Create tracer for observability
    # Tracer tracks agent execution, tool calls, token usage, and performance
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="nutrition",  # Agent type identifier
        user_id=current_user.id,  # User ID for user-specific tracking
        query=request.message,  # User's query
        image_base64=request.image_base64  # Food image (if provided for analysis)
    )
    
    try:
        # Get shared user context (medical history + preferences) with caching
        # ContextManager provides cached context to avoid redundant database queries
        from app.services.context_manager import context_manager
        shared_context = context_manager.get_user_context(
            user_id=current_user.id,
            db=db,
            force_refresh=False
        )
        
        # Initialize agent for current user with tracer and shared context
        # Agent receives user context (dietary preferences, restrictions) automatically
        agent = NutritionAgent(
            user_id=current_user.id, 
            db=db, 
            tracer=tracer,
            shared_context=shared_context  # Pass shared context with user preferences
        )
        
        # Get response (handles both text and image)
        # If image_base64 provided, agent analyzes food image using Gemini Vision
        # Otherwise, provides text-based meal recommendations
        result = await agent.recommend_meal(
            user_input=request.message,  # User's query
            image_base64=request.image_base64  # Food image (if provided)
        )
        
        # End trace with successful completion
        # Logs response, warnings, and marks trace as successful
        tracer.end_trace(
            response=result["response"],  # Agent's response
            warnings=result.get("warnings"),  # Dietary restriction warnings (if any)
            success=True  # Mark trace as successful
        )
        
        # Return response with all metadata
        return AgentChatResponse(
            response=result["response"],  # Agent's meal recommendation or analysis
            warnings=result.get("warnings"),  # Dietary restriction warnings (if conflicts detected)
            nutrition_analysis=result.get("nutrition_analysis"),  # Nutrition agent provides structured analysis (if image provided)
            degraded=result.get("degraded", False),  # P0.3: Include degraded flag (True if fallback model used)
            fallback_info=result.get("fallback_info")  # P0.3: Include fallback info (model fallback details)
        )
    except Exception as e:
        # Log error and end trace
        # Errors are logged to tracer before re-raising for proper observability
        tracer.end_trace(
            response=f"Error: {str(e)}",  # Error message
            warnings=None,  # No warnings on error
            success=False,  # Mark trace as failed
            error=str(e)  # Error details
        )
        raise  # Re-raise exception for FastAPI error handling


@router.post("/mental-fitness/chat", response_model=AgentChatResponse)
async def chat_with_mental_fitness_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Mental Fitness Agent.
    
    This endpoint allows users to interact with the Mental Fitness Agent for
    mental wellness guidance, mindfulness practices, stress management, and
    mental health support. The agent considers medical history (especially
    mental health conditions) before responding.
    
    Agent Capabilities:
        - Mental wellness recommendations (meditation, mindfulness, stress management)
        - Activity recommendations (breathing exercises, journaling, yoga)
        - Mental fitness logging
        - Wellness plan creation
        - Medical history integration (especially important for mental health)
    
    Focus Areas:
        - Stress management
        - Anxiety and mood support
        - Sleep improvement
        - Focus and concentration
        - Mindfulness practices
        - Mental wellness activities
    
    Args:
        request: AgentChatRequest containing:
            - message: str (user's query requesting mental wellness guidance)
            - image_base64: Optional[str] (not used by Mental Fitness Agent)
        current_user: Authenticated user (injected dependency)
        db: Database session (injected dependency)
    
    Returns:
        AgentChatResponse containing:
            - response: str (agent's mental wellness recommendation)
            - warnings: List[str] or None (warnings if any)
            - nutrition_analysis: None (not provided by Mental Fitness Agent)
            - degraded: bool (True if fallback model was used)
            - fallback_info: Dict or None (fallback model information)
            
    Observability:
        - Creates AgentTracer for execution tracking
        - Logs agent type, user ID, query, and response
        - Tracks tool calls, token usage, and performance metrics
        - Persists trace to database for analysis
        
    Error Handling:
        - Errors are logged to tracer before re-raising
        - Trace marked as failed with error details
        
    Example:
        POST /agents/mental-fitness/chat
        {
            "message": "Help me manage stress"
        }
    """
    # Create tracer for observability
    # Tracer tracks agent execution, tool calls, token usage, and performance
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="mental-fitness",  # Agent type identifier
        user_id=current_user.id,  # User ID for user-specific tracking
        query=request.message,  # User's query
        image_base64=request.image_base64  # Image (not used by Mental Fitness Agent)
    )
    
    try:
        # Initialize agent for current user with tracer
        # Agent receives user context (medical history, preferences) automatically
        agent = MentalFitnessAgent(user_id=current_user.id, db=db, tracer=tracer)
        
        # Get response
        # Agent checks medical history (especially mental health conditions) before responding
        result = await agent.recommend_practice(request.message)
        
        # End trace with successful completion
        # Logs response, warnings, and marks trace as successful
        tracer.end_trace(
            response=result["response"],  # Agent's response
            warnings=result.get("warnings"),  # Warnings (if any)
            success=True  # Mark trace as successful
        )
        
        # Return response with all metadata
        return AgentChatResponse(
            response=result["response"],  # Agent's mental wellness recommendation
            warnings=result.get("warnings"),  # Warnings (if any)
            nutrition_analysis=None,  # Mental fitness agent doesn't provide nutrition analysis
            degraded=result.get("degraded", False),  # P0.3: Include degraded flag (True if fallback model used)
            fallback_info=result.get("fallback_info")  # P0.3: Include fallback info (model fallback details)
        )
    except Exception as e:
        # Log error and end trace
        # Errors are logged to tracer before re-raising for proper observability
        tracer.end_trace(
            response=f"Error: {str(e)}",  # Error message
            warnings=None,  # No warnings on error
            success=False,  # Mark trace as failed
            error=str(e)  # Error details
        )
        raise  # Re-raise exception for FastAPI error handling


@router.post("/coordinator/chat/stream")
async def chat_with_coordinator_agent_stream(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Coordinator Agent (streaming version).
    
    This endpoint provides real-time streaming updates using Server-Sent Events (SSE).
    The coordinator agent analyzes queries and routes to appropriate agents or creates
    holistic plans, streaming step updates as they happen.
    
    Streaming Flow:
        1. Analyze query and determine routing strategy
        2. Stream step updates ("Analyzing query...", "Routing to...", etc.)
        3. Execute agent(s) and stream progress
        4. Stream final response with complete result
    
    SSE Format:
        - Each event is formatted as: "data: {json}\n\n"
        - Event types: "step" (progress updates), "response" (final result), "error" (errors)
        - Client receives real-time updates for better UX
    
    Coordinator Capabilities:
        - Query routing: Routes to Physical Fitness, Nutrition, or Mental Fitness agents
        - Holistic planning: Creates comprehensive plans combining all three domains
        - Parallel execution: Executes multiple agents in parallel for holistic plans
        - Degraded mode: Handles partial failures gracefully
    
    Args:
        request: AgentChatRequest containing:
            - message: str (user's query requesting guidance or comprehensive planning)
            - image_base64: Optional[str] (base64-encoded image for nutrition analysis)
        current_user: Authenticated user (injected dependency)
        db: Database session (injected dependency)
    
    Returns:
        StreamingResponse: Server-Sent Events stream containing:
            - Step updates: {"type": "step", "data": "step text"}
            - Final response: {"type": "response", "data": {...}}
            - Errors: {"type": "error", "data": {"error": "..."}}
            
    SSE Headers:
        - Content-Type: text/event-stream
        - Cache-Control: no-cache (prevents caching)
        - Connection: keep-alive (maintains connection)
        - X-Accel-Buffering: no (disables nginx buffering)
        
    Observability:
        - Creates AgentTracer for execution tracking
        - Logs step updates to tracer in real-time
        - Logs final response and warnings after streaming completes
        - Persists trace to database for analysis
        
    Error Handling:
        - Errors are logged to tracer and sent as SSE error events
        - Stream continues even if errors occur (error event sent)
        
    Example:
        POST /agents/coordinator/chat/stream
        {
            "message": "Create a complete wellness plan",
            "image_base64": null
        }
        
        Client receives SSE events:
        data: {"type": "step", "data": "Analyzing your query..."}
        data: {"type": "step", "data": "Creating holistic plan..."}
        data: {"type": "response", "data": {...}}
    """
    # Create tracer for observability
    # Tracer tracks agent execution, tool calls, token usage, and performance
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="coordinator",  # Agent type identifier
        user_id=current_user.id,  # User ID for user-specific tracking
        query=request.message,  # User's query
        image_base64=request.image_base64  # Image (if provided for nutrition analysis)
    )
    
    # Async generator function for SSE streaming
    # Yields SSE-formatted events as they occur
    async def generate():
        try:
            # Initialize coordinator agent for current user with tracer
            # Agent receives user context (medical history, preferences) automatically
            agent = CoordinatorAgent(user_id=current_user.id, db=db, tracer=tracer)
            
            response_data = None  # Store final response data
            
            # Stream query processing
            # Coordinator routes query or creates holistic plan, yielding updates
            async for item in agent.route_query_stream(
                user_query=request.message,  # User's query
                image_base64=request.image_base64  # Image (if provided)
            ):
                # Log steps to tracer
                # Step updates are logged for observability
                if item.get("type") == "step" and tracer:
                    tracer.log_step(item.get("data", ""))
                
                # Capture final response
                # Store response data for tracer logging after streaming completes
                if item.get("type") == "response":
                    response_data = item.get("data", {})
                
                # Format as SSE: data: {json}\n\n
                # SSE format requires "data: " prefix and double newline
                yield f"data: {json.dumps(item)}\n\n"
            
            # End trace after streaming completes
            # Log final response and warnings to tracer
            if response_data:
                tracer.end_trace(
                    response=response_data.get("response", ""),  # Final response
                    warnings=response_data.get("warnings"),  # Warnings (if any)
                    success=True  # Mark trace as successful
                )
            else:
                # No response data (shouldn't happen, but handle gracefully)
                tracer.end_trace(
                    response="Stream completed",  # Fallback response
                    warnings=None,  # No warnings
                    success=True  # Mark trace as successful
                )
                
        except Exception as e:
            # Log error and end trace
            # Errors are logged to tracer before sending error event
            tracer.end_trace(
                response=f"Error: {str(e)}",  # Error message
                warnings=None,  # No warnings on error
                success=False,  # Mark trace as failed
                error=str(e)  # Error details
            )
            # Send error as SSE event
            # Client receives error event for proper error handling
            error_event = {
                "type": "error",
                "data": {"error": f"Coordinator agent error: {str(e)}"}
            }
            yield f"data: {json.dumps(error_event)}\n\n"
    
    # Return StreamingResponse with SSE format
    # Media type is text/event-stream for SSE
    # Headers configured for proper SSE behavior
    return StreamingResponse(
        generate(),  # Async generator function
        media_type="text/event-stream",  # SSE media type
        headers={
            "Cache-Control": "no-cache",  # Prevent caching of SSE stream
            "Connection": "keep-alive",  # Maintain connection for streaming
            "X-Accel-Buffering": "no"  # Disable buffering in nginx (important for real-time streaming)
        }
    )


@router.post("/coordinator/chat", response_model=AgentChatResponse)
async def chat_with_coordinator_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Coordinator Agent (non-streaming version).
    
    This endpoint provides a non-streaming version of the coordinator agent for
    backward compatibility. It routes queries to appropriate agents or creates
    holistic plans, returning the complete result after processing.
    
    Coordinator Capabilities:
        - Query routing: Routes to Physical Fitness, Nutrition, or Mental Fitness agents
        - Holistic planning: Creates comprehensive plans combining all three domains
        - Parallel execution: Executes multiple agents in parallel for holistic plans
        - Degraded mode: Handles partial failures gracefully
    
    Routing Logic:
        - Analyzes query using LLM to determine routing strategy
        - Routes to Physical Fitness for exercise/workout queries
        - Routes to Nutrition for food/diet queries
        - Routes to Mental Fitness for mindfulness/stress queries
        - Creates holistic plan for comprehensive planning requests
    
    Args:
        request: AgentChatRequest containing:
            - message: str (user's query requesting guidance or comprehensive planning)
            - image_base64: Optional[str] (base64-encoded image for nutrition analysis)
        current_user: Authenticated user (injected dependency)
        db: Database session (injected dependency)
    
    Returns:
        AgentChatResponse containing:
            - response: str (agent's response or synthesized holistic plan)
            - warnings: List[str] or None (warnings if any)
            - nutrition_analysis: Dict or None (nutrition analysis if routed to nutrition)
            - steps: List[str] (list of step updates for UI)
            - degraded: bool (True if degraded mode was used)
            - fallback_info: Dict or None (fallback info for degraded mode)
            
    Observability:
        - Creates AgentTracer for execution tracking
        - Logs step updates to tracer
        - Logs final response and warnings
        - Persists trace to database for analysis
        
    Error Handling:
        - Errors are logged to tracer before re-raising
        - Trace marked as failed with error details
        
    Example:
        POST /agents/coordinator/chat
        {
            "message": "Create a complete wellness plan",
            "image_base64": null
        }
    """
    # Create tracer for observability
    # Tracer tracks agent execution, tool calls, token usage, and performance
    tracer = AgentTracer(db=db)
    trace_id = tracer.start_trace(
        agent_type="coordinator",  # Agent type identifier
        user_id=current_user.id,  # User ID for user-specific tracking
        query=request.message,  # User's query
        image_base64=request.image_base64  # Image (if provided for nutrition analysis)
    )
    
    try:
        # Initialize coordinator agent for current user with tracer
        # Agent receives user context (medical history, preferences) automatically
        agent = CoordinatorAgent(user_id=current_user.id, db=db, tracer=tracer)
        
        # Route query or create holistic plan
        # Coordinator analyzes query and routes to appropriate agent or creates holistic plan
        result = await agent.route_query(
            user_query=request.message,  # User's query
            image_base64=request.image_base64  # Image (if provided)
        )
        
        # Log steps to tracer
        # Step updates are logged for observability (e.g., "Analyzing query...", "Routing to...")
        if result.get("steps") and tracer:
            for step in result.get("steps", []):
                tracer.log_step(step)
        
        # End trace with successful completion
        # Logs response, warnings, and marks trace as successful
        tracer.end_trace(
            response=result["response"],  # Final response
            warnings=result.get("warnings"),  # Warnings (if any)
            success=True  # Mark trace as successful
        )
        
        # Return response with all metadata
        return AgentChatResponse(
            response=result["response"],  # Agent's response or synthesized holistic plan
            warnings=result.get("warnings"),  # Warnings (if any)
            nutrition_analysis=result.get("nutrition_analysis"),  # Nutrition analysis (if routed to nutrition)
            steps=result.get("steps"),  # Step updates for UI
            degraded=result.get("degraded", False),  # P0.3: Include degraded flag (True if degraded mode)
            fallback_info=result.get("fallback_info")  # P0.3: Include fallback info (degraded mode details)
        )
    except Exception as e:
        # Log error and end trace
        # Errors are logged to tracer before re-raising for proper observability
        tracer.end_trace(
            response=f"Error: {str(e)}",  # Error message
            warnings=None,  # No warnings on error
            success=False,  # Mark trace as failed
            error=str(e)  # Error details
        )
        raise  # Re-raise exception for FastAPI error handling


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

