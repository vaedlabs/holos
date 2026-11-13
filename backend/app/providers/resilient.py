"""ResilientProvider: deadlines, backup calls, retries, the fallback route and a circuit
breaker per provider (Plan C.9). Every time rule reads the call's measured Speed.

* Each call is bounded in our code at its deadline; no time left → ProviderTimeout.
* A streaming call (Part E #35) also fails on silence: no output within
  STALL_FIRST_S of sending, or no new output for STALL_GAP_S once writing →
  ProviderStalled. A long reply that keeps writing runs to the deadline.
* A slow call gets one identical backup call (Backups): a streaming call with no
  output yet at its kind's live p90 of time to first output (never once writing); a
  non-streaming call still running at its kind's live p90. Only if the p50 is still
  left, a slot is free at once, backups are under 10% of the last minute's calls and
  the budget allows it. The first reply wins; the cancelled call is charged at the
  winner's usage.
* Retry on 429, 5xx and timeouts: at most 2, and only if the call's p95 + 0.5 s is
  left after the wait. A longer Retry-After gives the route up at once.
* Then the fallback (another model or provider), with the same rules.
* Breaker per provider: a call is bad if it fails retryably (a stall included) or, not
  streaming, is still running at its p99; a timeout at our own deadline is neither
  good nor bad (for a non-streaming call, only before its p99). Opens
  when 5 calls within 60 s were bad and they were at least half; after 30 s one
  trial call goes through (half-open); good closes it, bad reopens it.
* An account failure (key rejected, out of credit) opens the breaker at once, for 5
  minutes, and logs one alert line; it isn't retried, but a fallback route may run.
* Bad requests and malformed replies are not retried here: they say nothing about
  provider health. The agent's own retry (C.10 step 6) handles malformed replies.
* Every attempt, also one that never went out, is recorded on the plan's trace with
  its timings, the provider's request ID and its cause (Part E #39).
"""

import asyncio
import logging
import random
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from pydantic import BaseModel

from app.config.speeds import TIMEOUT_OVERSHOOT_S, Speed
from app.observability.tracer import Attempt, Role, Trace

from .base import (
    AccountFailure,
    BadRequest,
    GenerateOptions,
    LLMProvider,
    LLMResult,
    Message,
    OverBudget,
    ProviderError,
    ProviderStalled,
    ProviderTimeout,
    RateLimited,
    ToolSpec,
    Usage,
)
from .base import ProviderUnavailable as Unavailable
from .scheduler import FairScheduler

log = logging.getLogger(__name__)

MAX_RETRIES = 2
BASE_DELAY_S = 0.5
MAX_DELAY_S = 4.0  # the longest backoff of our own; a Retry-After is honoured in full
BREAKER_BAD_CALLS = 5
BREAKER_BAD_SHARE = 0.5
BREAKER_WINDOW_S = 60.0
BREAKER_COOLDOWN_S = 30.0
# A fixed key or a top-up is picked up within this; each trial is one failed request
ACCOUNT_COOLDOWN_S = 300.0
SPEED_WINDOW = 200  # the live p90 is taken over this many recent calls of a kind
SPEED_MIN_SAMPLES = 50  # below this, the measured table's p90 is used
BACKUP_SHARE = 0.1  # at most this share of the last minute's calls get a backup
BACKUP_WINDOW_S = 60.0
# Silence rules for streaming calls (Part E #35). Measured 29 Oct 2026: on a typical
# day the first output came within 4.7 s (84 calls), but in an hour when OpenAI was
# slower healthy calls took up to 13.9 s (1,665 calls), so 20 s; pauses once writing
# were at most 0.6 s
STALL_FIRST_S = 20.0
STALL_GAP_S = 5.0


