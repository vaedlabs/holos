"""One request's trace (Plan C.5, C.11, Part E #39): its steps and every model call
attempt, with timings and how each ended, so a failure always names its cause.

    trace = Trace(trace_id)
    plan = CallPlan(..., trace=trace)        # the ResilientProvider records attempts
    trace.step("gate", agent="physical", outcome="block")

Every failure is one Cause from a closed list. A ProviderError carries its cause; any
other exception is a "bug", logged with its stack. Each failed attempt writes one log
line with the trace ID and the provider's request ID, which OpenAI or Google support can
look up. Never the person's message, prompts or replies.

P4.10 adds the background writer (`traces`, `gate_decisions`); the TraceView is built by
the composer (`orchestration.composer.trace_view`).
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Literal, get_args

log = logging.getLogger(__name__)

Cause = Literal[
    "no_time_left",  # the deadline came before the call could be sent
    "queue_full",  # no slot in our scheduler would free in time (load shedding)
    "over_budget",  # a spend cap had no room for the call
    "circuit_open",  # the provider's breaker was open
    "rate_limited",  # the provider said 429
    "unavailable",  # 5xx, a connection error, or an error event mid-stream
    "bad_request",  # the provider refused our request (4xx)
    "provider_timeout",  # the HTTP client's own timeout
    "no_first_output",  # streaming: nothing written within the first-output limit
    "output_stopped",  # streaming: writing stopped for the gap limit
    "deadline_waiting",  # our deadline, before the call wrote anything
    "deadline_writing",  # our deadline, while the call was writing
    "malformed",  # the reply didn't parse into the schema
    "truncated",  # the reply was cut off at max_output_tokens
    "wrong_language",  # the router called Hindi another language twice
    "cancelled",  # lost the race to its backup, or the request ended
    "bug",  # anything else: our code
]
CAUSES: frozenset[str] = frozenset(get_args(Cause))
Outcome = Literal["running", "ok"] | Cause
Role = Literal["first", "retry", "backup", "fallback"]


def cause_of(exc: BaseException) -> Cause:
    """The cause of a failure. Only a ProviderError (or a cancellation) has one."""
    cause = getattr(exc, "cause", None)
    if cause in CAUSES:
        return cause
    return "cancelled" if isinstance(exc, asyncio.CancelledError) else "bug"


@dataclass
class Attempt:
    """One model call, or a call that never went out (no slot, no budget, breaker)."""

    call: str  # the kind of call: router, physical, nutrition, meal_photo, mental, ...
    provider: str
    model: str
    role: Role
    began_ms: int  # since the trace began
    queued_ms: int = 0  # waiting for a slot in our scheduler
    sent_ms: int | None = None
    opened_ms: int | None = None  # the provider's response headers arrived (streaming)
    first_output_ms: int | None = None
    ended_ms: int | None = None
    outcome: Outcome = "running"
    request_id: str | None = None
    status: int | None = None  # the HTTP status of a refused call
    tokens_in: int = 0
    tokens_out: int = 0
    detail: str = ""  # the error's message, shortened


@dataclass
class Step:
    name: str  # route, tool_call, gate, retry, explain, fallback, ...
    agent: str | None
    at_ms: int
    duration_ms: int = 0
    outcome: str = "ok"
    detail: str = ""  # a name or a category, never the person's text


@dataclass
class Trace:
    trace_id: str
    clock: Callable[[], float] = time.monotonic
    started: float = field(default=0.0)
    steps: list[Step] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    # Told of each step as it is recorded: the stream shows progress (C.5 `step`)
    listener: Callable[[Step], None] | None = None

    def __post_init__(self) -> None:
        if not self.started:
            self.started = self.clock()

    def ms(self) -> int:
        return round((self.clock() - self.started) * 1000)

    def attempt(self, call: str, provider: str, model: str, role: Role) -> Attempt:
        record = Attempt(call or "call", provider, model, role, began_ms=self.ms())
        self.attempts.append(record)
        return record

    def step(self, name: str, agent: str | None = None, outcome: str = "ok",
             detail: str = "", began_ms: int | None = None) -> Step:
        now = self.ms()
        at = now if began_ms is None else began_ms
        record = Step(name, agent, at, now - at, outcome, detail[:120])
        self.steps.append(record)
        if self.listener is not None:
            self.listener(record)
        return record

    def end(self, attempt: Attempt, exc: BaseException | None = None, *,
            tokens: tuple[int, int] = (0, 0), request_id: str | None = None) -> None:
        """An attempt ended: ok without `exc`, else its cause. A failure is logged."""
        attempt.ended_ms = self.ms()
        attempt.tokens_in, attempt.tokens_out = tokens
        attempt.request_id = request_id or getattr(exc, "request_id", None) \
            or attempt.request_id
        if exc is None:
            attempt.outcome = "ok"
            return
        attempt.outcome = cause_of(exc)
        attempt.status = getattr(exc, "status", None)
        attempt.detail = str(exc)[:200]
        if attempt.outcome == "cancelled":
            return  # lost the race to its backup: not a failure
        line = ("model call failed: trace=%s call=%s role=%s provider=%s cause=%s "
                "request_id=%s status=%s queued_ms=%s sent_ms=%s opened_ms=%s "
                "first_output_ms=%s ended_ms=%s detail=%s")
        args = (self.trace_id, attempt.call, attempt.role, attempt.provider,
                attempt.outcome, attempt.request_id, attempt.status, attempt.queued_ms,
                attempt.sent_ms, attempt.opened_ms, attempt.first_output_ms,
                attempt.ended_ms, attempt.detail)
        if attempt.outcome == "bug":
            log.error(line, *args, exc_info=exc)
        else:
            log.warning(line, *args)

    @property
    def failures(self) -> list[Attempt]:
        return [a for a in self.attempts if a.outcome not in ("ok", "running", "cancelled")]

    def as_dict(self) -> dict:
        return {"trace_id": self.trace_id, "steps": [asdict(s) for s in self.steps],
                "attempts": [asdict(a) for a in self.attempts]}
