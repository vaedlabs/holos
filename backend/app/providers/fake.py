"""FakeProvider: scripted results for tests and LLM_MODE=fake (Plan C.9). No network."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .base import GenerateOptions, LLMResult, Message, ModelTurn, Opened, Progress, ToolSpec


@dataclass(frozen=True)
class Slow:
    """A step that takes `seconds` before it happens (a slow call)."""

    seconds: float
    step: "Step"


@dataclass(frozen=True)
class Stream:
    """A streamed step: for each gap, sleep it, then report one event; then the step
    happens. `silent` sleeps before the first event and reports nothing. output=False:
    the events only say the stream is alive (no reply text)."""

    gaps: tuple[float, ...]
    step: "Step"
    silent: float = 0.0
    output: bool = True


# A script step: a result, an exception to raise, a function of the call, a slow step
# or a streamed one
Step = LLMResult | Exception | Callable[["FakeCall"], LLMResult] | Slow | Stream


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
    streams: bool = False  # True: the ResilientProvider applies its silence rules
    request_id: str | None = None  # reported to `opened` when a call starts
    calls: list[FakeCall] = field(default_factory=list)

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
        call = FakeCall(list(messages), options, system, tools, schema)
        self.calls.append(call)
        if opened is not None and self.request_id is not None:
            opened(self.request_id)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if not self.script:
            raise AssertionError(f"FakeProvider {self.name!r} has no scripted step left")
        step = self.script.pop(0)
        if isinstance(step, Slow):
            await asyncio.sleep(step.seconds)
            step = step.step
        if isinstance(step, Stream):
            await asyncio.sleep(step.silent)
            for gap in step.gaps:
                await asyncio.sleep(gap)
                if progress is not None:
                    progress(step.output)
            step = step.step
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
