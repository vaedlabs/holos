"""One real call per provider (Plan P2.3). Nightly or by hand; never on push.

    cd backend && pytest -m paid tests/paid/test_providers_live.py
"""

import os

import httpx
import pytest
from dotenv import load_dotenv

from app.agents.schemas import MentalReply, NutritionReply
from app.providers import GenerateOptions, Turn
from app.providers.gemini import GeminiProvider
from app.providers.openai import OpenAIProvider

pytestmark = [pytest.mark.paid, pytest.mark.asyncio]

load_dotenv(".env")


def _key(name: str) -> str:
    key = os.getenv(name, "")
    if not key or "placeholder" in key or key.startswith("sk-ci"):
        pytest.skip(f"{name} is not a real key")
    return key


async def test_openai_live_mental_reply():
    provider = OpenAIProvider(_key("OPENAI_API_KEY"), http_client=httpx.AsyncClient(timeout=30))
    result = await provider.generate(
        [Turn("user", "One 3-minute practice to calm down before sleep.")],
        options=GenerateOptions(model="gpt-6-luna", max_output_tokens=1200),
        system="You are a calm wellbeing coach. Reply in the schema.", schema=MentalReply)
    assert isinstance(result.parsed, MentalReply)
    assert result.usage.tokens_in > 0 and not result.truncated


async def test_gemini_live_nutrition_reply():
    provider = GeminiProvider(_key("GOOGLE_GEMINI_API_KEY"),
                              http_client=httpx.AsyncClient(timeout=30))
    result = await provider.generate(
        [Turn("user", "Suggest one high-protein vegetarian snack.")],
        options=GenerateOptions(model="gemini-3.5-flash-lite", max_output_tokens=1400),
        system="You are a nutrition coach. Reply in the schema.", schema=NutritionReply)
    assert isinstance(result.parsed, NutritionReply)
    assert result.usage.tokens_in > 0 and not result.truncated
