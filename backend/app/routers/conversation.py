"""
Conversation history routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import os
import uuid
import base64
from pathlib import Path
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.models.conversation_message import ConversationMessage
from app.schemas.conversation import (
    ConversationMessageCreate,
    ConversationMessageResponse,
    ConversationHistoryResponse
)

router = APIRouter(prefix="/conversation", tags=["conversation"])

# Create uploads directory if it doesn't exist
UPLOADS_DIR = Path("uploads/images")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


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
            warnings=warnings_json,
            image_path=message.image_path,
            agent_type=message.agent_type or 'coordinator'
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
            image_path=db_message.image_path,
            agent_type=db_message.agent_type,
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
    agent_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Get conversation history for the current user, optionally filtered by agent_type"""
    try:
        query = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == current_user.id
        )
        
        # Filter by agent_type if provided
        if agent_type:
            query = query.filter(ConversationMessage.agent_type == agent_type)
        
        messages = query.order_by(ConversationMessage.created_at.asc()).all()
        
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
                image_path=msg.image_path,
                agent_type=msg.agent_type,
                created_at=msg.created_at
            ))
        
        return ConversationHistoryResponse(messages=message_responses)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching messages: {str(e)}"
        )


@router.post("/upload-image")
async def upload_image(
    image_base64: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Upload and store an image, return the path"""
    try:
        # Decode base64 image
        try:
            # Remove data URL prefix if present
            if ',' in image_base64:
                image_base64 = image_base64.split(',')[1]
            
            image_data = base64.b64decode(image_base64)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid base64 image data: {str(e)}"
            )
        
        # Generate unique filename
        filename = f"{current_user.id}_{uuid.uuid4().hex[:8]}.jpg"
        file_path = UPLOADS_DIR / filename
        
        # Save image
        with open(file_path, 'wb') as f:
            f.write(image_data)
        
        # Return relative path for storage in DB
        relative_path = f"images/{filename}"
        
        return {"image_path": relative_path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading image: {str(e)}"
        )


@router.get("/images/{filename}")
async def get_image(filename: str):
    """Serve stored images"""
    file_path = UPLOADS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(file_path)


@router.delete("/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversation_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Clear conversation history for the current user"""
    try:
        # Get all messages to delete associated images
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == current_user.id
        ).all()
        
        # Delete associated image files
        for msg in messages:
            if msg.image_path:
                image_file = UPLOADS_DIR / msg.image_path.split('/')[-1]
                if image_file.exists():
                    try:
                        image_file.unlink()
                    except:
                        pass  # Continue even if image deletion fails
        
        # Delete messages
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

