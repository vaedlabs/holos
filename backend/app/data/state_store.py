"""State that must be right lives in Postgres (Plan C.11, C.13, C.17).

Sessions, in-flight leases, principal flags, rate counters, spend and credit
reservations, pending writes and request claims.

Every operation runs in its own short transaction and uses the database clock
(`now()`), so several processes can share the store and no connection is held
between calls. Concurrency is handled by single atomic statements (upserts and
conditional updates) or by row locks (`SELECT ... FOR UPDATE`), never by Python locks.
"""

import hashlib
import json
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.config import limits


def hash_session_id(raw_id: str) -> str:
    """The DB stores sha256(id), never the cookie value (Plan C.6)."""
    return hashlib.sha256(raw_id.encode()).hexdigest()


@dataclass(frozen=True)
class SessionInfo:
    id_hash: str
    mode: str
    user_id: int | None
    ip_key: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class LeaseResult:
    acquired: bool
    retry_after: int = 0  # seconds, for the 429 Retry-After header


@dataclass(frozen=True)
class RateResult:
    allowed: bool
    count: int
    retry_after: int  # seconds until the window resets


@dataclass(frozen=True)
class SpendKey:
    """One spend row to reserve against. The caller picks the period bucket (P4.3)."""

    key: str
    period: str  # "day" or "month" (C.11)
    period_start: datetime
    cap_usd: Decimal | None = None
    cap_credits: int | None = None


@dataclass(frozen=True)
class Reservation:
    keys: tuple[SpendKey, ...]
    usd: Decimal
    credits: int


@dataclass(frozen=True)
class ConfirmResult:
    status_code: int
    body: dict[str, Any]


# A block reason, or None to allow (the gate runs again at confirm time, C.17)
Regate = Callable[[dict[str, Any]], Awaitable[str | None]]
# Inserts the log row inside the confirm transaction and returns the confirmation
CommitWrite = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]

_SESSION_COLUMNS = "id_hash, mode, user_id, ip_key, created_at, expires_at"

_LEASE_UPSERT = text(
    "INSERT INTO inflight_leases (principal_key, trace_id, expires_at) "
    "VALUES (:key, :trace, now() + :ttl) "
    "ON CONFLICT (principal_key) DO UPDATE "
    "SET trace_id = excluded.trace_id, expires_at = excluded.expires_at "
    "WHERE inflight_leases.expires_at < now() "
    "RETURNING trace_id"
)


def _not_negative(**amounts) -> None:
    """A negative reservation or settlement would free budget that was never spent."""
    bad = [name for name, value in amounts.items() if value < 0]
    if bad:
        raise ValueError(f"amounts must not be negative: {', '.join(bad)}")


class _Refused(Exception):
    """Rolls back a transaction that couldn't take everything it needed."""

    def __init__(self, retry_after: int = 0):
        self.retry_after = retry_after


