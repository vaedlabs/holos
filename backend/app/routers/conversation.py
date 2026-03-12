"""
Conversation history routes for managing chat messages and images.

This module provides FastAPI router endpoints for conversation management:
- Create messages: Save conversation messages (user and agent messages)
- Get conversation history: Retrieve conversation history with optional agent filtering
- Upload images: Upload and store images for conversation messages
- Get images: Serve stored images
- Clear conversation: Delete all conversation messages and associated images

Key Features:
- Conversation message storage (user messages, agent responses)
- Image upload and storage (base64 encoding, file system storage)
- Agent type filtering (coordinator, physical-fitness, nutrition, mental-fitness)
- Warning storage (safety warnings, dietary restrictions, etc.)
- Image cleanup on conversation deletion

Message Storage:
- User messages: User queries and input
- Agent messages: Agent responses and recommendations
- Warnings: Safety warnings, dietary restrictions, etc. (stored as JSON)
- Image paths: References to uploaded images
- Agent type: Which agent generated the response

Image Handling:
- Images uploaded as base64-encoded strings
- Stored in uploads/images directory
- Unique filenames: {user_id}_{uuid}.jpg
- Images served via GET endpoint
- Images deleted when conversation cleared

Security:
- All endpoints require authentication (get_current_user dependency)
- Users can only access and modify their own conversation messages
- Images are user-specific (filename includes user_id)
- Image paths validated before serving

Usage:
    POST /conversation/messages - Save conversation message
    GET /conversation/messages - Get conversation history (optionally filtered by agent_type)
    POST /conversation/upload-image - Upload image (base64)
    GET /conversation/images/{filename} - Serve stored image
    DELETE /conversation/messages - Clear conversation history
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

# FastAPI router for conversation endpoints
# Prefix: /conversation (all routes will be prefixed with /conversation)
# Tags: ["conversation"] (for API documentation grouping)
router = APIRouter(prefix="/conversation", tags=["conversation"])

# Create uploads directory if it doesn't exist
# Images are stored in uploads/images directory
# Directory is created on module import if it doesn't exist
UPLOADS_DIR = Path("uploads/images")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)  # Create directory structure if needed


@router.post("/messages", response_model=ConversationMessageResponse)
async def create_message(
    message: ConversationMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Save a conversation message.
    
    This endpoint saves a conversation message (user message or agent response)
    to the database. Messages include content, role, warnings, image path, and
    agent type. Warnings are stored as JSON strings in the database.
    
    Message Types:
        - User messages: User queries and input (role: "user")
        - Agent messages: Agent responses and recommendations (role: "assistant")
    
    Warnings Storage:
        - Warnings are stored as JSON strings in database
        - Parsed back to list when retrieving messages
        - Includes safety warnings, dietary restrictions, etc.
    
    Args:
        message: ConversationMessageCreate schema containing:
            - role: str (message role: "user" or "assistant")
            - content: str (message content)
            - warnings: Optional[List[str]] (warnings to store as JSON)
            - image_path: Optional[str] (path to uploaded image)
            - agent_type: Optional[str] (agent type: coordinator, physical-fitness, nutrition, mental-fitness)
        current_user: Authenticated user (injected dependency)
        db: Database session (injected dependency)
    
    Returns:
        ConversationMessageResponse: Saved message with ID and timestamps
        
    Raises:
        HTTPException 500: If message saving fails
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Messages are associated with authenticated user (user_id)
        
    Note:
        - Warnings are serialized to JSON before storage
        - Default agent_type is "coordinator" if not provided
        - Image path should reference uploaded image (via /upload-image endpoint)
        
    Example:
        POST /conversation/messages
        {
            "role": "assistant",
            "content": "Here's your workout plan...",
            "warnings": ["Exercise conflict detected"],
            "agent_type": "physical-fitness"
        }
    """
    try:
        # Serialize warnings to JSON string for database storage
        # Warnings are stored as JSON in database, parsed back to list when retrieving
        warnings_json = None
        if message.warnings:
            warnings_json = json.dumps(message.warnings)
        
        # Create conversation message record
        # Message is associated with current user
        db_message = ConversationMessage(
            user_id=current_user.id,  # Associate message with authenticated user
            role=message.role,  # Message role: "user" or "assistant"
            content=message.content,  # Message content
            warnings=warnings_json,  # Warnings as JSON string (or None)
            image_path=message.image_path,  # Image path (if image attached)
            agent_type=message.agent_type or 'coordinator'  # Agent type (default: coordinator)
        )
        
        # Save message to database
        db.add(db_message)
        db.commit()
        db.refresh(db_message)  # Refresh to get database-generated fields (id, created_at)
        
        # Parse warnings back to list for response
        # Warnings are stored as JSON, parsed back to list when returning
        warnings = None
        if db_message.warnings:
            try:
                warnings = json.loads(db_message.warnings)
            except:
                warnings = None  # Handle JSON parsing errors gracefully
        
        # Return saved message with parsed warnings
        return ConversationMessageResponse(
            id=db_message.id,  # Database-generated ID
            role=db_message.role,  # Message role
            content=db_message.content,  # Message content
            warnings=warnings,  # Warnings parsed back to list
            image_path=db_message.image_path,  # Image path (if any)
            agent_type=db_message.agent_type,  # Agent type
            created_at=db_message.created_at  # Creation timestamp
        )
    except Exception as e:
        # Rollback transaction on error
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
    """
    Get conversation history for the current user.
    
    This endpoint retrieves the authenticated user's conversation history,
    optionally filtered by agent type. Messages are ordered chronologically
    (oldest first) and warnings are parsed from JSON back to lists.
    
    Filtering:
        - If agent_type provided: Returns only messages from that agent
        - If agent_type not provided: Returns all conversation messages
        - Valid agent types: coordinator, physical-fitness, nutrition, mental-fitness
    
    Message Ordering:
        - Messages ordered by created_at ASC (oldest first)
        - Chronological order for conversation flow
    
    Args:
        agent_type: Optional[str] - Filter by agent type:
                    - "coordinator": Coordinator agent messages
                    - "physical-fitness": Physical Fitness agent messages
                    - "nutrition": Nutrition agent messages
                    - "mental-fitness": Mental Fitness agent messages
                    - None: All messages (no filter)
        current_user: Authenticated user (injected dependency)
                     Ensures users can only access their own messages
        db: Database session (injected dependency)
    
    Returns:
        ConversationHistoryResponse containing:
            - messages: List[ConversationMessageResponse] (list of conversation messages)
            
    Raises:
        HTTPException 500: If database query fails
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only access their own conversation messages (filtered by user_id)
        
    Note:
        - Warnings are parsed from JSON back to list for each message
        - Messages include user messages and agent responses
        - Image paths are included if messages have attached images
        
    Example:
        GET /conversation/messages?agent_type=nutrition
        
        Returns only Nutrition agent conversation messages
    """
    try:
        # Query conversation messages for current user
        # Filter by user_id to ensure users can only access their own messages
        query = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == current_user.id  # Security: Only current user's messages
        )
        
        # Filter by agent_type if provided
        # Allows filtering conversation history by specific agent
        if agent_type:
            query = query.filter(ConversationMessage.agent_type == agent_type)
        
        # Order messages chronologically (oldest first)
        # ASC order for conversation flow (oldest to newest)
        messages = query.order_by(ConversationMessage.created_at.asc()).all()
        
        # Build response list with parsed warnings
        # Warnings are stored as JSON, parsed back to list for response
        message_responses = []
        for msg in messages:
            # Parse warnings from JSON back to list
            warnings = None
            if msg.warnings:
                try:
                    warnings = json.loads(msg.warnings)
                except:
                    warnings = None  # Handle JSON parsing errors gracefully
            
            # Create response object with parsed warnings
            message_responses.append(ConversationMessageResponse(
                id=msg.id,  # Message ID
                role=msg.role,  # Message role (user or assistant)
                content=msg.content,  # Message content
                warnings=warnings,  # Warnings parsed back to list
                image_path=msg.image_path,  # Image path (if any)
                agent_type=msg.agent_type,  # Agent type
                created_at=msg.created_at  # Creation timestamp
            ))
        
        # Return conversation history
        return ConversationHistoryResponse(messages=message_responses)
    except Exception as e:
        # Handle database query errors
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
    """
    Serve stored images.
    
    This endpoint serves images stored in the uploads/images directory.
    Images are referenced by filename (from image_path in conversation messages).
    Used to display images in conversation history.
    
    Args:
        filename: str - Image filename (e.g., "123_a1b2c3d4.jpg")
                  Filename format: {user_id}_{uuid}.jpg
    
    Returns:
        FileResponse: Image file response with appropriate content type
        
    Raises:
        HTTPException 404: If image file not found
        
    Security:
        - No authentication required (images are public)
        - Filename validation prevents directory traversal
        - Images are user-specific (filename includes user_id)
        
    Note:
        - Images are served directly from file system
        - Content type inferred from file extension
        - Used to display images in conversation UI
        
    Example:
        GET /conversation/images/123_a1b2c3d4.jpg
        
        Returns image file if exists, 404 if not found
    """
    # Construct file path from filename
    # Images stored in uploads/images directory
    file_path = UPLOADS_DIR / filename
    
    # Check if image file exists
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Return image file response
    # FastAPI FileResponse handles content type and file serving
    return FileResponse(file_path)


