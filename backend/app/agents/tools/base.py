"""What every tool shares: the per-request context, the gate hook and the tool spec.

The coordinator (Phase 4) builds one ToolContext per request. Tools in one round run
at the same time (Plan C.10), so read tools open their own database session from
`ctx.sessions` instead of sharing one.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.schemas import Decision, Source, StagedWrite, WriteKind
from app.data.state_store import SpendKey


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str | None = None
    decisions: tuple[Decision, ...] = ()


# Gates a write before it is staged. P4.8 wires the real gate (Plan C.14, C.17).
GateHook = Callable[[WriteKind, BaseModel, "ToolContext"], Awaitable[GateResult]]


async def allow_all(kind: WriteKind, args: BaseModel, ctx: "ToolContext") -> GateResult:
    """Placeholder gate until P4.8."""
    return GateResult(allowed=True)


@dataclass
class ToolContext:
    mode: Literal["guest", "account"]
    trace_id: str
    user_id: int | None = None
    sessions: async_sessionmaker[AsyncSession] | None = None  # account mode only
    gate_write: GateHook = allow_all
    search: Any = None  # WebSearch; typed loosely to avoid an import cycle
    search_keys: list[SpendKey] = field(default_factory=list)  # credit caps (Plan C.13)
    staged_writes: list[StagedWrite] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    searches_used: int = 0
    untrusted: bool = False  # a web search result entered the turn (Plan C.17)

    def clear_staged(self) -> None:
        """A retry starts without the writes of the failed attempt (Plan C.10 step 6)."""
        self.staged_writes.clear()


ToolHandler = Callable[[BaseModel, ToolContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    name: str
    kind: Literal["read", "write", "search"]
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler

    async def run(self, raw_args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """Validate the model's arguments, then run. Bad arguments come back as an error
        the model can read, not an exception."""
        try:
            args = self.args_model.model_validate(raw_args)
        except ValidationError as exc:
            errors = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
            return {"status": "invalid_arguments", "errors": errors[:5]}
        return await self.handler(args, ctx)
