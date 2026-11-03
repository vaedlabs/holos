"""
Conversation history routes for managing chat messages and images.

This module provides FastAPI router endpoints for conversation management. Messages
are saved by the chat stream (routers/chat.py, P4.7); photos arrive with the message:
- Get conversation history: Retrieve conversation history with optional agent filtering
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

import io
import json
import logging
import re
import warnings

from fastapi import APIRouter, Depends, HTTPException, Response, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Session

from app.dependencies import (
    get_current_user,
    get_database,
    get_engine,
    get_image_store,
    get_principal,
)
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.orchestration.principal import Principal
from app.storage.deletion import delete_or_queue
from app.storage.images import ImageStore, user_prefix
from app.schemas.conversation import (
    AgentType,
    ConversationHistoryResponse,
    ConversationMessageResponse,
)

logger = logging.getLogger(__name__)


class ImageUploadRequest(BaseModel):
    image_base64: str


# FastAPI router for conversation endpoints
# Prefix: /conversation (all routes will be prefixed with /conversation)
# Tags: ["conversation"] (for API documentation grouping)
router = APIRouter(prefix="/conversation", tags=["conversation"])


# Image limits from Plan C.7: content-detected format, size and pixel caps,
# resized and re-encoded so nothing but a clean JPEG reaches the disk
MAX_IMAGE_BYTES = 7 * 1024 * 1024
MAX_IMAGE_SIDE = 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = 25_000_000
# Filenames are always "{user_id}_{8 hex}.jpg" (set by upload_image)
IMAGE_FILENAME = re.compile(r"\d+_[0-9a-f]{8}\.jpg")
IMAGE_NAME = re.compile(r"[0-9a-f]{32}\.jpg")  # users/{id}/{uuid hex}.jpg (P4.9)


def _clean_image(image_data: bytes) -> bytes:
    """Validate an uploaded image and return it as a resized JPEG without metadata.

    Raises HTTPException 415 if the bytes are not a JPEG, PNG or WebP image.
    """
    try:
        # PIL only warns between 1x and 2x MAX_IMAGE_PIXELS; make the cap exact
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(image_data))
        with img:
            if img.format not in ALLOWED_IMAGE_FORMATS:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Image must be JPEG, PNG or WebP.",
                )
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            out = io.BytesIO()
            # Re-encoding drops EXIF (location, device) and any trailing payload
            img.convert("RGB").save(out, format="JPEG", quality=85)
            return out.getvalue()
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File is not a valid JPEG, PNG or WebP image.",
        ) from None


def _parse_warnings(warnings_json: str | None) -> list | None:
    """Parse warnings JSON string back to list. Returns None on missing or malformed input."""
    if not warnings_json:
        return None
    try:
        return json.loads(warnings_json)
    except json.JSONDecodeError:
        logger.warning("Could not parse warnings JSON: %s", warnings_json)
        return None


@router.get("/messages", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    agent_type: AgentType | None = None,
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
            warnings = _parse_warnings(msg.warnings)
            
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


@router.get("/images/{name}")
async def get_image(
    name: str,
    principal: Principal = Depends(get_principal),
    images: ImageStore = Depends(get_image_store),
) -> Response:
    """One of the signed-in account's images (C.8). The key is built from the session's
    user, never from the request, so another account's image looks like no image
    (404, not 403). Names: "{32 hex}.jpg" (users/{id}/…), or "{id}_{8 hex}.jpg" for
    images saved before P4.9."""
    key = _image_key(principal.user_id, name)
    data = await images.get(key) if key else None
    if data is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


def _image_key(user_id: int | None, name: str) -> str | None:
    if user_id is None:
        return None
    if IMAGE_NAME.fullmatch(name):
        return f"{user_prefix(user_id)}{name}"
    if IMAGE_FILENAME.fullmatch(name) and name.startswith(f"{user_id}_"):
        return f"images/{name}"
    return None


@router.delete("/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversation_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    engine: AsyncEngine = Depends(get_engine),
    images: ImageStore = Depends(get_image_store),
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
        - Messages go in one transaction; their images after it, and an image
          delete that fails is queued for the job (deletion_queue)
        
    Example:
        DELETE /conversation/messages
        
        Clears all conversation messages and associated images for current user
    """
    try:
        keys = [key for (key,) in db.query(ConversationMessage.image_path).filter(
            ConversationMessage.user_id == current_user.id,
            ConversationMessage.image_path.is_not(None)).all()]
        # Delete messages from database
        db.query(ConversationMessage).filter(
            ConversationMessage.user_id == current_user.id  # Security: Only current user's messages
        ).delete()
        db.commit()  # Commit transaction
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear conversation history",
        ) from e
    # After the commit, like account deletion (C.18): a failed image delete is queued
    for key in keys:
        await delete_or_queue(engine, images, key)
    return None

