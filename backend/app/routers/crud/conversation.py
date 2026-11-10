"""The account's chat history and its photos. The chat stream saves both (P4.7); a
photo arrives with its message.

    GET    /conversation/messages?agent_type=   → the history, oldest first
    GET    /conversation/images/{name}          → one of the account's photos
    DELETE /conversation/messages               → the history and its photos

The image read and the clear are async: they wait on the image store, not on the sync
pool. The clear removes messages in one transaction and photos after it; a photo that
fails to go is queued for the job (deletion_queue, C.18).
"""

import json
import logging
import re

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.dependencies import (
    get_current_user,
    get_database,
    get_db_sessions,
    get_engine,
    get_image_store,
    get_principal,
)
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.orchestration.principal import Principal
from app.routers.errors import ApiError
from app.schemas.conversation import (
    AgentType,
    ConversationHistoryResponse,
    ConversationMessageResponse,
)
from app.storage.deletion import delete_or_queue
from app.storage.images import ImageStore, user_prefix

log = logging.getLogger(__name__)

router = APIRouter(prefix="/conversation", tags=["conversation"])

IMAGE_FILENAME = re.compile(r"\d+_[0-9a-f]{8}\.jpg")  # images/{id}_{8 hex}.jpg, before P4.9
IMAGE_NAME = re.compile(r"[0-9a-f]{32}\.jpg")  # users/{id}/{uuid hex}.jpg (P4.9)


def _parse_warnings(warnings_json: str | None) -> list | None:
    """Warnings are stored as JSON; missing or malformed gives None."""
    if not warnings_json:
        return None
    try:
        return json.loads(warnings_json)
    except json.JSONDecodeError:
        log.warning("Could not parse warnings JSON: %s", warnings_json)
        return None


@router.get("/messages", response_model=ConversationHistoryResponse)
def get_conversation_history(
    agent_type: AgentType | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
):
    query = db.query(ConversationMessage).filter(
        ConversationMessage.user_id == current_user.id)
    if agent_type:
        query = query.filter(ConversationMessage.agent_type == agent_type)
    messages = query.order_by(ConversationMessage.created_at.asc()).all()
    return ConversationHistoryResponse(messages=[
        ConversationMessageResponse(
            id=msg.id, role=msg.role, content=msg.content,
            warnings=_parse_warnings(msg.warnings), image_path=msg.image_path,
            agent_type=msg.agent_type, created_at=msg.created_at)
        for msg in messages])


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
        raise ApiError(404, "not_found", "There is no such image.")
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
    sessions: async_sessionmaker[AsyncSession] = Depends(get_db_sessions),
    engine: AsyncEngine = Depends(get_engine),
    images: ImageStore = Depends(get_image_store),
) -> None:
    mine = ConversationMessage.user_id == current_user.id
    async with sessions() as session, session.begin():
        keys = list(await session.scalars(select(ConversationMessage.image_path).where(
            mine, ConversationMessage.image_path.is_not(None))))
        await session.execute(delete(ConversationMessage).where(mine))
    # After the commit, like account deletion (C.18): a failed image delete is queued
    for key in keys:
        await delete_or_queue(engine, images, key)
