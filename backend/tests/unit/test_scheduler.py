"""FairScheduler: per-principal cap, round-robin, cancellation and bulkheads (Plan P2.3)."""

import asyncio

import pytest

from app.providers import FairScheduler

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _hold(scheduler, provider, principal, seconds, log, peak):
    async with scheduler.slot(provider, principal):
        log.append(principal)
        peak[principal] = max(peak.get(principal, 0), scheduler.in_use(principal=principal))
        await asyncio.sleep(seconds)


async def test_no_principal_gets_more_than_three_slots():
    s = FairScheduler()
    log, peak = [], {}
    await asyncio.gather(*(_hold(s, "openai", "alice", 0.02, log, peak) for _ in range(7)))
    assert peak["alice"] == 3 and len(log) == 7


async def test_waiting_principals_are_served_round_robin():
    s = FairScheduler(provider_slots={"openai": 1, "gemini": 1, "tavily": 1}, global_slots=1)
    order: list[str] = []
    blocker = asyncio.Event()

    async def first():
        async with s.slot("openai", "zed"):
            await blocker.wait()

    async def job(principal):
        async with s.slot("openai", principal):
            order.append(principal)
            await asyncio.sleep(0)

    holder = asyncio.create_task(first())
    await asyncio.sleep(0)
    # Alice queues three requests before Bob queues his
    tasks = [asyncio.create_task(job("alice")) for _ in range(3)]
    tasks += [asyncio.create_task(job("bob")) for _ in range(3)]
    await asyncio.sleep(0)
    blocker.set()
    await asyncio.gather(holder, *tasks)
    assert order == ["alice", "bob", "alice", "bob", "alice", "bob"]


async def test_cancelling_a_waiter_frees_its_place():
    s = FairScheduler(provider_slots={"openai": 1, "gemini": 1, "tavily": 1}, global_slots=1)
    release = asyncio.Event()

    async def holder():
        async with s.slot("openai", "a"):
            await release.wait()

    h = asyncio.create_task(holder())
    await asyncio.sleep(0)
    waiter = asyncio.create_task(s.acquire("openai", "b"))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    await h
    assert s.in_use() == 0 and s.in_use(principal="b") == 0
    async with s.slot("openai", "c"):  # nothing stuck
        assert s.in_use() == 1


async def test_cancelling_a_running_call_releases_its_slot():
    s = FairScheduler()
    task = asyncio.create_task(_hold(s, "gemini", "a", 10, [], {}))
    await asyncio.sleep(0.01)
    assert s.in_use(provider="gemini") == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert s.in_use(provider="gemini") == 0 and s.in_use(principal="a") == 0


async def test_slow_gemini_does_not_take_openai_slots():
    s = FairScheduler()  # gemini 4, openai 6, global 8
    gemini = [asyncio.create_task(_hold(s, "gemini", f"g{i}", 0.5, [], {})) for i in range(10)]
    await asyncio.sleep(0.01)
    assert s.in_use(provider="gemini") == 4  # its bulkhead, not more
    started = asyncio.get_running_loop().time()
    await asyncio.gather(*(_hold(s, "openai", f"o{i}", 0.01, [], {}) for i in range(4)))
    assert asyncio.get_running_loop().time() - started < 0.2  # didn't wait for Gemini
    for t in gemini:
        t.cancel()
    await asyncio.gather(*gemini, return_exceptions=True)


async def test_global_limit_across_llm_providers():
    s = FairScheduler(provider_slots={"openai": 8, "gemini": 8, "tavily": 4}, global_slots=8)
    tasks = [asyncio.create_task(_hold(s, p, f"{p}{i}", 0.2, [], {}))
             for p in ("openai", "gemini") for i in range(6)]
    await asyncio.sleep(0.02)
    assert s.in_use() == 8
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert s.in_use() == 0


async def test_search_slots_do_not_count_against_the_llm_limit():
    s = FairScheduler(provider_slots={"openai": 8, "gemini": 8, "tavily": 4}, global_slots=2)
    tasks = [asyncio.create_task(_hold(s, "openai", f"o{i}", 0.2, [], {})) for i in range(2)]
    await asyncio.sleep(0.01)
    async with s.slot("tavily", "t1"):  # global LLM limit is full, search still runs
        assert s.in_use(provider="tavily") == 1
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        await FairScheduler().acquire("anthropic", "a")


async def test_waiters_cancelled_as_slots_free_do_not_leak():
    """Regression: a waiter cancelled while a slot frees used to be granted the slot,
    which then leaked."""
    s = FairScheduler(provider_slots={"openai": 2, "gemini": 2, "tavily": 2}, global_slots=2)
    holders = [asyncio.create_task(_hold(s, "openai", f"h{i}", 0.05, [], {})) for i in range(2)]
    await asyncio.sleep(0.01)
    waiters = [asyncio.create_task(_hold(s, "openai", f"w{i}", 0.05, [], {})) for i in range(6)]
    await asyncio.sleep(0.01)
    # Holders first: their slots free (and are handed out) before the cancelled
    # waiters have run their own clean-up, which is the window the bug needed
    for t in holders + waiters:
        t.cancel()
    await asyncio.gather(*holders, *waiters, return_exceptions=True)
    assert s.in_use() == 0 and s.in_use(provider="openai") == 0
    async with s.slot("openai", "after"):
        assert s.in_use() == 1


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
async def test_random_load_never_exceeds_caps_or_leaks(seed):
    import random

    r = random.Random(seed)
    caps = {"openai": 3, "gemini": 2, "tavily": 2}
    s = FairScheduler(provider_slots=caps, global_slots=4, per_principal=2)
    principals = [f"p{i}" for i in range(6)]
    violations = []

    async def job():
        provider, principal = r.choice(list(caps)), r.choice(principals)
        async with s.slot(provider, principal):
            if s.in_use(provider=provider) > caps[provider]:
                violations.append(f"{provider} over its cap")
            if s.in_use(principal=principal) > 2:
                violations.append(f"{principal} over 3")
            if s.in_use() > 4:
                violations.append("global over 4")
            await asyncio.sleep(r.random() / 100)

    tasks = [asyncio.create_task(job()) for _ in range(120)]
    for _ in range(40):  # cancel random tasks, waiting or running
        await asyncio.sleep(r.random() / 200)
        r.choice(tasks).cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert violations == []
    assert s.in_use() == 0
    assert all(s.in_use(provider=p) == 0 for p in caps)
    assert all(s.in_use(principal=p) == 0 for p in principals)
