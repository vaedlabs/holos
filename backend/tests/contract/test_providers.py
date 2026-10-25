"""The same contract tests on OpenAIProvider and GeminiProvider, replaying recorded HTTP
(Plan P2.3). No network. Re-record with `python -m tests.contract.record_providers`.
"""

import httpx
import pytest

from app.agents.schemas import (
    GetRecentLogsArgs,
    MentalReply,
    NutritionReply,
    PhysicalReply,
)
from app.providers import (
    BadRequest,
    MalformedOutput,
    ModelTurn,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
    ToolCall,
    ToolResult,
    Turn,
)
from app.providers.gemini import _to_steps
from app.providers.openai import _to_input

from .http_fixtures import RaisingTransport, ReplayTransport, load
from .provider_scenarios import (
    EXPECTED_ERRORS,
    PROVIDERS,
    image,
    make_provider,
    options,
    structured_mental,
    structured_nutrition,
    structured_physical,
    tool_call,
    truncated,
)

pytestmark = [pytest.mark.contract, pytest.mark.asyncio]


def _replay(provider_name: str, scenario: str, check_body: bool = True):
    transport = ReplayTransport(load(provider_name, scenario), check_body=check_body)
    return make_provider(provider_name, "test-key", transport), transport


def _recorded_usage(provider_name: str, scenario: str) -> list[dict]:
    return [ex["response"]["body"].get("usage") for ex in load(provider_name, scenario)]


@pytest.mark.parametrize("provider_name", PROVIDERS)
@pytest.mark.parametrize(
    ("run", "model"),
    [(structured_nutrition, NutritionReply), (structured_mental, MentalReply),
     (structured_physical, PhysicalReply)],
    ids=["nutrition", "mental", "physical"],
)
async def test_structured_parse(provider_name, run, model):
    provider, transport = _replay(provider_name, run.__name__)
    if (provider_name, run.__name__) in EXPECTED_ERRORS:
        with pytest.raises(BadRequest, match="too many states"):
            await run(provider, provider_name)
        return
    [result] = await run(provider, provider_name)
    assert isinstance(result.parsed, model)
    assert result.parsed.kind in ("plan", "answer", "clarify", "log_ack")
    assert result.usage.tokens_in > 0 and result.usage.tokens_out > 0
    assert result.turn is not None and result.turn.provider == provider_name
    assert transport.remaining == 0


@pytest.mark.parametrize("provider_name", PROVIDERS)
async def test_nutrition_reply_parses_on_both_providers(provider_name):
    """Nutrition runs on Gemini with an OpenAI fallback (C.9): both must parse it."""
    provider, _ = _replay(provider_name, "structured_nutrition")
    [result] = await structured_nutrition(provider, provider_name)
    reply = result.parsed
    assert isinstance(reply, NutritionReply) and reply.items
    for food in reply.items:
        assert 1 <= len(food.ingredients) <= 8  # limits enforced by Pydantic, not the provider


@pytest.mark.parametrize("provider_name", PROVIDERS)
async def test_tool_call_round_trip(provider_name):
    provider, transport = _replay(provider_name, "tool_call")
    first, second = await tool_call(provider, provider_name)
    [call] = first.tool_calls
    assert call.name == "get_recent_logs"
    GetRecentLogsArgs.model_validate(call.arguments)
    assert first.parsed is None
    assert second.tool_calls == () and second.text
    assert transport.remaining == 0  # the second request matched the recording exactly


@pytest.mark.parametrize("provider_name", PROVIDERS)
async def test_token_usage_matches_the_response(provider_name):
    provider, _ = _replay(provider_name, "structured_mental")
    [result] = await structured_mental(provider, provider_name)
    [usage] = _recorded_usage(provider_name, "structured_mental")
    if provider_name == "openai":
        assert (result.usage.tokens_in, result.usage.tokens_out) == (
            usage["input_tokens"], usage["output_tokens"])
    else:
        assert result.usage.tokens_in == usage["total_input_tokens"]
        assert result.usage.tokens_out == (usage["total_output_tokens"]
                                           + usage.get("total_thought_tokens", 0))