class StateStore:
    def __init__(self, engine: AsyncEngine):
        self._engine = engine

    # --- Sessions (C.6) ---

    async def create_session(
        self, mode: str, ip_key: str, user_id: int | None = None
    ) -> tuple[str, SessionInfo]:
        """Create a session; returns (cookie value, session). Only the hash is stored."""
        if (mode == "account") != (user_id is not None):
            raise ValueError("account sessions need a user_id; guest sessions must not have one")
        raw_id = secrets.token_urlsafe(32)  # 256 bits
        ttl = limits.GUEST_SESSION_TTL if mode == "guest" else limits.ACCOUNT_SESSION_IDLE
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                text(
                    "INSERT INTO sessions (id_hash, mode, user_id, ip_key, expires_at) "
                    "VALUES (:h, :mode, :uid, :ip, now() + :ttl) "
                    f"RETURNING {_SESSION_COLUMNS}"
                ),
                {"h": hash_session_id(raw_id), "mode": mode, "uid": user_id, "ip": ip_key,
                 "ttl": ttl},
            )).one()
        return raw_id, SessionInfo(*row)

    async def touch_session(self, raw_id: str) -> SessionInfo | None:
        """Mark a live session as used. Accounts slide the 7-day idle timeout, capped
        at 30 days from creation; guests keep their absolute 240 minutes."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                text(
                    "UPDATE sessions SET last_seen_at = now(), expires_at = CASE "
                    "WHEN mode = 'account' THEN LEAST(created_at + :max, now() + :idle) "
                    "ELSE expires_at END "
                    "WHERE id_hash = :h AND expires_at > now() "
                    f"RETURNING {_SESSION_COLUMNS}"
                ),
                {"h": hash_session_id(raw_id), "max": limits.ACCOUNT_SESSION_MAX,
                 "idle": limits.ACCOUNT_SESSION_IDLE},
            )).one_or_none()
        return SessionInfo(*row) if row else None

    async def end_session(self, raw_id: str) -> bool:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM sessions WHERE id_hash = :h"), {"h": hash_session_id(raw_id)}
            )
        return result.rowcount == 1

    async def end_user_sessions(self, user_id: int) -> int:
        """Log out everywhere (POST /auth/logout-all)."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": user_id}
            )
        return result.rowcount

    async def purge_expired_sessions(self) -> int:
        async with self._engine.begin() as conn:
            result = await conn.execute(text("DELETE FROM sessions WHERE expires_at <= now()"))
        return result.rowcount

    # --- In-flight leases (C.13) ---

    async def acquire_lease(
        self, principal_key: str, trace_id: str, ip_key: str | None = None
    ) -> LeaseResult:
        """One request in flight per principal. Guests (ip_key given) also take one of
        the IP key's slots, in the same transaction: both or neither."""
        try:
            async with self._engine.begin() as conn:
                await self._take_lease(conn, principal_key, trace_id)
                if ip_key is not None:
                    await self._take_ip_slot(conn, ip_key, trace_id)
        except _Refused as refused:
            return LeaseResult(False, refused.retry_after)
        return LeaseResult(True)

    async def _take_lease(self, conn: AsyncConnection, key: str, trace_id: str) -> None:
        taken = await conn.execute(
            _LEASE_UPSERT, {"key": key, "trace": trace_id, "ttl": limits.LEASE_TTL}
        )
        if taken.one_or_none() is None:
            raise _Refused(await self._seconds_left(conn, [key]))

    async def _take_ip_slot(self, conn: AsyncConnection, ip_key: str, trace_id: str) -> None:
        slots = [f"ip:{ip_key}:{n}" for n in range(limits.INFLIGHT_PER_GUEST_IP)]
        for slot in slots:
            taken = await conn.execute(
                _LEASE_UPSERT, {"key": slot, "trace": trace_id, "ttl": limits.LEASE_TTL}
            )
            if taken.one_or_none() is not None:
                return
        raise _Refused(await self._seconds_left(conn, slots, soonest=True))

    @staticmethod
    async def _seconds_left(conn: AsyncConnection, keys: list[str], soonest: bool = False) -> int:
        agg = "min" if soonest else "max"
        seconds = await conn.scalar(
            text(
                f"SELECT ceil(extract(epoch FROM {agg}(expires_at) - now())) "
                "FROM inflight_leases WHERE principal_key = ANY(:keys)"
            ),
            {"keys": keys},
        )
        return max(int(seconds or 0), 1)

    async def release_lease(
        self, principal_key: str, trace_id: str, ip_key: str | None = None
    ) -> None:
        """Delete only the leases this request holds (same trace_id)."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM inflight_leases WHERE trace_id = :trace "
                    "AND (principal_key = :key OR principal_key LIKE :slots)"
                ),
                {"trace": trace_id, "key": principal_key,
                 "slots": f"ip:{ip_key}:%" if ip_key else ""},
            )

    # --- Principal flags (C.16) ---

    async def set_crisis(self, principal_key: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO principal_flags (principal_key, crisis_at) VALUES (:key, now()) "
                    "ON CONFLICT (principal_key) DO UPDATE SET crisis_at = now()"
                ),
                {"key": principal_key},
            )

    async def crisis_active(self, principal_key: str) -> bool:
        async with self._engine.connect() as conn:
            found = await conn.scalar(
                text(
                    "SELECT 1 FROM principal_flags WHERE principal_key = :key "
                    "AND crisis_at > now() - :ttl"
                ),
                {"key": principal_key, "ttl": limits.CRISIS_FLAG_TTL},
            )
        return found is not None

    async def purge_expired_flags(self) -> int:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM principal_flags WHERE crisis_at IS NULL "
                     "OR crisis_at <= now() - :ttl"),
                {"ttl": limits.CRISIS_FLAG_TTL},
            )
        return result.rowcount

    # --- Rate counters ---

    async def hit_rate(self, key: str, window: timedelta, limit: int) -> RateResult:
        """Count one request in the current fixed window; allowed while count <= limit."""
        seconds = int(window.total_seconds())
        if seconds < 1 or limit < 0:
            raise ValueError("window must be at least 1 second and limit at least 0")
        async with self._engine.begin() as conn:
            count, retry_after = (await conn.execute(
                text(
                    "INSERT INTO rate_counters (key, window_start, count) VALUES (:key, "
                    "to_timestamp(floor(extract(epoch FROM now()) / :s) * :s), 1) "
                    "ON CONFLICT (key, window_start) DO UPDATE "
                    "SET count = rate_counters.count + 1 "
                    "RETURNING count, "
                    "ceil(extract(epoch FROM window_start + make_interval(secs => :s) - now()))"
                ),
                {"key": key, "s": seconds},
            )).one()
        return RateResult(count <= limit, count, max(int(retry_after), 1))

    async def peek_rate(self, key: str, window: timedelta) -> int:
        """The count in the current fixed window, without counting a request."""
        seconds = int(window.total_seconds())
        async with self._engine.connect() as conn:
            count = (await conn.execute(
                text(
                    "SELECT count FROM rate_counters WHERE key = :key AND window_start = "
                    "to_timestamp(floor(extract(epoch FROM now()) / :s) * :s)"
                ),
                {"key": key, "s": seconds},
            )).scalar_one_or_none()
        return count or 0

    async def purge_rate_counters(self, older_than: timedelta) -> int:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM rate_counters WHERE window_start < now() - :age"),
                {"age": older_than},
            )
        return result.rowcount

    # --- Spend and search credits (C.13) ---

    async def reserve(
        self, keys: list[SpendKey], usd: Decimal = Decimal("0"), credits: int = 0
    ) -> Reservation | None:
        """Reserve against every key, or none: if any cap would be passed, nothing is
        reserved and None is returned. Keys are locked in a fixed order so two
        reservations can't deadlock."""
        _not_negative(usd=usd, credits=credits)
        ordered = tuple(sorted(keys, key=lambda k: (k.key, k.period, k.period_start)))
        try:
            async with self._engine.begin() as conn:
                for k in ordered:
                    await self._reserve_one(conn, k, usd, credits)
        except _Refused:
            return None
        return Reservation(ordered, usd, credits)

    async def _reserve_one(
        self, conn: AsyncConnection, k: SpendKey, usd: Decimal, credits: int
    ) -> None:
        where = {"key": k.key, "period": k.period, "start": k.period_start}
        await conn.execute(
            text(
                "INSERT INTO spend (key, period, period_start) VALUES (:key, :period, :start) "
                "ON CONFLICT DO NOTHING"
            ),
            where,
        )
        caps = []
        if k.cap_usd is not None:
            caps.append("cost_usd + reserved_usd + :usd <= :cap_usd")
        if k.cap_credits is not None:
            caps.append("search_credits + reserved_credits + :credits <= :cap_credits")
        updated = await conn.execute(
            text(
                "UPDATE spend SET reserved_usd = reserved_usd + :usd, "
                "reserved_credits = reserved_credits + :credits "
                "WHERE key = :key AND period = :period AND period_start = :start"
                + "".join(f" AND {c}" for c in caps)
                + " RETURNING key"
            ),
            {**where, "usd": usd, "credits": credits, "cap_usd": k.cap_usd,
             "cap_credits": k.cap_credits},
        )
        if updated.one_or_none() is None:
            raise _Refused()

    async def settle(
        self,
        reservation: Reservation,
        usd: Decimal,
        tokens_in: int = 0,
        tokens_out: int = 0,
        credits: int = 0,
    ) -> None:
        """Replace the reservation with what the call actually cost."""
        _not_negative(usd=usd, tokens_in=tokens_in, tokens_out=tokens_out, credits=credits)
        async with self._engine.begin() as conn:
            for k in reservation.keys:
                await conn.execute(
                    text(
                        "UPDATE spend SET "
                        "reserved_usd = GREATEST(reserved_usd - :r_usd, 0), "
                        "reserved_credits = GREATEST(reserved_credits - :r_credits, 0), "
                        "cost_usd = cost_usd + :usd, search_credits = search_credits + :credits, "
                        "tokens_in = tokens_in + :t_in, tokens_out = tokens_out + :t_out "
                        "WHERE key = :key AND period = :period AND period_start = :start"
                    ),
                    {"r_usd": reservation.usd, "r_credits": reservation.credits, "usd": usd,
                     "credits": credits, "t_in": tokens_in, "t_out": tokens_out, "key": k.key,
                     "period": k.period, "start": k.period_start},
                )

    async def cancel(self, reservation: Reservation) -> None:
        """Give a reservation back when the call never ran."""
        await self.settle(reservation, Decimal("0"))

    async def spend(self, key: str, period: str, period_start: datetime) -> dict[str, Any] | None:
        async with self._engine.connect() as conn:
            row = (await conn.execute(
                text(
                    "SELECT cost_usd, reserved_usd, search_credits, reserved_credits, "
                    "tokens_in, tokens_out FROM spend "
                    "WHERE key = :key AND period = :period AND period_start = :start"
                ),
                {"key": key, "period": period, "start": period_start},
            )).mappings().one_or_none()
        return dict(row) if row else None

    # --- Pending writes (C.17) ---

    async def stage_write(
        self, user_id: int, kind: str, payload: dict[str, Any], profile_hash: str, trace_id: str
    ) -> uuid.UUID:
        write_id = uuid.uuid4()
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO pending_writes (id, user_id, kind, payload, profile_hash, "
                    "trace_id, expires_at) VALUES (:id, :uid, :kind, CAST(:payload AS json), "
                    ":hash, :trace, now() + :ttl)"
                ),
                {"id": write_id, "uid": user_id, "kind": kind,
                 "payload": _json(payload), "hash": profile_hash, "trace": trace_id,
                 "ttl": limits.PENDING_WRITE_TTL},
            )
        return write_id

    async def confirm_write(
        self, write_id: uuid.UUID, user_id: int, regate: Regate, commit: CommitWrite
    ) -> ConfirmResult:
        """Confirm a pending write in one transaction (C.17). Any failure rolls back
        everything and the write stays pending. A repeat confirm returns the stored
        result with its original status code."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                text(
                    "SELECT kind, payload, status, result, expires_at <= now() AS expired "
                    "FROM pending_writes WHERE id = :id AND user_id = :uid FOR UPDATE"
                ),
                {"id": write_id, "uid": user_id},
            )).mappings().one_or_none()
            if row is None:
                return ConfirmResult(404, {"error": "not_found"})
            if row["status"] in ("committed", "discarded"):
                return ConfirmResult(row["result"]["status_code"], row["result"]["body"])
            if row["expired"]:
                return ConfirmResult(410, {"error": "expired"})

            payload = {"kind": row["kind"], **row["payload"]}
            reason = await regate(payload)
            if reason is not None:
                result = {"status_code": 409, "body": {"error": "blocked", "reason": reason}}
                await self._finish_write(conn, write_id, "discarded", result)
                return ConfirmResult(409, result["body"])

            async with AsyncSession(bind=conn) as session:
                body = await commit(session, payload)
                await session.flush()
            result = {"status_code": 200, "body": body}
            await self._finish_write(conn, write_id, "committed", result)
            return ConfirmResult(200, body)

    @staticmethod
    async def _finish_write(
        conn: AsyncConnection, write_id: uuid.UUID, status: str, result: dict[str, Any]
    ) -> None:
        await conn.execute(
            text(
                "UPDATE pending_writes SET status = :status, result = CAST(:result AS json), "
                "confirmed_at = now(), expires_at = now() + interval '1 day' WHERE id = :id"
            ),
            {"status": status, "result": _json(result), "id": write_id},
        )

    # --- Request claims (C.5) ---

    async def claim_request(
        self, user_id: int, client_request_id: uuid.UUID, trace_id: str
    ) -> bool:
        """True for the first claim of (user_id, client_request_id); False for a duplicate."""
        async with self._engine.begin() as conn:
            claimed = await conn.execute(
                text(
                    "INSERT INTO request_claims (user_id, client_request_id, trace_id) "
                    "VALUES (:uid, :rid, :trace) ON CONFLICT DO NOTHING RETURNING trace_id"
                ),
                {"uid": user_id, "rid": client_request_id, "trace": trace_id},
            )
            return claimed.one_or_none() is not None


def _json(value: Any) -> str:
    return json.dumps(value, default=str)
