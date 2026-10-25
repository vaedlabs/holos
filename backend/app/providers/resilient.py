"""ResilientProvider: retry with backoff, then the fallback route, with a circuit
breaker per provider (Plan C.9).

* Retry on 429, 5xx and timeouts: at most 2 retries, honouring Retry-After.
* Then the fallback (another model or provider), with the same retry rule.
* Breaker per provider: opens after 5 failures within 60 s; after 30 s it lets one
  trial call through (half-open); success closes it, failure opens it again.
* Bad requests and malformed replies are not retried here: they say nothing about
  provider health. The agent's own retry (C.10 step 6) handles malformed replies.
"""

import asyncio
import random
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from .base import GenerateOptions, LLMProvider, LLMResult, Message, ProviderError, ToolSpec
from .base import ProviderUnavailable as Unavailable

MAX_RETRIES = 2
BASE_DELAY_S = 0.5
MAX_DELAY_S = 4.0
BREAKER_FAILURES = 5
BREAKER_WINDOW_S = 60.0
BREAKER_COOLDOWN_S = 30.0


@dataclass
class CircuitBreaker:
    clock: Callable[[], float] = time.monotonic
    state: str = "closed"  # closed, open, half_open
    opened_at: float = 0.0
    trial_in_flight: bool = False
    failures: deque = field(default_factory=deque)

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

    def record_success(self) -> None:
        self.state, self.trial_in_flight = "closed", False
        self.failures.clear()

    def record_failure(self) -> None:
        now = self.clock()
        if self.state == "half_open":
            self.state, self.opened_at, self.trial_in_flight = "open", now, False
            return
        self.failures.append(now)
        while self.failures and now - self.failures[0] > BREAKER_WINDOW_S:
            self.failures.popleft()
        if len(self.failures) >= BREAKER_FAILURES:
            self.state, self.opened_at = "open", now
            self.failures.clear()


class Breakers:
    """One breaker per provider name, shared by every request in the process."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._breakers: dict[str, CircuitBreaker] = {}

    def __getitem__(self, provider: str) -> CircuitBreaker:
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(clock=self._clock)
        return self._breakers[provider]


@dataclass(frozen=True)
class Route:
    provider: LLMProvider
    options: GenerateOptions


class ResilientProvider:
    def __init__(
        self,
        primary: Route,
        fallback: Route | None,
        breakers: Breakers,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ):
        self._routes = [r for r in (primary, fallback) if r is not None]
        self._breakers = breakers
        self._sleep = sleep
        self._jitter = jitter

    async def generate(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResult:
        last: ProviderError | None = None
        for route in self._routes:
            try:
                return await self._attempt(route, messages, system, tools, schema)
            except ProviderError as exc:
                if not exc.retryable:
                    raise
                last = exc
        assert last is not None
        raise last

    async def _attempt(self, route, messages, system, tools, schema) -> LLMResult:
        breaker = self._breakers[route.provider.name]
        for attempt in range(MAX_RETRIES + 1):
            if not breaker.allow():
                raise Unavailable("circuit open", route.provider.name)
            try:
                result = await route.provider.generate(
                    messages, options=route.options, system=system, tools=tools, schema=schema
                )
            except ProviderError as exc:
                if not exc.retryable:
                    # The provider answered, so it is up; a bad request or bad reply
                    # says nothing about its health. End a half-open trial as healthy.
                    if breaker.state == "half_open":
                        breaker.record_success()
                    raise
                breaker.record_failure()
                if attempt == MAX_RETRIES:
                    raise
                await self._sleep(self._delay(attempt, exc.retry_after))
                continue
            breaker.record_success()
            return result
        raise AssertionError("unreachable")

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, MAX_DELAY_S)
        backoff = BASE_DELAY_S * 2**attempt
        return min(backoff * (0.5 + self._jitter() / 2), MAX_DELAY_S)
