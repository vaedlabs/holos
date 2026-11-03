"""The composer (Plan C.5): gated results in, stream events out, in order, each one
handed to a sink that saves it before it is sent.

    composer = Composer(trace_id, "guest", sink)
    await composer.accepted(contract_version)
    trace.listener = composer.on_trace_step      # tool calls, gate, retry as they happen
    await composer.section("physical", result)   # a coach's AgentResult, already gated
    await composer.reply(gated(text, profile))   # Holos's own reply (C.15)
    await composer.done(trace_view(...), usage, turn)

Only gated content reaches the person: items come from an AgentResult the coach gated
(C.10), and every text event takes a `Gated`, which only `gated()` makes, by running
`gate_text`. Exactly one terminal event: after `done` or `error` nothing else is sent.
Events go out one batch at a time under a lock, so concurrent coaches' sections never
interleave and `seq` follows the order sent.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from app.agents.base import decisions_of
from app.agents.display import history_text, item_display, keep_lines
from app.agents.schemas import (
    EVENT_DATA,
    TERMINAL_EVENTS,
    AgentName,
    AgentResult,
    CommittedWrite,
    Decision,
    HistoryTurn,
    Source,
    StagedWrite,
    TraceStep,
    TraceTool,
    TraceView,
    TurnKind,
    Usage,
    UserProfile,
)
from app.agents.tools.write import summarise
from app.data.stream_store import Event
from app.guardrails.gate import gate_text
from app.guardrails.loader import get_guardrails
from app.observability.tracer import Step, Trace
from app.orchestration.staging import confirm_attributes, warning_text

log = logging.getLogger(__name__)

STILL_WORKING_S = 8  # Part E #35
TRACE_VIEW_MAX = 32 * 1024
TURN_CHARS = 2000  # HistoryTurn.content
WARNING_CHARS = 400
AGENTS: frozenset[str] = frozenset({"physical", "nutrition", "mental"})
TOOL_STATUSES = frozenset({"ok", "error", "refused", "staged", "held", "unavailable"})

# Statuses the app shows; not conversation (the coaches and the router write that)
NOTICES = {
    "cap_reached": "You've reached today's limit. Try again tomorrow.",
    "search_off": "Web search is off for now, so this answer has no sources.",
    "partial_result": "One coach took too long to answer; here is what is ready.",
    "month_budget_used": "Holos has used this month's budget. Please try again next month.",
}
ERRORS = {
    "busy": "Holos is busy right now. Please try again in a moment.",
    "cap_reached": "You've reached today's limit. Try again tomorrow.",
    "unavailable": "The coach is unavailable right now. Please try again.",
    "malformed": "The coach's answer didn't come through. Please try again.",
    "interrupted": "Your answer was interrupted. Tap to try again.",
}


class Sink(Protocol):
    async def emit(self, events: list[Event], final: bool) -> None: ...


class StreamEnded(RuntimeError):
    """Something tried to send after the terminal event."""


@dataclass(frozen=True)
class Gated:
    """Text that passed `gate_text`. Make it with `gated()`; nothing else should."""

    text: str
    decisions: tuple[Decision, ...] = ()


def gated(text: str, profile: UserProfile) -> Gated:
    result = gate_text(text, profile)
    return Gated(result.content.strip(), tuple(decisions_of(result)))


@dataclass
class Composer:
    trace_id: str
    mode: Literal["guest", "account"]
    sink: Sink
    clock: Callable[[], float] = field(default=lambda: asyncio.get_running_loop().time())
    _seq: int = 0
    _ended: bool = False
    _last_sent: float | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Progress the trace reported, waiting to go out ahead of whatever is sent next
    _queued: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    _flush: asyncio.Task | None = None

    # --- Opening and progress ---

    async def accepted(self, contract_version: int) -> None:
        await self._send([("accepted", {"contract_version": contract_version,
                                        "mode": self.mode})])

    async def step(self, name: str, agent: AgentName | None = None,
                   detail: str | None = None) -> None:
        fields: dict[str, Any] = {"name": name}
        if agent is not None:
            fields["agent"] = agent
        if detail:
            fields["detail"] = detail[:200]
        await self._send([("step", fields)])

    def on_trace_step(self, step: Step) -> None:
        """Trace listener: tool calls, the gate and retries become `step` events."""
        if step.name not in ("tool_call", "gate", "retry") or self._ended:
            return
        agent = step.agent if step.agent in AGENTS else None
        if step.name == "tool_call":
            status = _tool_status(step.outcome)
            detail = step.detail + ("" if status in ("ok", "staged") else f" {status}")
        elif step.name == "gate":
            detail = None if step.outcome == "allow" else step.outcome
        else:
            detail = step.detail or None
        fields: dict[str, Any] = {"name": step.name}
        if agent is not None:
            fields["agent"] = agent
        if detail:
            fields["detail"] = detail[:200]
        # Queued, not sent from a task: a task would run after whatever the caller
        # sends next (found by the golden streams). The next send takes the queue
        # first; if nothing is sent soon, a flush does.
        self._queued.append(("step", fields))
        if self._flush is None or self._flush.done():
            self._flush = asyncio.get_running_loop().create_task(self._send([]))

    async def still_working(self) -> None:
        """Run alongside the request: `still_working` after 8 s without an event."""
        while not self._ended:
            last = self._last_sent if self._last_sent is not None else self.clock()
            wait = last + STILL_WORKING_S - self.clock()
            if wait > 0:
                await asyncio.sleep(wait)
                continue
            await self.step("still_working")

    # --- Content ---

    async def section(self, agent: AgentName, result: AgentResult) -> None:
        """One coach's answer, or its failure (the app shows Retry for that coach)."""
        end: dict[str, Any] = {"agent": agent, "removed_count": result.removed_count,
                               "decisions": [d.model_dump(mode="json")
                                             for d in result.decisions]}
        warnings = [w[:WARNING_CHARS] for w in result.warnings]
        if warnings:
            end["warnings"] = warnings
        reply = result.reply
        if reply is None:
            await self._send([("section_end", {**end, "error": result.error or "unavailable"})])
            return
        events: list[tuple[str, dict[str, Any]]] = [
            ("section_start", {"agent": agent, "kind": reply.kind})]
        for line in (reply.summary, reply.follow_up):
            if line:
                events.append(("text", {"agent": agent, "chunk": line}))
        caveats = result.item_caveats or [[] for _ in reply.items]
        for item, item_caveats in zip(reply.items, caveats, strict=True):
            events.append(("item", {"agent": agent, "item": item.model_dump(mode="json"),
                                    "display": item_display(item)[:300],
                                    "caveats": item_caveats}))
        events += [("text", {"agent": agent, "chunk": note}) for note in reply.notes]
        if result.sources:
            events.append(("sources", {"agent": agent, "sources": [
                s.model_dump(mode="json") for s in result.sources]}))
        events.append(("section_end", end))
        await self._send(events)

    async def reply(self, text: Gated) -> None:
        """Holos's own reply, when no coach was needed (C.15)."""
        await self._text(text, {})

    async def summary(self, text: Gated) -> None:
        """The multi-coach summary (C.2 stage 11)."""
        await self._text(text, {"summary": True})

    async def helplines(self, full: bool) -> None:
        """After the sections (C.16): the signed-off crisis message when a coach set
        `risk_flag`, else the short reminder while the crisis flag is set."""
        crisis = get_guardrails().rules.crisis
        await self._send([("crisis", {
            "text": crisis.message if full else crisis.reminder,
            "helplines": [h.model_dump() for h in crisis.helplines]})])

    async def crisis(self) -> None:
        """The crisis stream's one event (C.16)."""
        await self.helplines(full=True)

    async def notice(self, code: str) -> None:
        await self._send([("notice", {"code": code, "message": NOTICES[code]})])

    async def pending_write(self, write: StagedWrite, *, write_id: str | None = None,
                            expires_at: datetime | None = None,
                            profile_hash: str | None = None) -> None:
        """A write that waits for the person's confirmation (C.17)."""
        fields: dict[str, Any] = {"summary": summarise(write.kind, write.args)[:300],
                                  "warnings": [warning_text(w) for w in write.conflicts],
                                  "attributes": confirm_attributes(write)}
        if self.mode == "account":
            fields |= {"write_id": write_id, "expires_at": expires_at}
        else:
            fields |= {"entry": write.model_dump(mode="json"), "profile_hash": profile_hash}
        await self._send([("pending_write", fields)])

    async def committed(self, writes: list[tuple[StagedWrite, str | None]]) -> None:
        """Confirmations from the commit result (C.17): written here, never by a model.
        Each write with its stored ID (account) or None (guest: the browser stores it)."""
        await self._send([("committed", {"writes": [
            confirmation(w, write_id, self.mode) for w, write_id in writes]})])

    # --- The end ---

    async def done(self, view: TraceView, usage: Usage, turn: HistoryTurn | None = None
                   ) -> None:
        fields: dict[str, Any] = {"trace": view.model_dump(mode="json"),
                                  "usage": usage.model_dump(mode="json")}
        if turn is not None and self.mode == "guest":
            fields["turn"] = turn.model_dump(mode="json")
        await self._send([("done", fields)])

    async def error(self, code: str, retry_after: int | None = None) -> None:
        fields: dict[str, Any] = {"code": code, "message": ERRORS.get(code, ERRORS["unavailable"])}
        if retry_after is not None:
            fields["retry_after"] = retry_after
        await self._send([("error", fields)])

    @property
    def ended(self) -> bool:
        return self._ended

    # --- Sending ---

    async def _text(self, text: Gated, fields: dict[str, Any]) -> None:
        if not isinstance(text, Gated):
            raise TypeError("text events take gated text only (C.5)")
        if text.text:
            await self._send([("text", {**fields, "chunk": text.text[:1000]})])

    async def _send(self, events: list[tuple[str, dict[str, Any]]]) -> None:
        async with self._lock:
            if self._ended:
                if not events:
                    return  # a late flush: progress after the end is dropped
                raise StreamEnded(f"{events[0][0]} after the end of {self.trace_id}")
            events = [*self._queued, *events]
            self._queued.clear()
            if not events:
                return
            final = events[-1][0] in TERMINAL_EVENTS
            batch: list[Event] = []
            for name, fields in events:
                # The contract, checked before anything leaves; sent as the model writes
                # it (ISO dates), with only the fields set
                model = EVENT_DATA[name].model_validate(
                    {"seq": self._seq + len(batch), "trace_id": self.trace_id, **fields})
                data = {k: v for k, v in model.model_dump(mode="json").items()
                        if k in model.model_fields_set}
                batch.append((data["seq"], name, data))
            await self.sink.emit(batch, final)
            self._seq += len(batch)
            self._last_sent = self.clock()
            self._ended = final


