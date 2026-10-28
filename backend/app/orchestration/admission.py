"""Admission, C.2 stage 6: who may start a chat request now (Plan C.12, C.13).

    admitted = await admit(principal, client_request_id, store)   # or ApiError 429/409/503
    try:
        ...                                                        # stages 7-14
    finally:
        await admitted.release()                                   # stage 15

A request is refused before it takes anything if the chat provider's circuit breaker
is open (503 until its trial call) or a spend cap has nothing left. Then,
in one transaction: the request claim (accounts), the principal's lease, an IP slot
(guests), a global slot, and one count on each request counter. A refused request
holds no lease and counts nowhere. Runs before any image is decoded (stage 7).
"""

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.config import limits
from app.data.state_store import Counter, SpendKey, StateStore
from app.providers.resilient import CircuitBreaker
from app.routers.errors import ApiError

from .budget import day_start, month_start, search_keys, spend_keys, window_start
from .principal import Principal, ip_requests_key

SERVER_BUSY_RETRY_S = 5  # a typical request ends within seconds; a slot frees soon
MINUTE = timedelta(minutes=1)
DAY = timedelta(days=1)

# refusal → (HTTP status, code, message shown in the chat)
_REFUSALS = {
    "duplicate": (409, "duplicate_request", "This message was already sent."),
    "lease": (429, "busy", "Your last message is still being answered. "
              "Please wait for it to finish."),
    "ip_slot": (429, "network_busy", "Several chats from your network are running right "
                "now. Please try again in a moment."),
    "global_slot": (503, "server_busy", "Holos is busy right now. "
                    "Please try again in a few seconds."),
    "minute": (429, "too_fast", "You're sending messages quickly. "
               "Please wait a moment and try again."),
    "session": (429, "cap_reached", "You've used this session's allowance. "
                "Please come back later."),
    "account": (429, "cap_reached", "You've reached today's limit. "
                "It resets at midnight UTC."),
    "ip": (429, "cap_reached", "Your network has reached its limit for now. "
           "Please try again later."),
    "global_day": (429, "cap_reached", "The demo has used today's budget. "
                   "Please come back tomorrow."),
    "global_month": (429, "month_budget_used", "This month's demo budget is used up. "
                     "You can still watch the demo video."),
}


@dataclass
class Admitted:
    trace_id: str
    principal: Principal
    spend_keys: list[SpendKey]  # every LLM call reserves against these (budget.py)
    search_keys: list[SpendKey]  # every web search reserves a credit against these
    _store: StateStore = field(repr=False)

    @property
    def _ip_key(self) -> str | None:
        return self.principal.ip_key if self.principal.user_id is None else None

    async def release(self) -> None:
        """Stage 15, in `finally`: frees the lease and slots this request holds."""
        await self._store.release_lease(self.principal.principal_key, self.trace_id,
                                        self._ip_key)


def _counters(principal: Principal) -> tuple[Counter, ...]:
    key = principal.principal_key
    minute = Counter(f"{key}:minute", MINUTE, limits.REQUESTS_PER_MINUTE, "minute")
    if principal.user_id is not None:
        return (minute, Counter(f"{key}:requests", DAY, limits.ACCOUNT_DAY_REQUESTS, "account"))
    session = principal.session
    return (
        minute,
        Counter(f"{key}:requests", limits.GUEST_SESSION_TTL, limits.GUEST_SESSION_REQUESTS,
                "session", window_start=session.created_at),
        # Past the allowance (60) new sessions need the interactive check (sessions.py);
        # requests stop at the hard stop
        Counter(ip_requests_key(principal.ip_key), limits.GUEST_IP_WINDOW,
                limits.GUEST_IP_REQUESTS * limits.GUEST_IP_HARD_STOP_FACTOR, "ip"),
    )


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(int((moment - now).total_seconds()) + 1, 1)


def _cap_retry_after(name: str, principal: Principal, now: datetime) -> int:
    """When a full spend cap has room again."""
    if name == "session":
        return _seconds_until(principal.session.expires_at, now)
    if name == "ip":
        return _seconds_until(window_start(limits.GUEST_IP_WINDOW, now)
                              + limits.GUEST_IP_WINDOW, now)
    if name == "global_month":
        start = month_start(now)
        return _seconds_until((start + timedelta(days=32)).replace(day=1), now)
    return _seconds_until(day_start(now) + DAY, now)  # account, global_day


def _refused(name: str, retry_after: int) -> ApiError:
    status, code, message = _REFUSALS[name]
    return ApiError(status, code, message, retry_after=None if name == "duplicate"
                    else retry_after)


async def admit(
    principal: Principal,
    client_request_id: uuid.UUID,
    store: StateStore,
    billing_day: int = 1,
    trace_id: str | None = None,
    breaker: CircuitBreaker | None = None,
) -> Admitted:
    # The provider is failing: refuse at once rather than start a doomed request (C.13)
    down_for = breaker.retry_after() if breaker is not None else None
    if down_for is not None:
        raise _refused("global_slot", math.ceil(down_for))
    now = datetime.now(UTC)
    trace_id = trace_id or uuid.uuid4().hex
    keys = spend_keys(principal, now)
    full = await store.first_over_cap(keys)
    if full is not None:
        raise _refused(full.name, _cap_retry_after(full.name, principal, now))

    guest = principal.user_id is None
    result = await store.admit(
        principal.principal_key, trace_id,
        ip_key=principal.ip_key if guest else None,
        global_slots=limits.INFLIGHT_GLOBAL,
        counters=_counters(principal),
        claim=None if guest else (principal.user_id, client_request_id),
    )
    if not result.admitted:
        retry_after = (SERVER_BUSY_RETRY_S if result.refused_by == "global_slot"
                       else result.retry_after)
        raise _refused(result.refused_by, retry_after)
    return Admitted(trace_id, principal, keys, search_keys(principal, billing_day, now), store)
