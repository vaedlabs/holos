"""The provider interface (Plan C.9): one generate() call, any model.

A conversation is a list of provider-neutral items (turns with optional images,
tool calls and tool results). Each provider translates it into its own wire format.
Errors are mapped to a small set the ResilientProvider understands.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError

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


# --- Errors ---


class ProviderError(Exception):
    """Base class. `retryable` errors are retried and may fall back (C.9)."""

    retryable = False

    def __init__(self, message: str, provider: str = "", retry_after: float | None = None):
        super().__init__(message)
        self.provider = provider
        self.retry_after = retry_after


class RateLimited(ProviderError):
    retryable = True


class ProviderUnavailable(ProviderError):
    """5xx, connection errors, or an open circuit breaker."""

    retryable = True


class ProviderTimeout(ProviderError):
    retryable = True


class BadRequest(ProviderError):
    """4xx other than 429: our request is wrong; retrying won't help."""


class MalformedOutput(ProviderError):
    """The reply doesn't parse into the schema or was cut off (C.10 step 4)."""


def parse_reply(text: str | None, schema: type[BaseModel], provider: str) -> BaseModel:
    if not text:
        raise MalformedOutput("empty reply", provider)
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        raise MalformedOutput(f"reply doesn't match {schema.__name__}: {exc}", provider) from exc


class LLMProvider(Protocol):
    name: ProviderName

    async def generate(
        self,
        messages: list[Message],
        *,
        options: GenerateOptions,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResult:
        """One model call. With `schema`, a reply without tool calls is parsed into it."""
        ...