def confirmation(write: StagedWrite, write_id: str | None,
                 mode: Literal["guest", "account"]) -> dict[str, Any]:
    """A committed write as the app shows it: "Logged: …" from what was stored, with
    the ID (account) or the whole entry (guest). The stream's `committed` event and the
    confirm endpoint both send this, so the app reads one shape."""
    return CommittedWrite(kind=write.kind,
                          summary=f"Logged: {summarise(write.kind, write.args)}"[:300],
                          write_id=write_id, entry=write if mode == "guest" else None,
                          warnings=[warning_text(w) for w in write.conflicts]
                          ).model_dump(mode="json")


# --- The trace as the person may see it (C.5 TraceView) ---


def trace_view(trace: Trace, route: TurnKind | Literal["crisis"],
               agents: list[AgentName], decisions: list[Decision], sources: list[Source],
               usage: Usage) -> TraceView:
    """At most 32 KB: tools go first, then steps, then decisions. No text the person
    wrote: tool arguments stay empty (Part E #39)."""
    steps = [TraceStep(name=s.name[:40], agent=s.agent if s.agent in AGENTS else None,
                       start_ms=max(s.at_ms, 0), duration_ms=max(s.duration_ms, 0),
                       queue_ms=0)
             for s in trace.steps if s.name != "tool_call"]
    steps += [TraceStep(name=f"call_{a.role}", agent=_call_agent(a.call),
                        start_ms=a.began_ms, duration_ms=max((a.ended_ms or a.began_ms)
                                                             - a.began_ms, 0),
                        queue_ms=a.queued_ms)
              for a in trace.attempts]
    steps.sort(key=lambda s: s.start_ms)
    tools = [TraceTool(name=s.detail[:40] or "tool", args="", duration_ms=s.duration_ms,
                       status=_tool_status(s.outcome))
             for s in trace.steps if s.name == "tool_call"]
    view = TraceView(trace_id=trace.trace_id, route=route, agents=agents, steps=steps,
                     tools=tools, decisions=decisions,
                     retries=sum(s.name == "retry" for s in trace.steps),
                     sources=sources, usage=usage)
    for name in ("tools", "steps", "decisions"):
        while len(view.model_dump_json()) > TRACE_VIEW_MAX and getattr(view, name):
            kept = getattr(view, name)
            view = view.model_copy(update={name: kept[:len(kept) // 2]})
    return view


def _call_agent(call: str) -> AgentName | None:
    if call == "meal_photo":
        return "nutrition"
    return call if call in AGENTS else None  # type: ignore[return-value]


def _tool_status(outcome: str) -> str:
    if outcome in TOOL_STATUSES:
        return outcome
    return "unavailable" if "unavailable" in outcome else "error"


# --- The history turn (C.5, C.8) ---


def turn_text(*, own: Gated | None = None, summary: Gated | None = None,
              results: list[AgentResult] = ()) -> str:
    """What the person saw, for the next turn's history: Holos's own reply, or the
    summary and each coach's plan (summary, items with their days, notes)."""
    if own is not None:
        return keep_lines([own.text], TURN_CHARS)
    lines = [summary.text] if summary is not None and summary.text else []
    for result in results:
        if result.reply is not None:
            lines += history_text(result.reply, TURN_CHARS).splitlines()
    return keep_lines(lines, TURN_CHARS)


def history_turn(content: str, agents: list[AgentName]) -> HistoryTurn:
    return HistoryTurn(role="assistant", content=content, agents=agents or None,
                       ts=datetime.now(UTC))


async def cancel_quietly(task: asyncio.Task | None) -> None:
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
