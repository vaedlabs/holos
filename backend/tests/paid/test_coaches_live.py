"""The three coaches on real people's conversations (Plan P4.5, Part E #36). Nightly or by
hand.

    cd backend && pytest -m paid tests/paid/test_coaches_live.py     # ~120 runs, ~$0.04

Every coaching turn of the held-out persona conversations, on the production path
(OpenAI streaming, ResilientProvider, gate, tools), with the labelled coaches and the
other coaches named. Measured 29 Oct 2026 (Part D): 1 error in 191 runs, every log staged,
replies in the person's language. Quality was graded separately (Part D).
"""

import asyncio
import os
import time

import httpx
import pytest
from dotenv import load_dotenv

from app.agents.base import AgentRun
from app.agents.mental import MentalAgent
from app.agents.nutrition import NutritionAgent
from app.agents.physical import PhysicalAgent
from app.agents.tools import ToolContext
from app.providers import Breakers, FairScheduler, ResilientProvider, Route
from app.providers.openai import OpenAIProvider
from tests.scenarios.scenarios import HERE, conversations

pytestmark = [pytest.mark.paid, pytest.mark.asyncio]

load_dotenv(".env")

CLASSES = {"physical": PhysicalAgent, "nutrition": NutritionAgent, "mental": MentalAgent}


def _key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or "placeholder" in key or key.startswith("sk-ci"):
        pytest.skip("OPENAI_API_KEY is not a real key")
    return key


async def test_coaches_on_held_out_conversations():
    provider = OpenAIProvider(_key(), http_client=httpx.AsyncClient(timeout=120))
    breakers, scheduler = Breakers(), FairScheduler()
    agents = {d: c(ResilientProvider(Route(provider, c.options()), None, breakers,
                                     scheduler=scheduler)) for d, c in CLASSES.items()}
    gate = asyncio.Semaphore(8)
    convos = conversations(HERE / "conversations_blind.jsonl")
    jobs = [(ci, ti, a, c, t) for ci, c in enumerate(convos) for ti, t in enumerate(c.turns)
            if t.spec.kind == "coaching" and not t.spec.image for a in t.spec.agents]

    async def one(ci, ti, agent, convo, turn):
        async with gate:
            return turn, await agents[agent].run(AgentRun(
                message=turn.user, profile=convo.persona.profile,
                history=convo.history_before(ti),
                tools=ToolContext(mode="guest", trace_id=f"{ci}-{ti}"),
                deadline=time.monotonic() + 60, principal=f"{ci}-{ti}",
                others=tuple(a for a in turn.spec.agents if a != agent)))

    results = await asyncio.gather(*(one(*j) for j in jobs))
    # OpenAI fails now and then (live: 1 in 191 after retries): allow 2%
    errors = [r.error for _, r in results if r.error]
    assert len(errors) <= max(1, len(results) // 50), errors
    logs = [r for _, r in results if r.reply.kind == "log_ack"]
    assert logs and all(r.staged_writes for r in logs), "a log_ack without a staged write"
