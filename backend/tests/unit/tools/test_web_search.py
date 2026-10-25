"""web_search: cache, credits, caps, timeouts and the untrusted flag (Plan P2.2)."""

import pytest

from app.agents.tools import AGENT_TOOLS, WebSearch
from app.agents.tools import web_search as ws

from .conftest import Clock, FakeSearchClient, FakeStore

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

TOOL = next(t for t in AGENT_TOOLS["physical"] if t.name == "web_search")


def _service(client=None, store=None, clock=None):
    return WebSearch(client or FakeSearchClient(), store or FakeStore(), clock or Clock())


async def test_result_sets_untrusted_and_records_sources(ctx):
    ctx.search = _service()
    out = await TOOL.run({"query": "protein in dal"}, ctx)
    assert out["status"] == "ok"
    assert [r["id"] for r in out["results"]] == ["s1"]  # the ftp link was dropped
    assert ctx.untrusted is True
    assert [(s.id, s.url) for s in ctx.sources] == [("s1", "https://example.org/dal")]


async def test_client_called_with_basic_depth_and_five_results(ctx):
    client = FakeSearchClient()
    ctx.search = _service(client)
    await TOOL.run({"query": "q"}, ctx)
    assert client.calls == [("q", {"search_depth": "basic", "max_results": 5})]


async def test_cache_hit_makes_no_call_and_uses_no_credit(ctx):
    client, store = FakeSearchClient(), FakeStore()
    service = _service(client, store)
    ctx.search = service
    await TOOL.run({"query": "Protein in DAL "}, ctx)
    second = ctx.__class__(mode="guest", trace_id="t2", search_keys=["k"], search=service)
    out = await TOOL.run({"query": "protein   in dal"}, second)  # same after normalising
    assert len(client.calls) == 1
    assert store.used == 1 and store.reserved == 0
    assert out["status"] == "ok" and second.untrusted is True


async def test_cache_expires_after_an_hour(ctx):
    client, clock = FakeSearchClient(), Clock()
    service = _service(client, clock=clock)
    ctx.search = service
    await TOOL.run({"query": "q"}, ctx)
    clock.now += ws.CACHE_TTL_SECONDS + 1
    later = ctx.__class__(mode="guest", trace_id="t2", search_keys=["k"], search=service)
    await TOOL.run({"query": "q"}, later)
    assert len(client.calls) == 2


async def test_timeout_returns_unavailable_and_counts_the_credit(ctx, monkeypatch):
    monkeypatch.setattr(ws, "TIMEOUT_SECONDS", 0.05)
    store = FakeStore()
    ctx.search = _service(FakeSearchClient(delay=1.0), store)
    out = await TOOL.run({"query": "q"}, ctx)
    assert out == {"status": "search_unavailable"}
    assert store.used == 1 and store.reserved == 0
    assert ctx.untrusted is False


async def test_provider_error_returns_unavailable_and_counts_the_credit(ctx):
    store = FakeStore()
    ctx.search = _service(FakeSearchClient(error=RuntimeError("502")), store)
    assert await TOOL.run({"query": "q"}, ctx) == {"status": "search_unavailable"}
    assert store.used == 1


async def test_cap_returns_unavailable_without_a_call(ctx):
    client = FakeSearchClient()
    ctx.search = _service(client, FakeStore(room=0))
    assert await TOOL.run({"query": "q"}, ctx) == {"status": "search_unavailable"}
    assert client.calls == []
    assert ctx.untrusted is False  # a capped search doesn't make the turn untrusted (C.13)


async def test_two_searches_per_request(ctx):
    client = FakeSearchClient()
    ctx.search = _service(client)
    results = [await TOOL.run({"query": f"q{i}"}, ctx) for i in range(3)]
    assert [r["status"] for r in results] == ["ok", "ok", "search_unavailable"]
    assert len(client.calls) == 2
    assert [s.id for s in ctx.sources] == ["s1", "s2"]  # ids stay unique across searches


async def test_empty_results_do_not_mark_untrusted(ctx):
    ctx.search = _service(FakeSearchClient(results=[]))
    out = await TOOL.run({"query": "q"}, ctx)
    assert out == {"status": "ok", "results": []} and ctx.untrusted is False


async def test_snippets_are_shortened(ctx):
    long = [{"title": "t", "url": "https://x.org", "content": "word " * 200}]
    ctx.search = _service(FakeSearchClient(results=long))
    out = await TOOL.run({"query": "q"}, ctx)
    assert len(out["results"][0]["snippet"]) <= ws.SNIPPET_CHARS


async def test_no_search_service_means_unavailable(ctx):
    assert await TOOL.run({"query": "q"}, ctx) == {"status": "search_unavailable"}


async def test_query_too_long_is_invalid(ctx):
    ctx.search = _service()
    out = await TOOL.run({"query": "x" * 201}, ctx)
    assert out["status"] == "invalid_arguments"


class _RawClient:
    def __init__(self, raw):
        self.raw, self.calls = raw, 0

    async def search(self, query, **kwargs):
        self.calls += 1
        return self.raw


@pytest.mark.parametrize(
    "raw",
    [None, [], "oops", {}, {"results": None}, {"results": {"a": 1}}, {"results": "x"}],
    ids=["none", "list", "string", "no-results", "results-none", "results-dict", "results-str"],
)
async def test_unexpected_response_shape_is_unavailable_not_a_crash(ctx, raw):
    store = FakeStore()
    ctx.search = WebSearch(_RawClient(raw), store, Clock())
    assert await TOOL.run({"query": "q"}, ctx) == {"status": "search_unavailable"}
    assert store.used == 1  # the call happened, so the credit counts
    assert ctx.untrusted is False


@pytest.mark.parametrize(
    ("item", "kept"),
    [(None, False), ("x", False), (42, False),
     ({"title": "t", "url": None}, False), ({"title": "", "url": "https://a.b"}, False),
     ({"title": "t", "url": "javascript:alert(1)"}, False),
     ({"title": "t", "url": "data:text/html,x"}, False),
     ({"title": 5, "url": "https://a.b"}, True),
     ({"title": "t", "url": "https://a.b", "content": {"x": 1}}, True)],
)
async def test_malformed_items_are_skipped(ctx, item, kept):
    good = {"title": "good", "url": "https://good.org", "content": "fine"}
    ctx.search = WebSearch(_RawClient({"results": [item, good]}), FakeStore(), Clock())
    out = await TOOL.run({"query": "q"}, ctx)
    titles = [r["title"] for r in out["results"]]
    assert titles[-1] == "good"
    assert len(titles) == (2 if kept else 1)
    for r in out["results"]:
        assert isinstance(r["snippet"], str)
