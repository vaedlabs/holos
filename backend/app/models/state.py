"""Request state kept in Postgres (Plan C.11): sessions, leases, caps, writes, invites.

Columns that reference users.id cascade on user delete (marked † in C.11).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _user_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="CASCADE")


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Session(Base):
    """A browser session for a guest or an account (Plan C.6)."""

    __tablename__ = "sessions"
    __table_args__ = (CheckConstraint("mode IN ('guest', 'account')", name="ck_sessions_mode"),)

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    user_id: Mapped[int | None] = mapped_column(_user_fk(), index=True)
    ip_key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = _now()
    last_seen_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class InflightLease(Base):
    """One request in flight per principal (Plan C.13)."""

    __tablename__ = "inflight_leases"

    principal_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PrincipalFlag(Base):
    """Flags on a principal; crisis_at lasts 30 minutes (Plan C.16)."""

    __tablename__ = "principal_flags"

    principal_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    crisis_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RateCounter(Base):
    __tablename__ = "rate_counters"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, server_default="0")


class Spend(Base):
    """Spend and search credits per key and period, with open reservations (Plan C.13)."""

    __tablename__ = "spend"
    __table_args__ = (CheckConstraint("period IN ('day', 'month')", name="ck_spend_period"),)

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    period: Mapped[str] = mapped_column(String(8), primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    tokens_in: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tokens_out: Mapped[int] = mapped_column(BigInteger, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default="0")
    search_credits: Mapped[int] = mapped_column(Integer, server_default="0")
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default="0")
    reserved_credits: Mapped[int] = mapped_column(Integer, server_default="0")


class PendingWrite(Base):
    """A staged log write awaiting confirmation (Plan C.17)."""

    __tablename__ = "pending_writes"
    __table_args__ = (
        CheckConstraint("kind IN ('workout', 'meal', 'practice')", name="ck_pending_writes_kind"),
        CheckConstraint(
            "status IN ('pending', 'committed', 'discarded')", name="ck_pending_writes_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(_user_fk(), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    profile_hash: Mapped[str] = mapped_column(String(64))
    trace_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RequestClaim(Base):
    """Claims (user_id, client_request_id) so a request runs once (Plan C.5)."""

    __tablename__ = "request_claims"

    user_id: Mapped[int] = mapped_column(_user_fk(), primary_key=True)
    client_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now()


class Invite(Base):
    """Invite-only account sign-up (Plan C.18)."""

    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Who made the invite, e.g. "cli"; not a user reference (invites come from the CLI)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[int | None] = mapped_column(_user_fk(), index=True)


class DeletionQueue(Base):
    """Object-store prefixes still to delete after an account is removed (Plan C.18)."""

    __tablename__ = "deletion_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prefix: Mapped[str] = mapped_column(String(256))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
