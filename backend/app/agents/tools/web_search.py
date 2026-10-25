"""web_search (Plan C.10, C.13, P2.2).

One shared AsyncTavilyClient, basic depth, 5 results, 5 s timeout, a 1-hour cache
on the normalised query, and a search credit reserved before each real call.

* Cache hit: no call, no credit.
* Cap reached (per request, session, IP, account or global): `search_unavailable`
  without a call. The turn is not marked untrusted (C.13).
* Timeout or error: `search_unavailable`, and the credit counts as used (C.13).
* Any result: the turn becomes untrusted, so writes need confirmation (C.17).
"""

import asyncio
import os
import time
from collections import OrderedDict
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Protocol

from pydantic import ValidationError

from app.agents.schemas import Source, WebSearchArgs
from app.config import limits
from app.data.state_store import StateStore
from app.guardrails.normalise import normalise_text

from .base import Tool, ToolContext

CACHE_TTL_SECONDS = 3600
CACHE_MAX_ENTRIES = 500
TIMEOUT_SECONDS = 5.0
MAX_RESULTS = 5
SNIPPET_CHARS = 300

UNAVAILABLE = {"status": "search_unavailable"}


class SearchClient(Protocol):
    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]: ...


class WebSearch:
    """The search service shared by all requests in a process."""

    def __init__(
        self,
        client: SearchClient,
        store: StateStore | None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._client = client
        self._store = store
        self._clock = clock
        self._cache: OrderedDict[str, tuple[float, list[dict[str, str]]]] = OrderedDict()

    def _cached(self, key: str) -> list[dict[str, str]] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires, results = entry
        if expires <= self._clock():
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return results

    def _remember(self, key: str, results: list[dict[str, str]]) -> None:
        self._cache[key] = (self._clock() + CACHE_TTL_SECONDS, results)
        self._cache.move_to_end(key)
        while len(self._cache) > CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)

    async def search(self, query: str, ctx: ToolContext) -> dict[str, Any]:
        if ctx.searches_used >= limits.SEARCHES_PER_REQUEST:
            return UNAVAILABLE
        ctx.searches_used += 1

        key = normalise_text(query)
        results = self._cached(key)
        if results is None:
            results = await self._fetch(query, ctx)
            if results is None:
                return UNAVAILABLE
            self._remember(key, results)
        return _answer(results, ctx)

    async def _fetch(self, query: str, ctx: ToolContext) -> list[dict[str, str]] | None:
        reservation = None
        if self._store is not None and ctx.search_keys:
            reservation = await self._store.reserve(ctx.search_keys, credits=1)
            if reservation is None:
                return None  # a cap is reached: no call
        try:
            raw = await asyncio.wait_for(
                self._client.search(query, search_depth="basic", max_results=MAX_RESULTS),
                timeout=TIMEOUT_SECONDS,
            )
        except Exception:  # timeout or provider error: the credit is used (C.13)
            return None
        finally:
            if reservation is not None:
                await self._store.settle(reservation, Decimal("0"), credits=1)
        return _parse(raw)


def _parse(raw: Any) -> list[dict[str, str]] | None:
    """Results from a Tavily response. None (search unavailable) if the response has an
    unexpected shape; malformed items are skipped. A bad response must never crash
    the agent's tool round."""
    if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
        return None
    results = []
    for item in raw["results"][:MAX_RESULTS]:
        if not isinstance(item, dict):
            continue
        title, url = str(item.get("title") or "")[:200], str(item.get("url") or "")
        if not url.startswith(("https://", "http://")) or not title:
            continue
        content = item.get("content")
        snippet = " ".join(content.split())[:SNIPPET_CHARS] if isinstance(content, str) else ""
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


def _answer(results: list[dict[str, str]], ctx: ToolContext) -> dict[str, Any]:
    """Number results with turn-unique ids (s1, s2, ...) and record them as sources."""
    out = []
    for r in results:
        source_id = f"s{len(ctx.sources) + 1}"
        try:
            ctx.sources.append(Source(id=source_id, title=r["title"], url=r["url"]))
        except ValidationError:
            continue
        out.append({"id": source_id, **r})
    if out:
        ctx.untrusted = True
    return {"status": "ok", "results": out}


_shared: WebSearch | None = None


def get_web_search(store: StateStore | None) -> WebSearch:
    """The process-wide search service with one shared Tavily client."""
    global _shared
    if _shared is None:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=os.environ["TAVILY_API_KEY"],
                                   timeout=int(TIMEOUT_SECONDS))
        _shared = WebSearch(client, store)
    return _shared


async def web_search(args: WebSearchArgs, ctx: ToolContext) -> dict[str, Any]:
    if ctx.search is None:
        return UNAVAILABLE
    return await ctx.search.search(args.query, ctx)


WEB_SEARCH = Tool(
    name="web_search",
    kind="search",
    description="Search the web. Cite results by their id in source_ids.",
    args_model=WebSearchArgs,
    handler=web_search,
)
