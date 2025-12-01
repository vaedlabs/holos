"""
Conversation history routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import json
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.models.conversation_message import ConversationMessage
from app.schemas.conversation import (
    ConversationMessageCreate,
    ConversationMessageResponse,
    ConversationHistoryResponse
)

router = APIRouter(prefix="/conversation", tags=["conversation"])


@router.post("/messages", response_model=ConversationMessageResponse)
async def create_message(
    message: ConversationMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Save a conversation message"""
    try:
        warnings_json = None
        if message.warnings:
            warnings_json = json.dumps(message.warnings)
        
        db_message = ConversationMessage(
            user_id=current_user.id,
            role=message.role,
            content=message.content,
            warnings=warnings_json
        )
        
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        # Parse warnings back to list
        warnings = None
        if db_message.warnings:
            try:
                warnings = json.loads(db_message.warnings)
            except:
                warnings = None
        
        return ConversationMessageResponse(
            id=db_message.id,
            role=db_message.role,
            content=db_message.content,
            warnings=warnings,
            created_at=db_message.created_at
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving message: {str(e)}"
        )


@router.get("/messages", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Get conversation history for the current user"""
    try:
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == current_user.id
        ).order_by(ConversationMessage.created_at.asc()).all()
        
        message_responses = []
        for msg in messages:
            warnings = None
            if msg.warnings:
                try:
                    warnings = json.loads(msg.warnings)
                except:
                    warnings = None
            
            message_responses.append(ConversationMessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                warnings=warnings,
                created_at=msg.created_at
            ))
        
        return ConversationHistoryResponse(messages=message_responses)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching messages: {str(e)}"
        )


@router.delete("/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversation_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Clear conversation history for the current user"""
    try:
        db.query(ConversationMessage).filter(
            ConversationMessage.user_id == current_user.id
        ).delete()
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing messages: {str(e)}"
        )

