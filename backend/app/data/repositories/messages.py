import uuid
from datetime import datetime

from sqlalchemy import delete, select

from app.models import ConversationMessage

from .base import UserScopedRepository


class MessageRepository(UserScopedRepository):
    """The user's conversation history."""

    async def add(
        self,
        role: str,
        content: str,
        agent_type: str = "coordinator",
        warnings: str | None = None,
        image_path: str | None = None,
        client_request_id: uuid.UUID | None = None,
        created_at: datetime | None = None,  # an imported turn keeps its time
    ) -> ConversationMessage:
        row = ConversationMessage(
            user_id=self._user_id, role=role, content=content, agent_type=agent_type,
            warnings=warnings, image_path=image_path, client_request_id=client_request_id,
        )
        if created_at is not None:
            row.created_at = created_at
        self._session.add(row)
        await self._session.flush()
        return row

    async def recent(self, n: int = 6) -> list[ConversationMessage]:
        """The last `n` messages, oldest first (prompt order)."""
        rows = await self._session.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.user_id == self._user_id)
            .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
            .limit(n)
        )
        return list(reversed(list(rows)))

    async def clear(self) -> int:
        result = await self._session.execute(
            delete(ConversationMessage).where(ConversationMessage.user_id == self._user_id)
        )
        return result.rowcount
