"""
Agent interaction routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.agents.physical_fitness_agent import PhysicalFitnessAgent
from app.schemas.agents import AgentChatRequest, AgentChatResponse

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
    try:
        # Initialize agent for current user
        agent = PhysicalFitnessAgent(user_id=current_user.id, db=db)
        
        # Get response with potential warnings
        result = await agent.recommend_exercise(request.message)
        
        return AgentChatResponse(
            response=result["response"],
            warnings=result.get("warnings")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {str(e)}"
        )

