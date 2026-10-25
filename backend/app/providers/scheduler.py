"""FairScheduler: bounded, fair access to the providers (Plan C.9, C.12).

* Slots per provider (bulkheads): a slow Gemini can't take OpenAI's slots.
* LLM calls share a global limit (8); Tavily has only its own bulkhead.
* At most 3 slots per principal across providers.
* Waiting principals are served round-robin, so one busy user can't starve others.
* Cancelling a waiting or running call frees its place.

Usage:
    async with scheduler.slot("openai", principal_key):
        result = await provider.generate(...)
"""

import asyncio
from collections import Counter, OrderedDict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from app.config import limits

# Per-provider caps aren't fixed in the plan (Part E #15); they sum above the global
# limit so either LLM provider can use most of it when the other is idle.
PROVIDER_SLOTS = {"openai": 6, "gemini": 4, "tavily": 4}
LLM_PROVIDERS = frozenset({"openai", "gemini"})


def _new_future() -> asyncio.Future:
    return asyncio.get_running_loop().create_future()


@dataclass(eq=False)
class _Waiter:
    provider: str
    future: asyncio.Future = field(default_factory=_new_future)


class FairScheduler:
    def __init__(
        self,
        provider_slots: dict[str, int] | None = None,
        global_slots: int = limits.LLM_SLOTS_GLOBAL,
        per_principal: int = limits.LLM_SLOTS_PER_PRINCIPAL,
    ):
        self._caps = dict(provider_slots or PROVIDER_SLOTS)
        self._global = global_slots
        self._per_principal = per_principal
        self._by_provider: Counter[str] = Counter()
        self._by_principal: Counter[str] = Counter()
        self._llm_in_use = 0
        # principal -> its waiters, in arrival order; principals rotate for fairness
        self._waiting: OrderedDict[str, deque[_Waiter]] = OrderedDict()

    @asynccontextmanager
    async def slot(self, provider: str, principal: str):
        await self.acquire(provider, principal)
        try:
            yield
        finally:
            self.release(provider, principal)

    def in_use(self, provider: str | None = None, principal: str | None = None) -> int:
        if provider is not None:
            return self._by_provider[provider]
        if principal is not None:
            return self._by_principal[principal]
        return self._llm_in_use

    async def acquire(self, provider: str, principal: str) -> None:
        if provider not in self._caps:
            raise ValueError(f"unknown provider {provider!r}")
        if not self._waiting and self._can_run(provider, principal):
            self._take(provider, principal)
            return
        waiter = _Waiter(provider)
        self._waiting.setdefault(principal, deque()).append(waiter)
        self._dispatch()
        try:
            await waiter.future
        except asyncio.CancelledError:
            if waiter.future.done() and not waiter.future.cancelled():
                self.release(provider, principal)  # granted just as we were cancelled
            else:
                self._forget(principal, waiter)
            raise

    def release(self, provider: str, principal: str) -> None:
        self._by_provider[provider] -= 1
        self._by_principal[principal] -= 1
        if provider in LLM_PROVIDERS:
            self._llm_in_use -= 1
        self._dispatch()

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
                for gone in [w for w in queue if w.future.done()]:
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
