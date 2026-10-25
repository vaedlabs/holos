"""GeminiProvider: the Interactions API through google-genai's async client (Plan C.9).

The async client covers Interactions (Part D), so no thread is needed. Requests
are stateless (store=False): the whole conversation is sent each time, including
the model's thought steps, which Gemini needs back. SDK retries are off.
"""

import base64
import json
from typing import Any

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

# The Interactions client raises these wrapped errors; the package doesn't export them
# publicly (Part E #15). The contract tests replay 429/500/400 through the SDK, so a
# change here fails CI instead of escaping as an unmapped error.
from google.genai._gaos.lib import compat_errors
from pydantic import BaseModel

from app.agents.schemas import llm_json_schema

from .base import (
    BadRequest,
    GenerateOptions,
    LLMResult,
    MalformedOutput,
    Message,
    ModelTurn,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
    ToolCall,
    ToolResult,
    ToolSpec,
    Turn,
    Usage,
    parse_reply,
)

# Gemini has no "none"; "minimal" is its lowest thinking level
THINKING = {"none": "minimal", "low": "low", "medium": "medium", "high": "high"}


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, http_client: httpx.AsyncClient | None = None):
        options = types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1),
            httpx_async_client=http_client,
        )
        self._client = genai.Client(api_key=api_key, http_options=options)
        # The Interactions client retries 408/409/429/5xx up to 4 times by default and
        # ignores HttpOptions.retry_options. None means no retries; the ResilientProvider
        # owns retrying. Private attribute (Part E #15): the contract tests fail on any
        # unexpected repeat request, so an SDK change here can't go unnoticed.
        self._client.aio.interactions.sdk_configuration.retry_config = None

    async def generate(
        self,
        messages: list[Message],
        *,
        options: GenerateOptions,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResult:
        request: dict[str, Any] = {
            "model": options.model,
            "input": [step for m in messages for step in _to_steps(m)],
            "store": False,
            "generation_config": {"max_output_tokens": options.max_output_tokens,
                                  "thinking_level": THINKING[options.reasoning]},
            "timeout": options.timeout_s,
        }
        if system:
            request["system_instruction"] = system
        if tools:
            request["tools"] = [{"type": "function", "name": t.name,
                                 "description": t.description, "parameters": t.parameters}
                                for t in tools]
        if schema is not None:
            request["response_format"] = {"type": "text", "mime_type": "application/json",
                                          "schema": gemini_schema(schema)}
        try:
            interaction = await self._client.aio.interactions.create(**request)
        except (compat_errors.APITimeoutError, httpx.TimeoutException) as exc:
            raise ProviderTimeout(str(exc), self.name) from exc
        except compat_errors.APIStatusError as exc:
            raise _status_error(exc.status_code, str(exc),
                                _retry_after(exc.response.headers)) from exc
        except genai_errors.APIError as exc:
            raise _status_error(exc.code or 0, str(exc), None) from exc
        except (compat_errors.APIConnectionError, httpx.TransportError) as exc:
            raise ProviderUnavailable(str(exc), self.name) from exc
        except compat_errors.APIError as exc:  # e.g. a response that didn't validate
            raise ProviderUnavailable(str(exc), self.name) from exc
        return _to_result(interaction, options.model, schema)


def gemini_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """The provider-safe schema with item limits removed from nested arrays.

    Gemini rejects NutritionReply as "too many states for serving": its foods array
    holds arrays of ingredients and tags, each with its own maxItems (Part D, 26 Oct
    2026). Dropping minItems/maxItems below the top level fixes it; the top-level item
    limit stays. Pydantic still enforces every limit when the reply is parsed, so a
    reply over a limit becomes MalformedOutput and the agent retries (C.10).
    """

    def walk(node: Any, inside_array: bool) -> Any:
        if isinstance(node, list):
            return [walk(n, inside_array) for n in node]
        if not isinstance(node, dict):
            return node
        out = {}
        for key, value in node.items():
            if inside_array and node.get("type") == "array" and key in ("minItems", "maxItems"):
                continue
            nested = inside_array or (key == "items" and node.get("type") == "array")
            out[key] = walk(value, nested)
        return out

    return walk(llm_json_schema(schema), inside_array=False)


def _to_steps(message: Message) -> list[dict[str, Any]]:
    if isinstance(message, Turn):
        if message.role == "assistant":
            return [{"type": "model_output", "content": [{"type": "text", "text": message.text}]}]
        content: list[dict[str, Any]] = [{"type": "text", "text": message.text}]
        for image in message.images:
            content.append({"type": "image", "mime_type": image.mime_type,
                            "data": base64.b64encode(image.data).decode()})
        return [{"type": "user_input", "content": content}]
    if isinstance(message, ModelTurn):
        if message.provider == "gemini":
            return list(message.items)
        steps: list[dict[str, Any]] = []
        if message.text:
            steps.append({"type": "model_output",
                          "content": [{"type": "text", "text": message.text}]})
        steps += [{"type": "function_call", "id": c.id, "name": c.name,
                   "arguments": c.arguments} for c in message.tool_calls]
        return steps
    if isinstance(message, ToolResult):
        return [{"type": "function_result", "call_id": message.call_id, "name": message.name,
                 "result": json.dumps(message.output)}]
    raise TypeError(f"unknown message {message!r}")


def _to_result(interaction: Any, model: str, schema: type[BaseModel] | None) -> LLMResult:
    if interaction.status in ("failed", "budget_exceeded"):
        raise ProviderUnavailable(f"interaction {interaction.status}: {interaction.errors}",
                                  "gemini")
    steps = interaction.steps or []
    calls = tuple(
        ToolCall(id=s.id, name=s.name, arguments=dict(s.arguments or {}))
        for s in steps if s.type == "function_call"
    )
    text = interaction.output_text or None
    truncated = interaction.status == "incomplete"
    usage = interaction.usage
    result_usage = Usage(
        tokens_in=usage.total_input_tokens or 0,
        tokens_out=(usage.total_output_tokens or 0) + (usage.total_thought_tokens or 0),
        reasoning_tokens=usage.total_thought_tokens or 0,
        cached_tokens=usage.total_cached_tokens or 0,
    ) if usage else Usage()
    parsed = None
    if schema is not None and not calls:
        if truncated:
            raise MalformedOutput("reply cut off at max_output_tokens", "gemini")
        parsed = parse_reply(text, schema, "gemini")
    turn = ModelTurn(provider="gemini",
                     items=tuple(s.model_dump(mode="json", exclude_none=True, by_alias=True)
                                 for s in steps),
                     tool_calls=calls, text=text)
    return LLMResult(provider="gemini", model=model, tool_calls=calls, text=text,
                     parsed=parsed, usage=result_usage, truncated=truncated, turn=turn)


def _status_error(status: int, message: str, retry_after: float | None):
    if status == 429:
        return RateLimited(message, "gemini", retry_after)
    if status >= 500:
        return ProviderUnavailable(message, "gemini", retry_after)
    return BadRequest(message, "gemini")


def _retry_after(headers: Any) -> float | None:
    try:
        return float(headers.get("retry-after", ""))
    except (AttributeError, ValueError):
        return None
