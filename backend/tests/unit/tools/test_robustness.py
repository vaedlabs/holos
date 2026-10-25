"""Robustness of the tools beyond the plan's list: cancellation, fuzzed arguments,
cache bounds, Unicode queries, JSON-safe output and a failing gate."""

import asyncio
import contextlib
import copy
import json
import random

import pytest

from app.agents.schemas import StagedWrite
from app.agents.tools import AGENT_TOOLS, ToolContext, WebSearch
from app.agents.tools import web_search as ws

from .conftest import Clock, FakeSearchClient, FakeStore
from .test_write_and_read_tools import WRITES

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

TOOLS = {t.name: t for tools in AGENT_TOOLS.values() for t in tools}
SEARCH = TOOLS["web_search"]


async def test_cancelled_search_settles_its_credit():
    store = FakeStore()
    ctx = ToolContext(mode="guest", trace_id="t", search_keys=["k"],
                      search=WebSearch(FakeSearchClient(delay=5), store, Clock()))
    task = asyncio.create_task(SEARCH.run({"query": "q"}, ctx))
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert store.reserved == 0 and store.used == 1  # no leaked reservation


# --- Fuzzed arguments: never an exception, never an invalid staged write ---

_JUNK = [None, True, -1, 0, 10**9, 3.7, "", " ", "x" * 5000, "बैठक 🏋️", [], {}, [None],
         {"nested": {"deep": [1]}}, "'; DROP TABLE users; --", "\u0000", float("nan")]


def _mutate(r: random.Random, valid: dict) -> dict:
    args = copy.deepcopy(valid)  # never edit the shared test data
    for _ in range(r.randint(1, 4)):
        roll = r.random()
        if roll < 0.4 and args:
            args[r.choice(list(args))] = r.choice(_JUNK)
        elif roll < 0.6 and args:
            args.pop(r.choice(list(args)))
        elif roll < 0.8:
            args[r.choice(["extra", "user_id", "kind", "__class__"])] = r.choice(_JUNK)
        else:
            args = copy.deepcopy(r.choice([{}, {"query": r.choice(_JUNK)}, valid]))
    return args


VALID = {
    **{name: args for name, (_, args, _) in WRITES.items()},
    "get_recent_logs": {"kind": "workout", "days": 7},
    "web_search": {"query": "protein"},
}


@pytest.mark.parametrize("name", sorted(VALID))
async def test_fuzzed_arguments_never_raise(name):
    r = random.Random(f"fuzz-{name}")
    outcomes = set()
    for _ in range(300):
        ctx = ToolContext(mode="guest", trace_id="t", search_keys=["k"],
                          search=WebSearch(FakeSearchClient(), FakeStore(room=10**6), Clock()))
        out = await TOOLS[name].run(_mutate(r, VALID[name]), ctx)
        assert isinstance(out, dict)
        json.dumps(out)  # always JSON-safe for the provider
        outcomes.add(out.get("status", "entries"))
        for staged in ctx.staged_writes:
            StagedWrite.model_validate(staged.model_dump())  # only valid writes are staged
    assert "invalid_arguments" in outcomes  # the fuzzer did reach the validation path


async def test_cache_is_bounded_and_evicts_oldest(monkeypatch):
    monkeypatch.setattr(ws, "CACHE_MAX_ENTRIES", 50)
    client = FakeSearchClient()
    service = WebSearch(client, FakeStore(room=10**6), Clock())
    for i in range(80):
        await SEARCH.run({"query": f"q{i}"}, ToolContext(mode="guest", trace_id="t",
                                                         search=service, search_keys=["k"]))
    assert len(service._cache) == 50
    calls = len(client.calls)
    await SEARCH.run({"query": "q79"}, ToolContext(mode="guest", trace_id="t", search=service,
                                                  search_keys=["k"]))
    await SEARCH.run({"query": "q0"}, ToolContext(mode="guest", trace_id="t", search=service,
                                                 search_keys=["k"]))
    assert len(client.calls) == calls + 1  # newest still cached, oldest evicted


@pytest.mark.parametrize(
    "variant",
    ["दाल   प्रोटीन", "दाल प्रोटीन​", "ＤＡＬ protein", "DAL PROTEIN"],
)
async def test_unicode_variants_share_a_cache_entry(variant):
    base = "दाल प्रोटीन" if "प्रोटीन" in variant else "dal protein"
    client = FakeSearchClient()
    service = WebSearch(client, FakeStore(), Clock())
    for query in (base, variant):
        await SEARCH.run({"query": query}, ToolContext(mode="guest", trace_id="t",
                                                      search=service, search_keys=["k"]))
    assert len(client.calls) == 1


async def test_failing_gate_stages_nothing():
    async def broken_gate(kind, args, ctx):
        raise RuntimeError("gate unavailable")

    ctx = ToolContext(mode="guest", trace_id="t", gate_write=broken_gate)
    with pytest.raises(RuntimeError):
        await TOOLS["log_meal"].run(WRITES["log_meal"][1], ctx)
    assert ctx.staged_writes == []  # fails closed: the agent treats this as a failure


async def test_concurrent_identical_searches_documented():
    """Two identical queries at the same moment both miss the cache and both call.
    Accepted: at most one extra credit, and the 2-per-request limit still applies."""
    client = FakeSearchClient(delay=0.05)
    store = FakeStore()
    service = WebSearch(client, store, Clock())
    ctxs = [ToolContext(mode="guest", trace_id=f"t{i}", search=service, search_keys=["k"])
            for i in range(2)]
    await asyncio.gather(*(SEARCH.run({"query": "same"}, c) for c in ctxs))
    assert len(client.calls) == 2 and store.used == 2
    await SEARCH.run({"query": "same"}, ToolContext(mode="guest", trace_id="t3", search=service,
                                                    search_keys=["k"]))
    assert len(client.calls) == 2  # cached afterwards
