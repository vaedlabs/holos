"""ResilientProvider: deadlines, backup calls, retries, the fallback route and a circuit
breaker per provider (Plan C.9). Every time rule reads the call's measured Speed.

* Each call is bounded in our code at its deadline; no time left → ProviderTimeout.
* A call still running at its kind's live p90 (Backups) gets one identical backup
  call, if the p50 is still left, a slot is free at once, backups are under 10% of
  the last minute's calls and the budget allows it. The first reply wins; the
  cancelled call is charged at the winner's usage.
* Retry on 429, 5xx and timeouts: at most 2, and only if the call's p95 + 0.5 s is
  left after the wait. A longer Retry-After gives the route up at once.
* Then the fallback (another model or provider), with the same rules.
* Breaker per provider: a call is bad if it fails retryably or is still running at
  its p99; a timeout at our own deadline before p99 is neither good nor bad. Opens
  when 5 calls within 60 s were bad and they were at least half; after 30 s one
  trial call goes through (half-open); good closes it, bad reopens it.
* Bad requests and malformed replies are not retried here: they say nothing about
  provider health. The agent's own retry (C.10 step 6) handles malformed replies.
"""

import asyncio
import random
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from pydantic import BaseModel

from app.config.speeds import TIMEOUT_OVERSHOOT_S, Speed

from .base import (
    BadRequest,
    GenerateOptions,
    LLMProvider,
    LLMResult,
    Message,
    OverBudget,
    ProviderError,
    ProviderTimeout,
    RateLimited,
    ToolSpec,
    Usage,
)
from .base import ProviderUnavailable as Unavailable
from .scheduler import FairScheduler

MAX_RETRIES = 2
BASE_DELAY_S = 0.5
MAX_DELAY_S = 4.0  # the longest backoff of our own; a Retry-After is honoured in full
BREAKER_BAD_CALLS = 5
BREAKER_BAD_SHARE = 0.5
BREAKER_WINDOW_S = 60.0
BREAKER_COOLDOWN_S = 30.0
SPEED_WINDOW = 200  # the live p90 is taken over this many recent calls of a kind
SPEED_MIN_SAMPLES = 50  # below this, the measured table's p90 is used
BACKUP_SHARE = 0.1  # at most this share of the last minute's calls get a backup
BACKUP_WINDOW_S = 60.0


@dataclass
class CircuitBreaker:
    clock: Callable[[], float] = time.monotonic
    state: str = "closed"  # closed, open, half_open
    opened_at: float = 0.0
    trial_in_flight: bool = False
    calls: deque = field(default_factory=deque)  # (time, bad) within the window

    def allow(self) -> bool:
        now = self.clock()
        if self.state == "open" and now - self.opened_at >= BREAKER_COOLDOWN_S:
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
        left = self.opened_at + BREAKER_COOLDOWN_S - self.clock()
        return left if left > 0 else None

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
                self.state, self.trial_in_flight = "closed", False
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

    def threshold(self, kind: str, table: Speed) -> float:
        times = self._times.get(kind)
        if not times or len(times) < SPEED_MIN_SAMPLES:
            return table.p90
        ordered = sorted(times)
        return ordered[int(0.9 * len(ordered))]

    def record_time(self, kind: str, seconds: float) -> None:
        """A call's time to its reply; a cancelled call's time so far. Cancelled calls
        all ran past the threshold, so they still count on the right side of p90."""
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


