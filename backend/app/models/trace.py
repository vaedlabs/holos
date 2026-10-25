"""Request traces and gate decisions (Plan C.11). user_id cascades on user delete."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _user_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="CASCADE")


class Trace(Base):
    __tablename__ = "traces"

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id_hash: Mapped[str | None] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(_user_fk(), index=True)
    route: Mapped[str] = mapped_column(String(16))
    steps: Mapped[list[Any]] = mapped_column(JSON)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class GateDecision(Base):
    __tablename__ = "gate_decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int | None] = mapped_column(_user_fk(), index=True)
    rule_id: Mapped[str] = mapped_column(String(40))
    rules_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(8))
    item: Mapped[str | None] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RuleHitCount(Base):
    __tablename__ = "rule_hit_counts"

    rule_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, server_default="0")
