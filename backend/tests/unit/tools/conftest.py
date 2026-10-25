"""Fakes for tool tests: no network, no database."""

import asyncio
from dataclasses import dataclass, field

import pytest

from app.agents.tools import ToolContext


class FakeSearchClient:
    def __init__(self, results=None, delay: float = 0.0, error: Exception | None = None):
        self.results = results if results is not None else [
            {"title": "Protein in dal", "url": "https://example.org/dal", "content": "Dal has "
             "about 9 g of protein per cooked cup."},
            {"title": "Not a link", "url": "ftp://example.org/x", "content": "dropped"},
        ]
        self.delay, self.error, self.calls = delay, error, []

    async def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return {"results": self.results}


@dataclass
class FakeStore:
    """Stands in for StateStore.reserve / settle."""

    room: int = 10
    reserved: int = 0
    used: int = 0
    settled: list = field(default_factory=list)

    async def reserve(self, keys, usd=None, credits=0):
        if self.reserved + self.used + credits > self.room:
            return None
        self.reserved += credits
        return ("reservation", credits)

    async def settle(self, reservation, usd, tokens_in=0, tokens_out=0, credits=0):
        self.reserved -= reservation[1]
        self.used += credits
        self.settled.append(credits)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def ctx():
    return ToolContext(mode="guest", trace_id="t1", search_keys=["k"])