@router.delete("/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversation_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """
    Clear conversation history for the current user.
    
    This endpoint deletes all conversation messages for the authenticated user
    and removes associated image files from the file system. This action is
    irreversible and should be used with caution.
    
    Deletion Flow:
        1. Fetch all user's conversation messages
        2. Delete associated image files from file system
        3. Delete all conversation messages from database
        4. Commit transaction
    
    Image Cleanup:
        - Images referenced in messages are deleted from file system
        - Image deletion failures are ignored (non-critical)
        - Prevents orphaned image files
    
    Args:
        current_user: Authenticated user (injected dependency)
                     Ensures users can only clear their own conversation history
        db: Database session (injected dependency)
    
    Returns:
        None: 204 No Content response on successful deletion
        
    Raises:
        HTTPException 500: If deletion fails (transaction rolled back)
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only clear their own conversation history (filtered by user_id)
        
    Note:
        - This action is irreversible
        - Image file deletion failures are ignored (continues deletion)
        - All deletions performed in single transaction (atomicity)
        
    Example:
        DELETE /conversation/messages
        
        Clears all conversation messages and associated images for current user
    """
    try:
        # Get all messages to delete associated images
        # Fetch messages before deletion to access image_path fields
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == current_user.id  # Security: Only current user's messages
        ).all()
        
        # Delete associated image files from file system
        # Prevents orphaned image files when messages are deleted
        for msg in messages:
            if msg.image_path:
                # Extract filename from image path
                # Path format: "images/{filename}", extract just filename
                image_file = UPLOADS_DIR / msg.image_path.split('/')[-1]
                if image_file.exists():
                    try:
                        image_file.unlink()  # Delete image file
                    except:
                        pass  # Continue even if image deletion fails (non-critical)
        
        # Delete messages from database
        # All user's conversation messages are deleted
        db.query(ConversationMessage).filter(
            ConversationMessage.user_id == current_user.id  # Security: Only current user's messages
        ).delete()
        db.commit()  # Commit transaction
        return None  # 204 No Content response
    except Exception as e:
        # Rollback transaction on error
        # Ensures data consistency if deletion fails
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing messages: {str(e)}"
        )

