"""The router on real people's conversations (Plan Part E #36). Nightly or by hand.

    cd backend && pytest -m paid tests/paid/test_router_live.py     # 215 calls, about $0.02

Routes the held-out persona conversations (tests/scenarios/conversations_blind.jsonl)
through the real Router on the production path. Measured 28-29 Oct 2026: 208 of 215
right on one run, 614 of 645 over three. Hindi is never refused (the router errors
first); English mixed with German or Spanish may be, if the model insists twice.
"""

import asyncio
import os
import time

import httpx
import pytest
from dotenv import load_dotenv

from app.config.speeds import ROUTER
from app.orchestration.router import Router, language
from app.providers import (
    Breakers,
    CallPlan,
    FairScheduler,
    GenerateOptions,
    ResilientProvider,
    Route,
)
from app.providers.openai import OpenAIProvider
from tests.scenarios.scenarios import HERE, conversations

pytestmark = [pytest.mark.paid, pytest.mark.asyncio]

load_dotenv(".env")

MIN_RIGHT = 0.93  # measured 0.95-0.97; below this, something changed


def _key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or "placeholder" in key or key.startswith("sk-ci"):
        pytest.skip("OPENAI_API_KEY is not a real key")
    return key


async def test_router_on_held_out_conversations():
    options = GenerateOptions(model="gpt-6-luna", max_output_tokens=300, timeout_s=5)
    llm = ResilientProvider(
        Route(OpenAIProvider(_key(), http_client=httpx.AsyncClient(timeout=30)), options),
        None, Breakers(), scheduler=FairScheduler())
    router = Router(llm)
    convos = conversations(HERE / "conversations_blind.jsonl")
    gate = asyncio.Semaphore(8)

    async def one(ci, ti):
        convo, turn = convos[ci], convos[ci].turns[ti]
        async with gate:
            decision = await router.route(
                turn.user, profile=convo.persona.profile, history=convo.history_before(ti),
                has_image=turn.spec.image, agents=list(turn.spec.app_agents) or None,
                plan=CallPlan(deadline=time.monotonic() + 5, speed=ROUTER,
                              principal=f"{ci}-{ti}", kind="router"))
        return turn, convo.right(ti, decision.kind, decision.agents), decision

    results = await asyncio.gather(*(one(ci, ti) for ci, c in enumerate(convos)
                                     for ti in range(len(c.turns))))
    right = sum(ok for _, ok, _ in results)
    assert right / len(results) >= MIN_RIGHT, f"{right} of {len(results)} right"
    refused = [t.user for t, _, d in results
               if d.kind == "other_language" and language(t.user) == "hindi"]
    assert refused == [], "a supported language was called another one"
    leaked = [t.user for t, _, d in results if language(t.user) == "other" and d.agents]
    assert leaked == [], "another language reached a coach"
