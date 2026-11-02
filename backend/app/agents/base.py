"""BaseAgent: one coach's turn (Plan C.10). Subclasses give only the domain, the reply
schema, their speeds and their guidance; the prompt prefix, tools and safety rules come
from the catalogue and rules.yaml.

    result = await PhysicalAgent(llm).run(AgentRun(message, profile, history, tools,
                                                   deadline, principal))

1. The prompt: static prefix (system), then profile, history and the message.
2. Tool rounds (at most TOOL_ROUNDS; a round's calls run at the same time), then the
   reply in the schema. A call with tools keeps the final call's reserve (its p95 +
   the timeout overshoot) on the deadline; without time for both, the call goes
   straight to the reply.
3. The gate (C.14; photo mode for a meal photo). A blocked item, a malformed reply, or
   a "logged" claim without a staged write (Part E #12) gets one retry with the
   reasons, if the reserve is left; the retry starts without the first try's writes.
4. Then blocked items are dropped ("N removed for your safety"). None left: the coach
   is told what was removed and why, and writes the reply itself without items (Part
   E #38); only if that fails too, the domain's fixed reply. A provider failure gives
   no reply, only an error code: the app shows it as a status with Retry (C.5).
   Any other exception is a bug: logged with its stack, the same error code, so one
   coach's failure never ends the others' answers.
5. Every step and model call goes on the request's trace (Part E #39).
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Protocol

from pydantic import BaseModel

from app.agents import schemas
from app.agents.prefix import prefix
from app.agents.schemas import (
    AgentError,
    AgentName,
    AgentResult,
    HistoryTurn,
    UserProfile,
    llm_json_schema,
)
from app.agents.style import STYLE_NOTE, writing_style
from app.agents.tools import AGENT_TOOLS, ToolContext
from app.config.limits import REASONING_ALLOWANCE_LOW, TOOL_ROUNDS
from app.config.speeds import TIMEOUT_OVERSHOOT_S, Speed
from app.guardrails.gate import gate
from app.guardrails.types import GateResult
from app.observability.tracer import Trace, cause_of
from app.providers import (
    CallPlan,
    GenerateOptions,
    ImageInput,
    LLMResult,
    MalformedOutput,
    Message,
    Meter,
    NoCapacity,
    OverBudget,
    ProviderError,
    ToolResult,
    ToolSpec,
    Turn,
)

log = logging.getLogger(__name__)


# Physical, Mental and Nutrition (text and photos): gpt-6-luna, reasoning low (C.9,
# Part E #29). P4.12 may move the model name to settings.
MODEL = "gpt-6-luna"
# A retry rewrites the same reply, so it takes about as long as the first try: live, 16
# retries took 0.13-1.31x the first try's time, median 0.83 (owner, 2 Nov 2026)
RETRY_TIME_RATIO = 1.35

# Only when the coach couldn't explain itself either (Part E #38)
UNSAFE_FALLBACK = {
    "physical": "I couldn't find exercises for this that are safe with your profile. Tell "
                "me a bit more about what you'd like, or check with your physiotherapist "
                "first.",
    "nutrition": "I couldn't find foods for this that fit your allergies and diet. Tell me "
                 "a bit more about what you'd like and I'll try again.",
    "mental": "I couldn't find a practice for this that's safe with your profile. Tell me "
              "a little more about what you need.",
}
REMOVED_NOTE = "{n} {items} removed for your safety"
AREA = {"physical": "exercise", "nutrition": "food", "mental": "mental wellbeing"}
LOG_RETRY = ("You said something was logged or saved, but no log tool returned "
             "\"staged\". If the person asked to log something, call the log tool; "
             "otherwise don't say it was logged.")
# Prompt guidance, not wording for the person (C.16)
CRISIS_NOTE = ("This person recently wrote something that suggested they may be in "
               "distress. Be especially gentle and supportive, don't push, and say that "
               "support is available if they want it.")
EXPLAIN = ("Holos note: the safety check removed {what} because of the person's profile: "
           "{reasons}. Reply with kind \"answer\" and no items: say briefly, in your own "
           "words and in the person's language, what you couldn't suggest and why, and ask "
           "what would help instead. Describe the kind of movement or food (\"deep knee "
           "bending\", \"wheat\") rather than naming the removed items: the safety check "
           "removes any sentence that names them.")


class Generator(Protocol):
    async def generate(self, messages: list[Message], *, plan: CallPlan,
                       system: str | None = None, tools: list[ToolSpec] | None = None,
                       schema: type[BaseModel] | None = None) -> LLMResult: ...


@dataclass
class AgentRun:
    message: str
    profile: UserProfile | None
    history: list[HistoryTurn]
    tools: ToolContext
    deadline: float  # monotonic clock time (C.10: 60 s per coach)
    principal: str
    meter: Meter | None = None
    images: tuple[ImageInput, ...] = ()  # a meal photo (nutrition only)
    others: tuple[AgentName, ...] = ()  # the other coaches answering this message
    trace: Trace | None = None  # the request's trace; None: a trace of this run alone
    crisis_recent: bool = False  # the crisis check matched in the last 30 minutes (C.16)


@dataclass
class _Try:
    reply: BaseModel | None = None
    gated: GateResult | None = None
    retry_because: str | None = None
    why: str = ""  # the retry's category for the trace: blocked, log_claim, a cause
    messages: list[Message] = field(default_factory=list)


class BaseAgent:
    domain: ClassVar[AgentName]
    schema: ClassVar[type[BaseModel]]
    speed: ClassVar[Speed]
    plan_speed: ClassVar[Speed]  # a reply that may hold a week plan (Part E #38)
    photo_speed: ClassVar[Speed | None] = None
    guidance: ClassVar[str] = ""  # domain guidance in the static prefix

    def __init__(self, llm: Generator, clock: Callable[[], float] = time.monotonic):
        self.llm = llm
        self.clock = clock
        self.tools = {t.name: t for t in AGENT_TOOLS[self.domain]}
        self.specs = [ToolSpec(t.name, t.description, llm_json_schema(t.args_model))
                      for t in self.tools.values()]
        self.system = prefix(self.domain, self.guidance)

    @classmethod
    def options(cls) -> GenerateOptions:
        """The route's options (C.9): the reply cap plus the reasoning allowance, because
        the Responses API counts reasoning tokens toward max_output_tokens."""
        return GenerateOptions(model=MODEL, reasoning="low",
                               max_output_tokens=(schemas.REPLY_TOKEN_CAP[cls.domain]
                                                  + REASONING_ALLOWANCE_LOW))

    async def run(self, run: AgentRun) -> AgentResult:
        if run.trace is None:
            run.trace = Trace("untraced", self.clock)
        began = run.trace.ms()
        try:
            result = await self._run(run)
        except ProviderError as exc:
            result = self._failed(run, error_code(exc), cause_of(exc))
        except Exception as exc:
            log.error("coach failed: trace=%s agent=%s cause=bug", run.trace.trace_id,
                      self.domain, exc_info=exc)
            result = self._failed(run, "unavailable", "bug")
        run.trace.step("coach", self.domain, "error" if result.error else "ok",
                       began_ms=began)
        return result

    async def _run(self, run: AgentRun) -> AgentResult:
        photo = bool(run.images)
        speed = self.photo_speed if photo and self.photo_speed else self.speed
        # Any reply may be a week plan, which takes longer to write than a short answer
        reply_speed = speed if photo else self.plan_speed
        messages = self._messages(run)
        last: _Try | None = None
        for attempt in range(2):
            if attempt:
                run.tools.clear_staged()
                run.trace.step("retry", self.domain, detail=last.why)
            began = self.clock()
            try:
                current = await self._try(messages, run, speed, reply_speed, photo)
            except MalformedOutput as exc:
                current = _Try(retry_because=f"The reply wasn't valid: {str(exc)[:300]}",
                               why=exc.cause, messages=messages)
            last = current
            if (current.retry_because is None or attempt
                    or not self._room_to_retry(run, self.clock() - began, speed)):
                break
            messages = [*current.messages, Turn("user", current.retry_because)]
        if last.gated is None:
            raise MalformedOutput("no valid reply after the retry", cause=last.why or None)
        return await self._finish(last, run, speed)

    # --- One try: tool rounds, the reply, the gate ---

    async def _try(self, messages: list[Message], run: AgentRun, speed: Speed,
                   reply_speed: Speed, photo: bool) -> _Try:
        """speed: a call that asks for tools; reply_speed: the reply, which any call may
        give instead."""
        messages = list(messages)
        reserve = reply_speed.p95 + TIMEOUT_OVERSHOOT_S
        for round_ in range(TOOL_ROUNDS + 1):
            left = run.deadline - self.clock()
            tools = round_ < TOOL_ROUNDS and left >= speed.p95 + reserve
            plan = CallPlan(deadline=run.deadline - reserve if tools else run.deadline,
                            speed=reply_speed, principal=run.principal, meter=run.meter,
                            kind="meal_photo" if photo else self.domain, trace=run.trace)
            result = await self.llm.generate(messages, plan=plan, system=self.system,
                                             tools=self.specs if tools else None,
                                             schema=self.schema)
            if result.turn is not None:
                messages.append(result.turn)
            if result.tool_calls and tools:
                messages += await self._run_tools(result, run)
                continue
            if result.truncated or not isinstance(result.parsed, self.schema):
                raise MalformedOutput("reply missing or cut off",
                                      cause="truncated" if result.truncated else None)
            return self._gate(result.parsed, run, photo, messages)
        raise AssertionError("unreachable: the last round has no tools")

    async def _run_tools(self, result: LLMResult, run: AgentRun) -> list[Message]:
        async def one(call) -> ToolResult:
            tool = self.tools.get(call.name)
            began = run.trace.ms()
            output = (await tool.run(call.arguments, run.tools) if tool is not None
                      else {"status": "unknown_tool"})
            status = output.get("status", "ok") if isinstance(output, dict) else "ok"
            run.trace.step("tool_call", self.domain, str(status), call.name, began)
            return ToolResult(call.id, call.name, output)

        return list(await asyncio.gather(*(one(c) for c in result.tool_calls)))

    def _gate(self, reply: BaseModel, run: AgentRun, photo: bool,
              messages: list[Message]) -> _Try:
        gated = gate(self.domain, reply.model_dump(mode="json"), run.profile or _NO_PROFILE,
                     purpose="photo" if photo else "plan")
        run.trace.step("gate", self.domain, gated.action)
        because, why = None, ""
        if gated.needs_retry:
            # The whole reply: live, a week plan's retry came back with only the swaps
            # and the rest of the week was lost (3 of 9 retries, Part E #38)
            because = ("Your reply was checked against the person's profile and these "
                       "items are not allowed: " + _blocked(gated) + ". Write your whole "
                       "reply again: keep every other item as it was and replace only "
                       "these with safe alternatives from the catalogue.")
            why = "blocked"
        elif (any(s.kind == "write_claim" for s in gated.scrubbed)
              and not run.tools.staged_writes):
            because, why = LOG_RETRY, "log_claim"
        return _Try(reply, gated, because, why, messages)

    # --- The result ---

    async def _finish(self, last: _Try, run: AgentRun, speed: Speed) -> AgentResult:
        gated = last.gated
        content = dict(gated.content)
        blocked = set(gated.blocked_items)
        kept = [(item, verdict) for item, verdict in zip(content.get("items", []),
                                                         gated.items, strict=True)
                if verdict.index not in blocked]
        warnings = list(gated.caveats)
        if blocked:
            reasons = sorted({d.reason for d in gated.decisions if d.action == "block"})
            n = len(blocked)
            warnings.append(REMOVED_NOTE.format(n=n, items="item" if n == 1 else "items")
                            + ": " + "; ".join(reasons))
        if content.get("kind") == "plan" and not kept:
            return await self._explain(last, run, speed, warnings, "the items")
        content["items"] = [item for item, _ in kept]
        known = {s.id for s in run.tools.sources}
        content["source_ids"] = [i for i in content.get("source_ids", []) if i in known]
        if not content.get("summary") and not content["items"] and not run.tools.staged_writes:
            # Every sentence was unsafe. With a staged write the summary may be empty:
            # the "logged" confirmation comes from the commit result (C.17)
            return await self._explain(last, run, speed, warnings, "every sentence")
        return AgentResult(
            reply=self.schema.model_validate(content),
            warnings=warnings,
            removed_count=len(blocked),
            item_caveats=[list(v.caveats) for _, v in kept],
            decisions=[*decisions_of(gated), *run.tools.decisions],
            sources=[s for s in run.tools.sources if s.id in content["source_ids"]],
            staged_writes=list(run.tools.staged_writes),
        )

    async def _explain(self, last: _Try, run: AgentRun, speed: Speed,
                       warnings: list[str], what: str) -> AgentResult:
        """Nothing safe was left: the coach says why in its own words, without items.
        Its reply is gated like any other; if it fails, the fixed reply (Part E #38)."""
        gated = last.gated
        began = run.trace.ms()
        reply = None
        if self._time_left(run, speed):
            note = EXPLAIN.format(what=what, reasons=_blocked(gated) or "unsafe content")
            plan = CallPlan(deadline=run.deadline, speed=speed, principal=run.principal,
                            meter=run.meter, kind=self.domain, trace=run.trace)
            try:
                result = await self.llm.generate([*last.messages, Turn("user", note)],
                                                 plan=plan, system=self.system,
                                                 schema=self.schema)
                if isinstance(result.parsed, self.schema) and not result.truncated:
                    reply = result.parsed
            except ProviderError:
                pass  # recorded on the trace by the provider
        if reply is not None:
            content = {**reply.model_dump(mode="json"), "kind": "answer", "items": [],
                       "source_ids": []}
            told = gate(self.domain, content, run.profile or _NO_PROFILE)
            if told.content.get("summary"):
                run.trace.step("explain", self.domain, began_ms=began)
                return AgentResult(
                    reply=self.schema.model_validate(told.content), warnings=warnings,
                    removed_count=len(gated.blocked_items),
                    decisions=[*decisions_of(gated), *decisions_of(told), *run.tools.decisions])
        run.trace.step("explain", self.domain, "fixed_reply", began_ms=began)
        fixed = self.schema(kind="answer", summary=UNSAFE_FALLBACK[self.domain], items=[],
                            notes=[], source_ids=[], follow_up=None, risk_flag=False)
        return AgentResult(reply=fixed, warnings=warnings,
                           removed_count=len(gated.blocked_items),
                           decisions=[*decisions_of(gated), *run.tools.decisions])

    def _failed(self, run: AgentRun, error: AgentError, cause: str) -> AgentResult:
        """No answer: the app shows a status with Retry, not a chat message (C.5)."""
        run.trace.step("failed", self.domain, cause)
        return AgentResult(reply=None, error=error, decisions=list(run.tools.decisions))

    # --- Helpers ---

    def _messages(self, run: AgentRun) -> list[Message]:
        """Profile, then history, then the message (C.9 prompt order)."""
        messages: list[Message] = [Turn("user", _profile_text(run.profile)),
                                   Turn("assistant", "Noted.")]
        for turn in run.history:
            messages.append(Turn(turn.role, turn.content))
        messages.append(Turn("user", f"{run.message}\n\n({self._note(run)})",
                             tuple(run.images)))
        return messages

    def _note(self, run: AgentRun) -> str:
        """Per-turn context (Part D: 46 of 374 replies covered another coach's area, 5
        came back in English to someone writing Hindi or Hinglish)."""
        note = f"Holos note: {STYLE_NOTE[writing_style(run.message)]}"
        if run.others:
            names = " and ".join(AREA[a] for a in run.others)
            note += (f" The {names} {'coach is' if len(run.others) == 1 else 'coaches are'} "
                     f"answering the rest of this message: answer only the "
                     f"{AREA[self.domain]} part.")
        if run.crisis_recent and self.domain == "mental":
            note += " " + CRISIS_NOTE
        return note

    def _room_to_retry(self, run: AgentRun, took: float, speed: Speed) -> bool:
        """Time for a retry the size of the first try, measured, not a fixed figure; a
        try that failed fast says little, so never less than a short answer's p50."""
        need = max(took, speed.p50) * RETRY_TIME_RATIO + TIMEOUT_OVERSHOOT_S
        return run.deadline - self.clock() >= need

    def _time_left(self, run: AgentRun, speed: Speed) -> bool:
        return run.deadline - self.clock() >= speed.p95 + TIMEOUT_OVERSHOOT_S


_NO_PROFILE = UserProfile(condition_ids=[], allergen_tags=[], diet_tags=[], notes="")
def _profile_text(profile: UserProfile | None) -> str:
    if profile is None:
        return "My profile: none yet (a guest)."
    lines = [
        f"conditions: {', '.join(profile.condition_ids) or 'none'}",
        f"allergies: {', '.join(profile.allergen_tags) or 'none'}",
        f"diet: {', '.join(profile.diet_tags) or 'none'}",
    ]
    if profile.notes.strip():
        lines.append(f"my notes: {profile.notes.strip()}")
    return "My profile. " + "; ".join(lines) + "."


def _blocked(gated: GateResult) -> str:
    return "; ".join(sorted({f"{d.reason} ({', '.join(d.offending_items)})"
                             for d in gated.decisions if d.action == "block"}))


def decisions_of(gated: GateResult) -> list[schemas.Decision]:
    return [schemas.Decision(action=d.action, rule_id=d.rule_id,
                             rules_version=d.rules_version, reason=d.reason,
                             offending_items=list(d.offending_items))
            for d in gated.decisions]


def error_code(exc: ProviderError) -> AgentError:
    if isinstance(exc, MalformedOutput):
        return "malformed"
    if isinstance(exc, OverBudget):
        return "cap_reached"
    if isinstance(exc, NoCapacity):
        return "busy"
    return "unavailable"

