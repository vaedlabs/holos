"""One real call per reply schema on the provider (Plan P2.3). Nightly or by hand;
never on push.

    cd backend && pytest -m paid tests/paid/test_providers_live.py
"""

import os

import httpx
import pytest
from dotenv import load_dotenv

from app.agents.schemas import REPLY_MODELS, REPLY_TOKEN_CAP
from app.config.limits import REASONING_ALLOWANCE_LOW
from app.providers import GenerateOptions, Turn
from app.providers.openai import OpenAIProvider

pytestmark = pytest.mark.paid

load_dotenv(".env")


def _key(name: str) -> str:
    key = os.getenv(name, "")
    if not key or "placeholder" in key or key.startswith("sk-ci"):
        pytest.skip(f"{name} is not a real key")
    return key


# One message per reply schema: the schema as sent (llm_json_schema) works live
ASKS = {
    "physical": "A 10-minute home workout for a beginner.",
    "nutrition": "Suggest one high-protein vegetarian snack.",
    "mental": "One 3-minute practice to calm down before sleep.",
}


@pytest.mark.parametrize("agent", list(REPLY_MODELS))
async def test_openai_live_reply(agent):
    provider = OpenAIProvider(_key("OPENAI_API_KEY"), http_client=httpx.AsyncClient(timeout=60))
    result = await provider.generate(
        [Turn("user", ASKS[agent])],
        options=GenerateOptions(model="gpt-6-luna", max_output_tokens=REPLY_TOKEN_CAP[agent]
                                + REASONING_ALLOWANCE_LOW, reasoning="low"),
        system=f"You are a {agent} coach. Reply in the schema.", schema=REPLY_MODELS[agent])
    assert isinstance(result.parsed, REPLY_MODELS[agent])
    assert result.usage.tokens_in > 0 and not result.truncated
