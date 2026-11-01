"""OpenAIProvider: the Responses API through AsyncOpenAI (Plan C.9).

The schema sent is agents.schemas.llm_json_schema (strict), not
responses.parse(text_format=Model): that would rebuild the schema from the Pydantic
model, including maxLength, which OpenAI's structured outputs reject (Part D).
The reply is validated with Pydantic afterwards. SDK retries are off; the
ResilientProvider owns retrying.

Every call streams (Part E #35): each event is reported to `progress`, so the
ResilientProvider can tell a long reply that is still being written from a stalled
call. Nothing reaches the user from here: the result is built from the final
`response.completed` event, exactly as a non-streamed reply.

The request ID (`x-request-id`, which OpenAI support can look up) is reported to
`opened` when the headers arrive, and carried on the result and on every error.
"""

import base64
import json
from typing import Any

import httpx
import openai
from pydantic import BaseModel

from app.agents.schemas import llm_json_schema

from .base import (
    BadRequest,
    GenerateOptions,
    LLMResult,
    MalformedOutput,
    Message,
    ModelTurn,
    Opened,
    Progress,
    ProviderError,
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

# Events that carry output; every other event only says the stream is alive
OUTPUT_EVENTS = frozenset({
    "response.output_text.delta", "response.function_call_arguments.delta",
    "response.refusal.delta",
})
FINAL_EVENTS = frozenset({"response.completed", "response.incomplete"})


class OpenAIProvider:
    name = "openai"
    streams = True

    def __init__(self, api_key: str, http_client: httpx.AsyncClient | None = None):
        self._client = openai.AsyncOpenAI(api_key=api_key, max_retries=0, http_client=http_client)

    async def generate(
        self,
        messages: list[Message],
        *,
        options: GenerateOptions,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        schema: type[BaseModel] | None = None,
        progress: Progress | None = None,
        opened: Opened | None = None,
    ) -> LLMResult:
        request: dict[str, Any] = {
            "model": options.model,
            "input": [item for m in messages for item in _to_input(m)],
            "max_output_tokens": options.max_output_tokens,
            "reasoning": {"effort": options.reasoning},
            "store": False,
            "stream": True,
            "timeout": options.timeout_s,
        }
        if system:
            request["instructions"] = system
        if tools:
            request["tools"] = [
                {"type": "function", "name": t.name, "description": t.description,
                 "parameters": t.parameters, "strict": True}
                for t in tools
            ]
        if schema is not None:
            request["text"] = {"format": {"type": "json_schema", "name": schema.__name__,
                                          "schema": llm_json_schema(schema), "strict": True}}
        ids: list[str | None] = [None]  # set when the headers arrive

        def on_open(request_id: str | None) -> None:
            ids[0] = request_id
            if opened is not None:
                opened(request_id)

        try:
            response = await self._stream(request, progress, on_open)
            return _to_result(response, options.model, schema, ids[0])
        except openai.APITimeoutError as exc:
            raise ProviderTimeout(str(exc), self.name, request_id=ids[0]) from exc
        except openai.RateLimitError as exc:
            raise RateLimited(str(exc), self.name, _retry_after(exc.response),
                              request_id=exc.request_id, status=exc.status_code) from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(str(exc), self.name, _retry_after(exc.response),
                                          request_id=exc.request_id,
                                          status=exc.status_code) from exc
            raise BadRequest(str(exc), self.name, request_id=exc.request_id,
                             status=exc.status_code) from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailable(str(exc), self.name, request_id=ids[0]) from exc
        except openai.APIError as exc:
            # An error event mid-stream (live, 29 Oct 2026: "An error occurred while
            # processing your request. You can retry your request")
            raise ProviderUnavailable(str(exc), self.name, request_id=ids[0]) from exc
        except ProviderError as exc:
            exc.request_id = exc.request_id or ids[0]  # a stream error or a bad reply
            raise

    async def _stream(self, request: dict[str, Any], progress: Progress | None,
                      opened: Opened) -> Any:
        """The final Response of a streamed call."""
        async with await self._client.responses.create(**request) as stream:
            opened(stream.response.headers.get("x-request-id"))
            async for event in stream:
                if progress is not None:
                    progress(event.type in OUTPUT_EVENTS)
                if event.type in FINAL_EVENTS:
                    return event.response
                if event.type in ("response.failed", "error"):
                    raise ProviderUnavailable(f"stream {event.type}: {_error_text(event)}",
                                              self.name)
        raise ProviderUnavailable("stream ended without a reply", self.name)


def _error_text(event: Any) -> str:
    error = getattr(event, "error", None) or getattr(getattr(event, "response", None),
                                                     "error", None)
    return str(getattr(error, "message", None) or error or getattr(event, "message", ""))[:200]


def _to_input(message: Message) -> list[dict[str, Any]]:
    if isinstance(message, Turn):
        if message.role == "assistant":
            return [{"role": "assistant", "content": message.text}]
        content: list[dict[str, Any]] = [{"type": "input_text", "text": message.text}]
        for image in message.images:
            data = base64.b64encode(image.data).decode()
            content.append({"type": "input_image",
                            "image_url": f"data:{image.mime_type};base64,{data}"})
        return [{"role": "user", "content": content}]
    if isinstance(message, ModelTurn):
        if message.provider == "openai":
            return list(message.items)
        items: list[dict[str, Any]] = []
        if message.text:
            items.append({"role": "assistant", "content": message.text})
        items += [{"type": "function_call", "call_id": c.id, "name": c.name,
                   "arguments": json.dumps(c.arguments)} for c in message.tool_calls]
        return items
    if isinstance(message, ToolResult):
        return [{"type": "function_call_output", "call_id": message.call_id,
                 "output": json.dumps(message.output)}]
    raise TypeError(f"unknown message {message!r}")


def _to_result(response: Any, model: str, schema: type[BaseModel] | None,
               request_id: str | None = None) -> LLMResult:
    truncated = (response.status == "incomplete"
                 and getattr(response.incomplete_details, "reason", None) == "max_output_tokens")
    calls = []
    for item in response.output:
        if item.type == "function_call":
            try:
                arguments = json.loads(item.arguments or "{}")
            except json.JSONDecodeError as exc:
                raise MalformedOutput(f"tool arguments aren't JSON: {exc}", "openai") from exc
            calls.append(ToolCall(id=item.call_id, name=item.name, arguments=arguments))
    usage = response.usage
    result_usage = Usage(
        tokens_in=usage.input_tokens,
        tokens_out=usage.output_tokens,
        reasoning_tokens=getattr(usage.output_tokens_details, "reasoning_tokens", 0) or 0,
        cached_tokens=getattr(usage.input_tokens_details, "cached_tokens", 0) or 0,
    )
    text = response.output_text or None
    parsed = None
    if schema is not None and not calls:
        if truncated:
            raise MalformedOutput("reply cut off at max_output_tokens", "openai",
                                  cause="truncated")
        parsed = parse_reply(text, schema, "openai")
    turn = ModelTurn(provider="openai",
                     items=tuple(i.model_dump(exclude_none=True) for i in response.output),
                     tool_calls=tuple(calls), text=text)
    return LLMResult(provider="openai", model=model, tool_calls=tuple(calls), text=text,
                     parsed=parsed, usage=result_usage, truncated=truncated, turn=turn,
                     request_id=request_id or getattr(response, "id", None))


def _retry_after(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    try:
        return float(response.headers.get("retry-after", ""))
    except ValueError:
        return None
