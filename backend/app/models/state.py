"""Request state kept in Postgres (Plan C.11): sessions, leases, caps, writes, invites.

Columns that reference users.id cascade on user delete (marked † in C.11).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
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
    # NULL while it waits: no time limit (Part E #50); a decided one is kept a day
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatRequest(Base):
    """One chat request per (principal, client_request_id): it runs once, and a
    reconnect finds it by that pair (Plan C.5, Part E #34)."""

    __tablename__ = "chat_requests"

    principal_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    client_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int | None] = mapped_column(_user_fk(), index=True)
    worker: Mapped[str | None] = mapped_column(String(128))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class StreamEventRow(Base):
    """A sent stream event, for a reconnect (Plan C.5). Health advice: kept 10 minutes."""

    __tablename__ = "stream_events"

    trace_id: Mapped[str] = mapped_column(
        ForeignKey("chat_requests.trace_id", ondelete="CASCADE"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    event: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
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


class AccountImport(Base):
    """One "save to an account" per (user, import_id): a resend gets the first result
    (Plan C.18; owner, 3 Nov 2026, Part E #46)."""

    __tablename__ = "account_imports"

    user_id: Mapped[int] = mapped_column(_user_fk(), primary_key=True)
    import_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = _now()


class UnresolvedTerm(Base):
    """A health phrase that names nothing in the catalogue, counted per day for the
    owner's review; no user link (Plan P4.10, Part E #42, #47). Kept 90 days."""

    __tablename__ = "unresolved_terms"

    term: Mapped[str] = mapped_column(String(40), primary_key=True)
    field: Mapped[str] = mapped_column(String(24), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
