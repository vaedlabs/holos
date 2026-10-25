"""No tool may block the event loop for more than 50 ms (Plan P2.2).

asyncio debug mode logs "Executing <...> took N seconds" for any step slower than
loop.slow_callback_duration. The check runs every tool and fails on such a log.
"""

import asyncio
import logging
import time

import pytest

from app.agents.tools import AGENT_TOOLS, Tool, ToolContext, WebSearch

from .conftest import Clock, FakeSearchClient, FakeStore
from .test_write_and_read_tools import WRITES

pytestmark = pytest.mark.unit

TOOLS = {t.name: t for tools in AGENT_TOOLS.values() for t in tools}


def _slow_steps(caplog, coro_factory) -> list[str]:
    loop = asyncio.new_event_loop()
    loop.set_debug(True)
    loop.slow_callback_duration = 0.05
    try:
        with caplog.at_level(logging.WARNING, logger="asyncio"):
            loop.run_until_complete(coro_factory())
    finally:
        loop.close()
    return [r.getMessage() for r in caplog.records if "took" in r.getMessage()]


async def _run_every_tool():
    service = WebSearch(FakeSearchClient(delay=0.01), FakeStore(), Clock())
    ctx = ToolContext(mode="guest", trace_id="t", search=service, search_keys=["k"])
    await TOOLS["web_search"].run({"query": "q"}, ctx)
    await TOOLS["get_recent_logs"].run({"kind": "workout", "days": 7}, ctx)
    for name, (_, args, _) in WRITES.items():
        await TOOLS[name].run(args, ctx)


def test_no_tool_blocks_the_loop(caplog):
    assert _slow_steps(caplog, _run_every_tool) == []


def test_the_check_catches_a_blocking_tool(caplog):
    async def blocking(args, ctx):
        time.sleep(0.1)  # a synchronous call inside an async tool
        return {}

    tool = Tool("bad", "read", "", TOOLS["get_recent_logs"].args_model, blocking)

    async def run():
        await tool.run({"kind": "workout", "days": 1}, ToolContext(mode="guest", trace_id="t"))

    assert _slow_steps(caplog, run), "debug mode should have reported the blocking call"
