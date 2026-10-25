from sqlalchemy import select

from app.models import ConversationMessage

from .base import UserScopedRepository


class ImageRepository(UserScopedRepository):
    """Image keys attached to the user's messages (the files live in the ImageStore)."""

    async def keys(self) -> list[str]:
        rows = await self._session.scalars(
            select(ConversationMessage.image_path)
            .where(
                ConversationMessage.user_id == self._user_id,
                ConversationMessage.image_path.is_not(None),
            )
            .order_by(ConversationMessage.id)
        )
        return list(rows)

    async def owns(self, key: str) -> bool:
        found = await self._session.scalar(
            select(ConversationMessage.id).where(
                ConversationMessage.user_id == self._user_id,
                ConversationMessage.image_path == key,
            ).limit(1)
        )
        return found is not None