@dataclass
class CircuitBreaker:
    clock: Callable[[], float] = time.monotonic
    state: str = "closed"  # closed, open, half_open
    opened_at: float = 0.0
    account: bool = False  # opened because the provider refused our account
    trial_in_flight: bool = False
    calls: deque = field(default_factory=deque)  # (time, bad) within the window

    def allow(self) -> bool:
        now = self.clock()
        if self.state == "open" and now - self.opened_at >= self._cooldown():
            self.state, self.trial_in_flight = "half_open", False
        if self.state == "closed":
            return True
        if self.state == "half_open" and not self.trial_in_flight:
            self.trial_in_flight = True
            return True
        return False

    def retry_after(self) -> float | None:
        """Seconds until the trial call, while open; None if calls may go through."""
        if self.state != "open":
            return None
        left = self.opened_at + self._cooldown() - self.clock()
        return left if left > 0 else None

    def _cooldown(self) -> float:
        return ACCOUNT_COOLDOWN_S if self.account else BREAKER_COOLDOWN_S

    def trip_account(self, provider: str) -> None:
        """The provider refused our account: open now, whatever the recent calls."""
        if self.state != "open":
            log.error("ALERT provider_account: %s refused our account (key or credit); "
                      "calls to it stop for %d s", provider, ACCOUNT_COOLDOWN_S)
        self.state, self.opened_at, self.account = "open", self.clock(), True
        self.trial_in_flight = False
        self.calls.clear()

    def end_trial(self) -> None:
        """The trial call was never made (no slot or no budget): another may try."""
        self.trial_in_flight = False

    def record_success(self) -> None:
        self._record(bad=False)

    def record_failure(self) -> None:
        self._record(bad=True)

    def _record(self, bad: bool) -> None:
        now = self.clock()
        if self.state == "half_open":
            if bad:
                self.state, self.opened_at, self.trial_in_flight = "open", now, False
            else:
                self.state, self.trial_in_flight, self.account = "closed", False, False
                self.calls.clear()
            return
        if self.state == "open":
            return  # a call that started before the breaker opened
        self.calls.append((now, bad))
        while self.calls and now - self.calls[0][0] > BREAKER_WINDOW_S:
            self.calls.popleft()
        bad_calls = sum(b for _, b in self.calls)
        if bad_calls >= BREAKER_BAD_CALLS and bad_calls >= BREAKER_BAD_SHARE * len(self.calls):
            self.state, self.opened_at = "open", now
            self.calls.clear()