@pytest.mark.parametrize("provider_name", PROVIDERS)
async def test_image_input(provider_name):
    provider, transport = _replay(provider_name, "image")
    [result] = await image(provider, provider_name)
    assert "red" in (result.text or "").lower()
    body = str(transport.requests[0]["body"])
    assert ("input_image" in body) if provider_name == "openai" else ("'image'" in body)


@pytest.mark.parametrize("provider_name", PROVIDERS)
async def test_truncated_reply_is_flagged(provider_name):
    provider, _ = _replay(provider_name, "truncated")
    [result] = await truncated(provider, provider_name)
    assert result.truncated is True


@pytest.mark.parametrize("provider_name", PROVIDERS)
async def test_truncated_reply_with_schema_is_malformed(provider_name):
    provider, _ = _replay(provider_name, "truncated", check_body=False)
    with pytest.raises(MalformedOutput, match="cut off"):
        await provider.generate([Turn("user", "x")], options=options(provider_name, 16),
                                schema=MentalReply)


@pytest.mark.parametrize("provider_name", PROVIDERS)
@pytest.mark.parametrize(
    ("scenario", "error"),
    [("rate_limited", RateLimited), ("server_error", ProviderUnavailable)],
)
async def test_http_errors_map(provider_name, scenario, error):
    provider, _ = _replay(provider_name, scenario)
    with pytest.raises(error) as exc:
        await provider.generate([Turn("user", "hi")], options=options(provider_name))
    assert exc.value.provider == provider_name
    if error is RateLimited:
        assert exc.value.retry_after == 7.0
    assert exc.value.retryable


async def test_openai_bad_request_maps():
    provider, _ = _replay("openai", "bad_request")
    with pytest.raises(BadRequest) as exc:
        await provider.generate([Turn("user", "hi")], options=options("openai"))
    assert not exc.value.retryable


@pytest.mark.parametrize("provider_name", PROVIDERS)
@pytest.mark.parametrize(
    ("raised", "error"),
    [(httpx.ReadTimeout("slow"), ProviderTimeout), (httpx.ConnectError("down"),
                                                     ProviderUnavailable)],
    ids=["timeout", "connection"],
)
async def test_transport_errors_map(provider_name, raised, error):
    provider = make_provider(provider_name, "test-key", RaisingTransport(raised))
    with pytest.raises(error):
        await provider.generate([Turn("user", "hi")], options=options(provider_name))


# --- A conversation can move between providers (fallback mid-turn) ---

CALL = ToolCall(id="c1", name="get_recent_logs", arguments={"kind": "meal", "days": 7})


def test_openai_rebuilds_a_gemini_turn():
    turn = ModelTurn(provider="gemini", items=({"type": "thought"},), tool_calls=(CALL,),
                     text=None)
    items = _to_input(turn)
    assert items == [{"type": "function_call", "call_id": "c1", "name": "get_recent_logs",
                      "arguments": '{"kind": "meal", "days": 7}'}]


def test_gemini_rebuilds_an_openai_turn():
    turn = ModelTurn(provider="openai", items=({"type": "reasoning"},), tool_calls=(CALL,),
                     text="Checking your logs.")
    steps = _to_steps(turn)
    assert steps[0]["type"] == "model_output"
    assert steps[1] == {"type": "function_call", "id": "c1", "name": "get_recent_logs",
                        "arguments": {"kind": "meal", "days": 7}}


@pytest.mark.parametrize("to_wire", [_to_input, _to_steps], ids=["openai", "gemini"])
def test_tool_results_are_json(to_wire):
    [item] = to_wire(ToolResult("c1", "get_recent_logs", {"entries": []}))
    assert '{"entries": []}' in str(item)