@dataclass
class _Race:
    usage: Usage | None = None  # the winning call's usage, to charge the cancelled one


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
    ):
        self._routes = [r for r in (primary, fallback) if r is not None]
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
        last: ProviderError | None = None
        for route in self._routes:
            try:
                return await self._route(route, plan, call)
            except ProviderError as exc:
                if not exc.retryable:
                    raise
                last = exc
        assert last is not None
        raise last

    def _left(self, plan: CallPlan) -> float:
        return plan.deadline - self._clock()

    async def _route(self, route: Route, plan: CallPlan, call: dict) -> LLMResult:
        breaker = self._breakers[route.provider.name]
        for attempt in range(MAX_RETRIES + 1):
            if not breaker.allow():
                raise Unavailable("circuit open", route.provider.name)
            try:
                return await self._attempt(route, plan, call, breaker)
            except ProviderError as exc:
                if not exc.retryable or attempt == MAX_RETRIES or breaker.state == "open":
                    raise
                wait = self._delay(attempt, exc.retry_after)
                if self._left(plan) - wait < plan.speed.p95 + TIMEOUT_OVERSHOOT_S:
                    raise  # no time for a retry to succeed: give the route up now
                await self._sleep(wait)
        raise AssertionError("unreachable")

    async def _attempt(self, route, plan, call, breaker) -> LLMResult:
        """One try, with its backup call if it runs slow; records it on the breaker."""
        name = route.provider.name
        try:
            hold = await self._reserve(plan, route.options)
            try:
                await self._scheduler.acquire(name, plan.principal,
                                              start_by=plan.deadline - plan.speed.p95)
            except BaseException:
                await self._release(plan, hold)
                raise
        except BaseException:
            breaker.end_trial()  # no call was made
            raise
        started = self._clock()
        try:
            result = await self._race(route, plan, call, hold, breaker)
        except ProviderError as exc:
            if isinstance(exc, ProviderTimeout) and self._clock() - started < plan.speed.p99:
                # Cut short by our own deadline: says nothing about the provider
                breaker.end_trial()
            elif exc.retryable:
                breaker.record_failure()
            elif breaker.state == "half_open":
                # The provider answered, so it is up; a bad request or bad reply says
                # nothing about its health. End a half-open trial as healthy.
                breaker.record_success()
            raise
        if self._clock() - started >= plan.speed.p99:
            breaker.record_failure()  # slow: still running at p99
        else:
            breaker.record_success()
        return result

    async def _race(self, route, plan, call, hold, breaker) -> LLMResult:
        race = _Race()
        self._backups.note_call()
        tasks = [asyncio.create_task(self._one(route, plan, call, hold, race))]
        try:
            wait = self._backups.threshold(plan.kind, plan.speed) if plan.kind else plan.speed.p90
            done, _ = await asyncio.wait(tasks, timeout=wait)
            if not done and breaker.state == "closed":
                backup = await self._backup(route, plan, call, race)
                if backup is not None:
                    tasks.append(backup)
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

    async def _backup(self, route, plan, call, race) -> asyncio.Task | None:
        name = route.provider.name
        if self._left(plan) < plan.speed.p50:
            return None
        if not self._scheduler.take_now(name, plan.principal):
            return None
        try:
            hold = await self._reserve(plan, route.options)
        except OverBudget:
            self._scheduler.release(name, plan.principal)
            return None
        if not self._backups.take():
            self._scheduler.release(name, plan.principal)
            await self._release(plan, hold)
            return None
        return asyncio.create_task(self._one(route, plan, call, hold, race))

    async def _one(self, route, plan, call, hold, race) -> LLMResult:
        """One provider call in a slot already taken; frees the slot and settles."""
        name = route.provider.name
        started = self._clock()
        options = route.options
        outcome = "keep"  # timed out, cancelled or unparsable: usage unknown
        try:
            left = self._left(plan)
            if left <= 0:
                outcome = "release"
                raise ProviderTimeout("no time left", name)
            options = replace(route.options, timeout_s=left)
            try:
                async with asyncio.timeout(left):
                    result = await route.provider.generate(call["messages"], options=options,
                                                           system=call["system"],
                                                           tools=call["tools"],
                                                           schema=call["schema"])
            except TimeoutError:
                raise ProviderTimeout("deadline reached", name) from None
            except _NOT_BILLED:
                outcome = "release"
                raise
            except asyncio.CancelledError:
                if plan.kind:
                    self._backups.record_time(plan.kind, self._clock() - started)
                raise
            outcome = "settle"
            if plan.kind:
                self._backups.record_time(plan.kind, self._clock() - started)
            if plan.meter is not None and hold is not None:
                await plan.meter.settle(hold, options, result.usage)
            return result
        finally:
            self._scheduler.release(name, plan.principal, held_s=self._clock() - started)
            if outcome == "keep" and race.usage is not None and plan.meter is not None \
                    and hold is not None:
                # Lost the race: the same request, so the winner's usage is the best
                # estimate of what this one was billed (Part E #32)
                await plan.meter.settle(hold, options, race.usage)
            elif outcome == "keep":
                await self._keep(plan, hold)
            elif outcome == "release":
                await self._release(plan, hold)

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

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return retry_after
        backoff = BASE_DELAY_S * 2**attempt
        return min(backoff * (0.5 + self._jitter() / 2), MAX_DELAY_S)
