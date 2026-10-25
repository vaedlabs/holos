"""The provider scenarios, shared by the recorder and the contract tests (Plan P2.3)."""

import io
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from PIL import Image

from app.agents.schemas import (
    GetRecentLogsArgs,
    MentalReply,
    NutritionReply,
    PhysicalReply,
    llm_json_schema,
)
from app.providers import (
    GenerateOptions,
    ImageInput,
    LLMResult,
    ToolResult,
    ToolSpec,
    Turn,
)
from app.providers.gemini import GeminiProvider
from app.providers.openai import OpenAIProvider

MODELS = {"openai": "gpt-6-luna", "gemini": "gemini-3.5-flash-lite"}
REPLY_CAP = {"openai": 1200, "gemini": 1400}
PROVIDERS = ("openai", "gemini")

RECENT_LOGS = ToolSpec(
    name="get_recent_logs",
    description="The user's recent workout, meal or practice logs, newest first.",
    parameters=llm_json_schema(GetRecentLogsArgs),
)
LOG_ENTRIES = {"entries": [{"date": "2026-10-24", "meal_type": "lunch",
                            "foods": "dal, rice", "calories": 520, "notes": None}]}


def make_provider(name: str, api_key: str, transport: httpx.AsyncBaseTransport):
    client = httpx.AsyncClient(transport=transport, timeout=30)
    cls = OpenAIProvider if name == "openai" else GeminiProvider
    return cls(api_key, http_client=client)


def options(name: str, max_output_tokens: int | None = None) -> GenerateOptions:
    return GenerateOptions(model=MODELS[name],
                           max_output_tokens=max_output_tokens or REPLY_CAP[name],
                           reasoning="none", timeout_s=30)


def red_square() -> ImageInput:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), (220, 20, 20)).save(out, format="JPEG", quality=85)
    return ImageInput(out.getvalue(), "image/jpeg")


@dataclass(frozen=True)
class Scenario:
    name: str
    run: Callable[[object, str], Awaitable[list[LLMResult]]]


async def structured_physical(provider, name):
    return [await provider.generate(
        [Turn("user", "A 2-exercise upper-body plan with no equipment, for a beginner.")],
        options=options(name), system="You are a careful fitness coach. Reply in the schema.",
        schema=PhysicalReply)]


async def structured_nutrition(provider, name):
    return [await provider.generate(
        [Turn("user", "Plan a high-protein vegetarian lunch with 2 foods.")],
        options=options(name), system="You are a nutrition coach. Reply in the schema.",
        schema=NutritionReply)]


async def structured_mental(provider, name):
    return [await provider.generate(
        [Turn("user", "One 5-minute practice for stress before an exam.")],
        options=options(name), system="You are a calm wellbeing coach. Reply in the schema.",
        schema=MentalReply)]


async def tool_call(provider, name):
    question = Turn("user", "What did I eat in the last 7 days? Use the tool, then answer "
                            "in one sentence.")
    first = await provider.generate([question], options=options(name),
                                    tools=[RECENT_LOGS])
    call = first.tool_calls[0]
    second = await provider.generate(
        [question, first.turn, ToolResult(call.id, call.name, LOG_ENTRIES)],
        options=options(name), tools=[RECENT_LOGS])
    return [first, second]


async def image(provider, name):
    return [await provider.generate(
        [Turn("user", "What colour is this square? Answer with one word.",
              images=(red_square(),))],
        options=options(name))]


async def truncated(provider, name):
    return [await provider.generate([Turn("user", "Write 300 words about sleep.")],
                                    options=options(name, max_output_tokens=16))]


SCENARIOS = [Scenario(f.__name__, f) for f in
             (structured_physical, structured_nutrition, structured_mental, tool_call, image,
              truncated)]

# Gemini rejects the physical schema ("too many states for serving": 124 exercise ids
# plus numeric bounds, Part D). C.9 never sends physical replies to Gemini; the real
# 400 is kept as an error-mapping fixture.
EXPECTED_ERRORS = {("gemini", "structured_physical"): "BadRequest"}
