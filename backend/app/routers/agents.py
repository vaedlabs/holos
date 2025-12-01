"""
Agent interaction routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.agents.physical_fitness_agent import PhysicalFitnessAgent
from app.agents.nutrition_agent import NutritionAgent
from app.agents.mental_fitness_agent import MentalFitnessAgent
from app.agents.coordinator_agent import CoordinatorAgent
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
            warnings=result.get("warnings"),
            nutrition_analysis=None  # Physical fitness agent doesn't provide nutrition analysis
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {str(e)}"
        )


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
    try:
        # Initialize agent for current user
        agent = NutritionAgent(user_id=current_user.id, db=db)
        
        # Get response (handles both text and image)
        result = await agent.recommend_meal(
            user_input=request.message,
            image_base64=request.image_base64
        )
        
        return AgentChatResponse(
            response=result["response"],
            warnings=result.get("warnings"),
            nutrition_analysis=result.get("nutrition_analysis")  # Nutrition agent provides structured analysis
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {str(e)}"
        )


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
    try:
        # Initialize agent for current user
        agent = MentalFitnessAgent(user_id=current_user.id, db=db)
        
        # Get response
        result = await agent.recommend_practice(request.message)
        
        return AgentChatResponse(
            response=result["response"],
            warnings=result.get("warnings"),
            nutrition_analysis=None  # Mental fitness agent doesn't provide nutrition analysis
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {str(e)}"
        )


@router.post("/coordinator/chat", response_model=AgentChatResponse)
async def chat_with_coordinator_agent(
    request: AgentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Chat with the Coordinator Agent.
    Routes queries to appropriate agents or creates holistic plans combining all three domains.
    """
    try:
        # Initialize coordinator agent for current user
        agent = CoordinatorAgent(user_id=current_user.id, db=db)
        
        # Route query or create holistic plan
        result = await agent.route_query(
            user_query=request.message,
            image_base64=request.image_base64
        )
        
        return AgentChatResponse(
            response=result["response"],
            warnings=result.get("warnings"),
            nutrition_analysis=result.get("nutrition_analysis")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Coordinator agent error: {str(e)}"
        )

