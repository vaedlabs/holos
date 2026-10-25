"""FakeProvider: scripted results for tests and LLM_MODE=fake (Plan C.9). No network."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .base import GenerateOptions, LLMResult, Message, ModelTurn, ToolSpec

# A script step: a result, an exception to raise, or a function of the call
Step = LLMResult | Exception | Callable[["FakeCall"], LLMResult]


@dataclass(frozen=True)
class FakeCall:
    messages: list[Message]
    options: GenerateOptions
    system: str | None
    tools: list[ToolSpec] | None
    schema: type[BaseModel] | None


@dataclass
class FakeProvider:
    script: list[Step] = field(default_factory=list)
    delay_s: float = 0.0
    name: str = "fake"
    calls: list[FakeCall] = field(default_factory=list)

    async def generate(
        self,
        messages: list[Message],
        *,
        options: GenerateOptions,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResult:
        call = FakeCall(list(messages), options, system, tools, schema)
        self.calls.append(call)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if not self.script:
            raise AssertionError(f"FakeProvider {self.name!r} has no scripted step left")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        result = step(call) if callable(step) else step
        if result.turn is None:  # fill the turn so callers can echo it like a real provider
            result = _with_turn(result)
        return result


def _with_turn(result: LLMResult) -> LLMResult:
    from dataclasses import replace

    return replace(result, turn=ModelTurn(provider=result.provider, items=(),
                                          tool_calls=result.tool_calls, text=result.text))


def reply(parsed: BaseModel, tokens: tuple[int, int] = (100, 50), **kw: Any) -> LLMResult:
    """A scripted final reply."""
    from .base import Usage

    return LLMResult(provider="fake", model=kw.pop("model", "fake-model"), parsed=parsed,
                     text=parsed.model_dump_json(), usage=Usage(*tokens), **kw)