class Breakers:
    """One breaker per provider name, shared by every request in the process."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._breakers: dict[str, CircuitBreaker] = {}

    def __getitem__(self, provider: str) -> CircuitBreaker:
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(clock=self._clock)
        return self._breakers[provider]


class Backups:
    """When a slow call gets a backup (Part E #32), shared by every request in the
    process. Provider speed drifts from day to day (Part D: the median doubled
    overnight), so the threshold is the live p90 of each kind of call, and backups
    are capped at 10% of the last minute's calls (at least 1)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._times: dict[str, deque[float]] = {}
        self._calls: deque[float] = deque()
        self._backups: deque[float] = deque()

    def threshold(self, kind: str, table: Speed, streaming: bool = False) -> float:
        times = self._times.get(kind)
        if not times or len(times) < SPEED_MIN_SAMPLES:
            return (table.first_p90 or table.p90) if streaming else table.p90
        ordered = sorted(times)
        return ordered[int(0.9 * len(ordered))]

    def record_time(self, kind: str, seconds: float) -> None:
        """A call's time to its first output (streaming) or to its reply; a cancelled
        call's time so far. Cancelled calls all ran past the threshold, so they still
        count on the right side of p90."""
        self._times.setdefault(kind, deque(maxlen=SPEED_WINDOW)).append(seconds)

    def note_call(self) -> None:
        self._calls.append(self._clock())

    def take(self) -> bool:
        """Room for one more backup in the last minute's share; takes it if so."""
        now = self._clock()
        for times in (self._calls, self._backups):
            while times and now - times[0] > BACKUP_WINDOW_S:
                times.popleft()
        if len(self._backups) + 1 > max(1, BACKUP_SHARE * len(self._calls)):
            return False
        self._backups.append(now)
        return True


class Meter(Protocol):
    """The budget for one caller's calls (C.13); budget.CallMeter in the app."""

    async def reserve(self, options: GenerateOptions) -> Any | None:
        """A hold for the call's maximum cost, or None if a cap has no room."""

    async def settle(self, hold: Any, options: GenerateOptions, usage: Usage) -> None:
        """The call reported its usage."""

    async def keep(self, hold: Any) -> None:
        """Usage unknown (timed out, cancelled, unparsable): spent at the maximum."""

    async def release(self, hold: Any) -> None:
        """Not billed (429, 5xx, refused) or never sent."""


@dataclass(frozen=True)
class CallPlan:
    deadline: float  # clock time the result is needed by (C.10 step 9)
    speed: Speed  # the measured speed of this kind of call (config/speeds.py)
    principal: str  # scheduler fairness key
    meter: Meter | None = None
    kind: str = ""  # names the call's kind for its live speed (Backups); "" = table only
    trace: Trace | None = None  # the request's trace; None: a trace of this call alone


@dataclass
class _Race:
    usage: Usage | None = None  # the winning call's usage, to charge the cancelled one


@dataclass
class _Watch:
    """One streaming call's progress, for the silence rules and the backup decision."""

    started: float
    first_output: float | None = None
    last_output: float | None = None


@dataclass(frozen=True)
class Route:
    provider: LLMProvider
    options: GenerateOptions


# Errors after which the call wasn't billed; any other end keeps the full reservation
_NOT_BILLED = (RateLimited, Unavailable, BadRequest)


class ResilientProvider:
    def __init__(
        self,
        primary: Route,
        fallback: Route | None,
        breakers: Breakers,
        scheduler: FairScheduler | None = None,
        backups: Backups | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
        stall_first_s: float = STALL_FIRST_S,
        stall_gap_s: float = STALL_GAP_S,
    ):
        self._routes = [r for r in (primary, fallback) if r is not None]
        self._stall_first_s = stall_first_s
        self._stall_gap_s = stall_gap_s
        self._breakers = breakers
        self._scheduler = scheduler or FairScheduler(clock=clock)
        self._backups = backups or Backups(clock)
        self._sleep = sleep
        self._jitter = jitter
        self._clock = clock

    async def generate(
        self,
        messages: list[Message],
        *,
        plan: CallPlan,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResult:
        call = {"messages": messages, "system": system, "tools": tools, "schema": schema}
        if plan.trace is None:
            plan = replace(plan, trace=Trace("untraced", self._clock))
        last: ProviderError | None = None
        for n, route in enumerate(self._routes):
            try:
                return await self._route(route, plan, call, fallback=n > 0)
            except ProviderError as exc:
                if not (exc.retryable or isinstance(exc, AccountFailure)):
                    raise
                last = exc
        assert last is not None
        raise last

    def _left(self, plan: CallPlan) -> float:
        return plan.deadline - self._clock()

    async def _route(self, route: Route, plan: CallPlan, call: dict,
                     fallback: bool) -> LLMResult:
        breaker = self._breakers[route.provider.name]
        for attempt in range(MAX_RETRIES + 1):
            role: Role = "retry" if attempt else "fallback" if fallback else "first"
            if not breaker.allow():
                # Left open by an account failure: the person is told the service is down
                kind = AccountFailure if breaker.account else Unavailable
                exc = kind("circuit open", route.provider.name, cause="circuit_open")
                plan.trace.end(self._record(plan, route, role), exc)
                raise exc
            try:
                return await self._attempt(route, plan, call, breaker, role)
            except ProviderError as exc:
                if not exc.retryable or attempt == MAX_RETRIES or breaker.state == "open":
                    raise
                wait = self._delay(attempt, exc.retry_after)
                if self._left(plan) - wait < plan.speed.p95 + TIMEOUT_OVERSHOOT_S:
                    raise  # no time for a retry to succeed: give the route up now
                await self._sleep(wait)
        raise AssertionError("unreachable")

    async def _attempt(self, route, plan, call, breaker, role: Role) -> LLMResult:
        """One try, with its backup call if it runs slow; records it on the breaker."""
        name = route.provider.name
        record = self._record(plan, route, role)
        try:
            hold = await self._reserve(plan, route.options)
            try:
                await self._scheduler.acquire(name, plan.principal,
                                              start_by=plan.deadline - plan.speed.p95)
            except BaseException:
                await asyncio.shield(self._release(plan, hold))
                raise
        except BaseException as exc:
            breaker.end_trial()  # no call was made
            plan.trace.end(record, exc)
            raise
        record.queued_ms = plan.trace.ms() - record.began_ms
        started = self._clock()
        streaming = _streams(route)
        try:
            result = await self._race(route, plan, call, hold, breaker, record)
        except ProviderError as exc:
            if isinstance(exc, ProviderTimeout) and (
                    streaming or self._clock() - started < plan.speed.p99):
                # Cut short by our own deadline: says nothing about the provider. A
                # streaming call that went silent raised ProviderStalled instead
                breaker.end_trial()
            elif isinstance(exc, AccountFailure):
                breaker.trip_account(name)
            elif exc.retryable:
                breaker.record_failure()
            elif breaker.state == "half_open":
                # The provider answered, so it is up; a bad request or bad reply says
                # nothing about its health. End a half-open trial as healthy.
                breaker.record_success()
            raise
        if not streaming and self._clock() - started >= plan.speed.p99:
            breaker.record_failure()  # slow: still running at p99
        else:
            breaker.record_success()
        return result

    async def _race(self, route, plan, call, hold, breaker, record: Attempt) -> LLMResult:
        race = _Race()
        self._backups.note_call()
        streaming = _streams(route)
        watch = _Watch(self._clock())
        tasks = [asyncio.create_task(self._one(route, plan, call, hold, race, watch,
                                               record))]
        try:
            if plan.kind:
                wait = self._backups.threshold(plan.kind, plan.speed, streaming)
            else:
                wait = (plan.speed.first_p90 or plan.speed.p90) if streaming else plan.speed.p90
            done, _ = await asyncio.wait(tasks, timeout=wait)
            # A streaming call that is writing is on its way: never back it up
            writing = streaming and watch.first_output is not None
            if not done and not writing:
                # A slow call without a backup says why on the trace (Part E #39)
                backup = (await self._backup(route, plan, call, race)
                          if breaker.state == "closed" else "breaker_not_closed")
                if isinstance(backup, asyncio.Task):
                    tasks.append(backup)
                else:
                    plan.trace.step("backup_skipped", outcome=backup, detail=plan.kind)
            pending = set(tasks)
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if task.exception() is None:
                        race.usage = task.result().usage
                        return task.result()
            raise tasks[0].exception()  # all failed: the first call's error is reported
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _backup(self, route, plan, call, race) -> asyncio.Task | str:
        """The backup call's task, or why there is none."""
        name = route.provider.name
        if self._left(plan) < plan.speed.p50:
            return "no_time"
        if not self._scheduler.take_now(name, plan.principal):
            return "no_slot"
        try:
            hold = await self._reserve(plan, route.options)
        except OverBudget:
            self._scheduler.release(name, plan.principal)
            return "over_budget"
        if not self._backups.take():
            self._scheduler.release(name, plan.principal)
            await self._release(plan, hold)
            return "share_cap"
        return asyncio.create_task(self._one(route, plan, call, hold, race,
                                             _Watch(self._clock()),
                                             self._record(plan, route, "backup")))

    async def _one(self, route, plan, call, hold, race, watch: _Watch,
                   record: Attempt) -> LLMResult:
        """One provider call in a slot already taken: frees the slot, settles, and ends
        its record on the trace."""
        try:
            result = await self._call(route, plan, call, hold, race, watch, record)
        except BaseException as exc:
            plan.trace.end(record, exc)
            raise
        plan.trace.end(record, tokens=(result.usage.tokens_in, result.usage.tokens_out),
                       request_id=result.request_id)
        return result

    async def _call(self, route, plan, call, hold, race, watch: _Watch,
                    record: Attempt) -> LLMResult:
        name = route.provider.name
        started = watch.started = self._clock()
        record.sent_ms = plan.trace.ms()
        streaming = _streams(route)
        options = route.options
        outcome = "keep"  # timed out, cancelled or unparsable: usage unknown
        usage: Usage | None = None

        def speed_sample() -> float:
            # Streaming: time to first output, the start that backups key on
            end = watch.first_output if streaming and watch.first_output else self._clock()
            return end - started

        try:
            left = self._left(plan)
            if left <= 0:
                outcome = "release"
                raise ProviderTimeout("no time left", name, cause="no_time_left")
            options = replace(route.options, timeout_s=left)
            try:
                async with asyncio.timeout(left):
                    request = route.provider.generate(
                        call["messages"], options=options, system=call["system"],
                        tools=call["tools"], schema=call["schema"],
                        progress=self._progress(watch, record, plan.trace) if streaming
                        else None,
                        opened=self._opened(record, plan.trace))
                    result = await (self._watched(request, watch, name) if streaming
                                    else request)
            except TimeoutError:
                writing = watch.first_output is not None
                raise ProviderTimeout(
                    "deadline reached" + (" while writing" if writing else ""), name,
                    cause="deadline_writing" if writing else "deadline_waiting") from None
            except _NOT_BILLED:
                outcome = "release"
                raise
            except asyncio.CancelledError:
                if plan.kind:
                    self._backups.record_time(plan.kind, speed_sample())
                raise
            outcome, usage = "settle", result.usage
            if plan.kind:
                self._backups.record_time(plan.kind, speed_sample())
            return result
        finally:
            self._scheduler.release(name, plan.principal, held_s=self._clock() - started)
            if outcome == "keep" and race.usage is not None:
                # Lost the race: the same request, so the winner's usage is the best
                # estimate of what this one was billed (Part E #32)
                outcome, usage = "settle", race.usage
            # Shielded: a call cancelled while it settles (the race ends while a
            # timed-out call is keeping its hold) would leave the hold reserved for the
            # rest of the period (break suite, Part E #59)
            await asyncio.shield(self._account(plan, hold, options, outcome, usage))

    def _progress(self, watch: _Watch, record: Attempt,
                  trace: Trace) -> Callable[[bool], None]:
        def on_event(output: bool) -> None:
            if output:
                now = self._clock()
                watch.last_output = now
                if watch.first_output is None:
                    watch.first_output = now
                    record.first_output_ms = trace.ms()
        return on_event

    @staticmethod
    def _opened(record: Attempt, trace: Trace) -> Callable[[str | None], None]:
        def on_open(request_id: str | None) -> None:
            record.opened_ms = trace.ms()
            record.request_id = request_id
        return on_open

    @staticmethod
    def _record(plan: CallPlan, route: Route, role: Role) -> Attempt:
        return plan.trace.attempt(plan.kind, route.provider.name, route.options.model, role)

    async def _watched(self, request: Awaitable[LLMResult], watch: _Watch,
                       name: str) -> LLMResult:
        """Await a streaming call, failing it when it goes silent (Part E #35)."""
        task = asyncio.ensure_future(request)
        try:
            while True:
                if watch.first_output is None:
                    silent_until = watch.started + self._stall_first_s
                else:
                    silent_until = watch.last_output + self._stall_gap_s
                wait = silent_until - self._clock()
                if wait <= 0:
                    first = watch.first_output is None
                    raise ProviderStalled(
                        f"stalled: {'no output' if first else 'output stopped'}", name,
                        cause="no_first_output" if first else "output_stopped")
                done, _ = await asyncio.wait({task}, timeout=wait)
                if done:
                    return task.result()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def _reserve(self, plan: CallPlan, options: GenerateOptions) -> Any | None:
        if plan.meter is None:
            return None
        hold = await plan.meter.reserve(options)
        if hold is None:
            raise OverBudget("a spend cap has no room for this call", "")
        return hold

    async def _release(self, plan: CallPlan, hold: Any | None) -> None:
        if plan.meter is not None and hold is not None:
            await plan.meter.release(hold)

    async def _keep(self, plan: CallPlan, hold: Any | None) -> None:
        if plan.meter is not None and hold is not None:
            await plan.meter.keep(hold)

    async def _account(self, plan: CallPlan, hold: Any | None, options: GenerateOptions,
                       outcome: str, usage: Usage | None) -> None:
        """A call's hold, settled at its usage, kept at its maximum or released."""
        if outcome == "settle" and plan.meter is not None and hold is not None:
            await plan.meter.settle(hold, options, usage)
        elif outcome == "keep":
            await self._keep(plan, hold)
        elif outcome == "release":
            await self._release(plan, hold)

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return retry_after
        backoff = BASE_DELAY_S * 2**attempt
        return min(backoff * (0.5 + self._jitter() / 2), MAX_DELAY_S)


def _streams(route: Route) -> bool:
    return bool(getattr(route.provider, "streams", False))
