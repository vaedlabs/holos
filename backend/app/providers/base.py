"""The provider interface (Plan C.9): one generate() call, any model.

A conversation is a list of provider-neutral items (turns with optional images,
tool calls and tool results). Each provider translates it into its own wire format.
Errors are mapped to a small set the ResilientProvider understands; each carries one
cause from the tracer's closed list (Part E #39).
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError

from app.observability.tracer import CAUSES, Cause

ProviderName = Literal["openai", "gemini", "fake"]
Reasoning = Literal["none", "low", "medium", "high"]


@dataclass(frozen=True)
class ImageInput:
    data: bytes
    mime_type: str = "image/jpeg"


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    text: str
    images: tuple[ImageInput, ...] = ()


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    """What the model produced in one call, sent back unchanged in the next request.

    `items` is the provider's own wire format (Gemini needs its thought steps
    returned). If the conversation moves to another provider (fallback), that
    provider rebuilds the turn from `text` and `tool_calls` instead.
    """

    provider: str
    items: tuple[dict[str, Any], ...]
    tool_calls: tuple[ToolCall, ...] = ()
    text: str | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    output: dict[str, Any]


Message = Turn | ModelTurn | ToolResult


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # provider-safe JSON Schema (agents.schemas.llm_json_schema)


@dataclass(frozen=True)
class GenerateOptions:
    model: str
    max_output_tokens: int  # reply cap plus any reasoning allowance (C.9)
    reasoning: Reasoning = "none"
    timeout_s: float = 25.0


@dataclass(frozen=True)
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0  # includes reasoning tokens
    reasoning_tokens: int = 0
    cached_tokens: int = 0


@dataclass(frozen=True)
class LLMResult:
    provider: ProviderName
    model: str
    tool_calls: tuple[ToolCall, ...] = ()
    text: str | None = None
    parsed: BaseModel | None = None
    usage: Usage = field(default_factory=Usage)
    truncated: bool = False  # stopped at max_output_tokens: a failure (C.10 step 4)
    turn: ModelTurn | None = None  # append to the conversation before the tool results
    request_id: str | None = None  # the provider's ID for the request, for its support


# --- Errors ---


class ProviderError(Exception):
    """Base class. `retryable` errors are retried and may fall back (C.9). `cause` is
    the class's unless a raise names a narrower one."""

    retryable = False
    cause: Cause = "bug"

    def __init__(self, message: str, provider: str = "", retry_after: float | None = None,
                 *, cause: Cause | None = None, request_id: str | None = None,
                 status: int | None = None):
        super().__init__(message)
        if cause is not None:
            if cause not in CAUSES:
                raise ValueError(f"unknown cause {cause!r}")
            self.cause = cause
        self.provider = provider
        self.retry_after = retry_after
        self.request_id = request_id
        self.status = status


class RateLimited(ProviderError):
    retryable = True
    cause = "rate_limited"


class ProviderUnavailable(ProviderError):
    """5xx, connection errors, an error mid-stream, or an open circuit breaker
    (cause circuit_open)."""

    retryable = True
    cause = "unavailable"


class ProviderTimeout(ProviderError):
    """The HTTP client's timeout, or our deadline (cause deadline_waiting or
    deadline_writing, or no_time_left before sending)."""

    retryable = True
    cause = "provider_timeout"


class ProviderStalled(ProviderError):
    """A streaming call went silent: no output within its first-output limit, or no new
    output within the gap limit once writing (Part E #35). Retryable; bad for the
    breaker. Cause no_first_output or output_stopped."""

    retryable = True
    cause = "no_first_output"


class BadRequest(ProviderError):
    """4xx other than 429: our request is wrong; retrying won't help."""

    cause = "bad_request"


class AccountFailure(ProviderError):
    """The provider refused our account, not this request: the API key was rejected
    (401/403) or the account is out of credit (OpenAI's 429 `insufficient_quota`).
    Every call will fail the same way until someone fixes it, so it isn't retried; it
    opens the provider's breaker at once and logs an alert (failure library, Part E #55).
    Another provider may still be tried."""

    cause = "account"


class NoCapacity(ProviderError):
    """No slot would free in time for this call (load shedding, C.9). Not retried:
    retrying adds load. Says nothing about the provider's health."""

    cause = "queue_full"


class OverBudget(ProviderError):
    """A spend cap has no room for this call's reservation (C.13). The call didn't run."""

    cause = "over_budget"


class MalformedOutput(ProviderError):
    """The reply doesn't parse into the schema, or was cut off (cause truncated) (C.10
    step 4)."""

    cause = "malformed"


def parse_reply(text: str | None, schema: type[BaseModel], provider: str) -> BaseModel:
    """The reply in the schema. Text over a length limit is trimmed, not failed:
    neither provider enforces lengths, and live 13 of 378 coach replies ran a little
    over one (Part D); a retry for that costs a whole call."""
    if not text:
        raise MalformedOutput("empty reply", provider)
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        error = exc
    too_long = [e for e in error.errors() if e["type"] == "string_too_long"]
    try:
        data = json.loads(text)
        for e in too_long:
            _replace(data, e["loc"], trim(e["input"], e["ctx"]["max_length"]))
        if too_long:
            return schema.model_validate(data)
    except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
        error = exc
    raise MalformedOutput(f"reply doesn't match {schema.__name__}: {error}", provider) from error


SENTENCE_END = re.compile(r"[.!?।](?=\s|$)")


def trim(text: str, limit: int) -> str:
    """At the last sentence end within the limit, if that keeps at least half; else at
    the last word, with an ellipsis."""
    if len(text) <= limit:
        return text
    window = text[:limit]
    ends = [m.end() for m in SENTENCE_END.finditer(window)]
    if ends and ends[-1] >= limit // 2:
        return window[:ends[-1]]
    cut = window[:limit - 1].rsplit(" ", 1)[0] if " " in window[:limit - 1] else window[:limit - 1]
    return cut.rstrip(" ,;:-") + "…"


def _replace(data: Any, loc: tuple, value: Any) -> None:
    for key in loc[:-1]:
        data = data[key]
    data[loc[-1]] = value


# Called by a streaming provider on every event; True when the event carried output
# (reply text or tool arguments). The ResilientProvider's silence rules read it.
Progress = Callable[[bool], None]
# Called once when the provider's response headers arrive, with its request ID: the
# trace can then tell a call the provider never answered from one it answered slowly
Opened = Callable[[str | None], None]


class LLMProvider(Protocol):
    name: ProviderName
    streams: bool  # reports Progress while the reply is written (Part E #35)

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
        """One model call. With `schema`, a reply without tool calls is parsed into it."""
        ...
