"""FairScheduler: bounded, fair access to the providers (Plan C.9, C.12).

* Slots per provider (bulkheads): a slow Gemini can't take OpenAI's slots.
* LLM calls share a global limit (24); Tavily has only its own bulkhead.
* At most 3 slots per principal across providers.
* Waiting principals are served round-robin, so one busy user can't starve others.
* Cancelling a waiting or running call frees its place.
* Load shedding: a call that can't get a slot by its `start_by` time fails with
  NoCapacity: at once if the predicted wait is too long, again whenever a finished
  call updates the prediction, and at the latest when that time comes. It never
  queues past its deadline.

Usage:
    async with scheduler.slot("openai", principal_key, start_by=deadline - p95):
        result = await provider.generate(...)
"""

import asyncio
import itertools
import time
from collections import Counter, OrderedDict, deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from app.config import limits, speeds

from .base import NoCapacity

LLM_PROVIDERS = frozenset({"openai", "gemini"})
# The average slot time starts at the measured physical p50 and follows real calls
SLOT_TIME_START_S = speeds.PHYSICAL.p50
SLOT_TIME_WEIGHT = 0.1  # weight of each new call in the running average


def _new_future() -> asyncio.Future:
    return asyncio.get_running_loop().create_future()


_arrivals = itertools.count()


@dataclass(eq=False)
class _Waiter:
    provider: str
    start_by: float | None = None
    arrival: int = field(default_factory=lambda: next(_arrivals))
    future: asyncio.Future = field(default_factory=_new_future)


class FairScheduler:
    def __init__(
        self,
        provider_slots: dict[str, int] | None = None,
        global_slots: int = limits.LLM_SLOTS_GLOBAL,
        per_principal: int = limits.LLM_SLOTS_PER_PRINCIPAL,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._caps = dict(provider_slots or limits.PROVIDER_SLOTS)
        self._global = global_slots
        self._per_principal = per_principal
        self._clock = clock
        self._by_provider: Counter[str] = Counter()
        self._by_principal: Counter[str] = Counter()
        self._llm_in_use = 0
        self._slot_time = dict.fromkeys(self._caps, SLOT_TIME_START_S)
        # principal -> its waiters, in arrival order; principals rotate for fairness
        self._waiting: OrderedDict[str, deque[_Waiter]] = OrderedDict()

    @asynccontextmanager
    async def slot(self, provider: str, principal: str, start_by: float | None = None):
        await self.acquire(provider, principal, start_by)
        started = self._clock()
        try:
            yield
        finally:
            self.release(provider, principal, held_s=self._clock() - started)

    def in_use(self, provider: str | None = None, principal: str | None = None) -> int:
        if provider is not None:
            return self._by_provider[provider]
        if principal is not None:
            return self._by_principal[principal]
        return self._llm_in_use

    def predicted_wait(self, provider: str, ahead: int | None = None) -> float:
        """Seconds until a waiter for `provider` with `ahead` waiters before it (default:
        a new one, behind all) would likely get a slot."""
        if ahead is None:
            ahead = sum(w.provider == provider for q in self._waiting.values() for w in q)
        slots = self._caps[provider]
        if provider in LLM_PROVIDERS:
            slots = min(slots, self._global)
        return (ahead + 1) / slots * self._slot_time[provider]

    def take_now(self, provider: str, principal: str) -> bool:
        """A slot only if one is free at once and nobody waits (backup calls)."""
        if self._waiting or not self._can_run(provider, principal):
            return False
        self._take(provider, principal)
        return True

    async def acquire(self, provider: str, principal: str, start_by: float | None = None) -> None:
        if provider not in self._caps:
            raise ValueError(f"unknown provider {provider!r}")
        if not self._waiting and self._can_run(provider, principal):
            self._take(provider, principal)
            return
        if start_by is not None and self._clock() + self.predicted_wait(provider) > start_by:
            raise NoCapacity("no slot in time", provider)
        waiter = _Waiter(provider, start_by)
        self._waiting.setdefault(principal, deque()).append(waiter)
        self._dispatch()
        try:
            if start_by is None:
                await waiter.future
            else:
                async with asyncio.timeout(max(start_by - self._clock(), 0)):
                    await waiter.future
        except NoCapacity:
            self._forget(principal, waiter)  # shed while waiting (_shed_late)
            raise
        except (asyncio.CancelledError, TimeoutError) as exc:
            if waiter.future.done() and not waiter.future.cancelled() \
                    and waiter.future.exception() is None:
                self.release(provider, principal)  # granted just as we were cancelled
            else:
                self._forget(principal, waiter)
            if isinstance(exc, TimeoutError):
                raise NoCapacity("no slot in time", provider) from None
            raise

    def release(self, provider: str, principal: str, held_s: float | None = None) -> None:
        self._by_provider[provider] -= 1
        self._by_principal[principal] -= 1
        if provider in LLM_PROVIDERS:
            self._llm_in_use -= 1
        if held_s is not None:
            self._slot_time[provider] += SLOT_TIME_WEIGHT * (held_s - self._slot_time[provider])
        self._dispatch()
        if held_s is not None:
            self._shed_late(provider)

    def _shed_late(self, provider: str) -> None:
        """With the updated slot time, fail the waiters that can no longer start in time,
        rather than letting them wait until their start_by to hear it."""
        queue = sorted((w for q in self._waiting.values() for w in q
                        if w.provider == provider and not w.future.done()),
                       key=lambda w: w.arrival)
        now, ahead = self._clock(), 0
        for waiter in queue:
            if waiter.start_by is not None and \
                    now + self.predicted_wait(provider, ahead) > waiter.start_by:
                waiter.future.set_exception(NoCapacity("no slot in time", provider))
            else:
                ahead += 1

    def _can_run(self, provider: str, principal: str) -> bool:
        if self._by_provider[provider] >= self._caps[provider]:
            return False
        if self._by_principal[principal] >= self._per_principal:
            return False
        return not (provider in LLM_PROVIDERS and self._llm_in_use >= self._global)

    def _take(self, provider: str, principal: str) -> None:
        self._by_provider[provider] += 1
        self._by_principal[principal] += 1
        if provider in LLM_PROVIDERS:
            self._llm_in_use += 1

    def _dispatch(self) -> None:
        """Grant free slots, visiting waiting principals in turn (round-robin)."""
        granted = True
        while granted and self._waiting:
            granted = False
            for principal in list(self._waiting):
                queue = self._waiting[principal]
                # A waiter cancelled but not yet cleaned up must not get a slot: its
                # future can't take a result, and the slot would leak
                for gone in [w for w in queue if w.future.done()]:  # cancelled or shed
                    queue.remove(gone)
                if not queue:
                    del self._waiting[principal]
                    continue
                waiter = next((w for w in queue if self._can_run(w.provider, principal)), None)
                if waiter is None:
                    continue
                queue.remove(waiter)
                self._take(waiter.provider, principal)
                waiter.future.set_result(None)
                # Served principals go to the back of the line
                self._waiting.move_to_end(principal)
                if not queue:
                    del self._waiting[principal]
                granted = True
                break

    def _forget(self, principal: str, waiter: _Waiter) -> None:
        queue = self._waiting.get(principal)
        if queue and waiter in queue:
            queue.remove(waiter)
            if not queue:
                del self._waiting[principal]
