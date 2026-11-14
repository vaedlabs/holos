"""An account's chat history (Plan C.5 History, C.11, C.21; Part E #61).

Each turn is two rows: the person's message (with its photo and the request's
`client_request_id`) and the answer. The answer keeps the models' history text in
`content`, who answered in `agents`, and what the person saw in `display`: the turn's
content events, without their envelope.
"""

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    image_path = Column(String, nullable=True)  # an image key (C.8), the person's message
    # The coaches who answered, in the order physical, nutrition, mental; null for the
    # person's message and for Holos's own reply
    agents = Column(ARRAY(String), nullable=True)
    # What the person saw (C.5 History); none is SQL NULL, not JSON null
    display = Column(JSON(none_as_null=True), nullable=True)
    trace_id = Column(String(64), nullable=True)  # the answer's request
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Idempotency key from the chat request (Plan C.5): the same request can't be stored twice
    client_request_id = Column(Uuid, nullable=True)
    __table_args__ = (
        UniqueConstraint("user_id", "client_request_id", name="uq_conversation_user_request"),
        Index("idx_conversation_user_created", "user_id", "created_at"),
        Index("idx_conversation_user_trace", "user_id", "trace_id"),
    )

    user = relationship("User", back_populates="conversation_messages")
