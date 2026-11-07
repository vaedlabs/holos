"""One chat request from routing to `done` (Plan C.2 stages 9–14).

    await run_chat(job, services)

Load the profile and history, route, then either gate the router's own reply or run
the chosen coaches in parallel, each section sent as soon as its coach ends (the first
before the slowest). Two or more answers get a summary from the small model, gated.
Helplines follow the sections when a coach set `risk_flag` or the crisis flag is set.
Accounts save the message, what the person saw and the turn's writes in one
transaction; guests get the turn and their entries in the events for the browser to
keep. Every "Logged" comes from what was stored (C.17, `staging`).

The work belongs to the request, not the connection (Part E #34): a dropped connection
changes nothing here. Every failure ends the stream with one terminal event.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.agents.base import AgentRun, error_code
from app.agents.display import history_text
from app.agents.schemas import (
    AgentName,
    AgentResult,
    ChatPayload,
    Usage,
    UserProfile,
)
from app.agents.style import STYLE_NOTE, writing_style
from app.agents.tools import ToolContext
from app.config.limits import (
    AGENT_DEADLINE_S,
    REQUEST_DEADLINE_S,
    RESERVE_TOKENS_IN,
    ROUTING_DEADLINE_S,
)
from app.config.speeds import ROUTER, SUMMARY
from app.data.state_store import StateStore
from app.data.stream_store import RequestEnded
from app.observability.background import Outcome
from app.observability.tracer import Trace
from app.orchestration.admission import Admitted
from app.orchestration.budget import Budget, CallMeter
from app.orchestration.composer import (
    Composer,
    Gated,
    gated,
    history_turn,
    trace_view,
    turn_text,
)
from app.orchestration.principal import Principal
from app.orchestration.services import Services
from app.orchestration.staging import (
    Saved,
    commit_writes,
    guest_writes,
    profile_hash,
    turn_writes,
    write_gate,
)
from app.providers import CallPlan, ImageInput, ProviderError, Turn
from app.providers.base import trim
from app.storage.context import Sessions, load_context, save_turn
from app.storage.images import ImageStore, image_key
from app.storage.profile import unchecked_caveat

log = logging.getLogger(__name__)

SUMMARY_CHARS = 600
NO_PROFILE = UserProfile(condition_ids=[], allergen_tags=[], diet_tags=[], notes="")
SUMMARY_PROMPT = """\
You write the closing line of Holos's answer. Several coaches (exercise, food, mental \
wellbeing) have each answered part of the person's message; their answers are below. \
Write one to three short sentences, at most 600 characters, that tie the answers \
together for this person. Use only what the coaches said: add no new advice, items, \
numbers or medical claims. Plain text, no lists, no headings."""


@dataclass
class ChatJob:
    principal: Principal
    payload: ChatPayload
    admitted: Admitted
    composer: Composer
    trace: Trace
    store: StateStore
    sessions: Sessions | None
    image: ImageInput | None = None
    images: ImageStore | None = None  # where an account's photo is kept (C.8)
    started: float = field(default_factory=time.monotonic)
    crisis_recent: bool = False  # read once, at the start (C.16)
    outcome: Outcome | None = None  # for the background writer (C.2 stage 15)

    def __post_init__(self) -> None:
        if self.outcome is None:
            self.outcome = Outcome(self.trace, self.principal.session.id_hash,
                                   self.principal.user_id)

    @property
    def deadline(self) -> float:
        return self.started + REQUEST_DEADLINE_S


async def run_chat(job: ChatJob, services: Services) -> None:
    """Stages 9–14. Never raises (except RequestEnded): every end is an event."""
    meters = _Meters(job)
    try:
        await _run(job, services, meters)
    finally:
        job.outcome.usage = meters.usage().model_dump(mode="json")


async def _run(job: ChatJob, services: Services, meters: "_Meters") -> None:
    c = job.composer
    try:
        await c.step("admitted")
        job.crisis_recent = await job.store.crisis_active(job.principal.principal_key)
        context = await load_context(job.principal, job.payload, job.sessions)
        profile, history = context.profile, context.history
        try:
            decision = await services.router.route(
                job.payload.message, plan=_plan(job, ROUTER, "router", meters,
                                                 ROUTING_DEADLINE_S),
                profile=profile, history=history, has_image=job.image is not None,
                agents=job.payload.agents)
        except ProviderError as exc:
            await _fail(job, error_code(exc), meters)
            return
        agents = list(decision.agents)
        job.outcome.route = decision.kind
        await c.step("routed", agents[0] if len(agents) == 1 else None,
                     ", ".join(agents) or decision.kind)
        own = summary = None
        results: dict[AgentName, AgentResult] = {}
        untrusted: dict[AgentName, bool] = {}
        if not agents:
            own = gated(decision.reply or "", profile or NO_PROFILE)
            await c.reply(own)
        else:
            results, untrusted = await _coaches(job, services, agents, profile, history,
                                                meters, unchecked_caveat(context.unchecked))
            answered = [a for a in agents if results[a].reply is not None]
            if not answered:
                await _fail(job, results[agents[0]].error or "unavailable", meters)
                return
            if len(answered) < len(agents):
                await c.notice("partial_result")
            if len(answered) >= 2:
                summary = await _summary(job, services, {a: results[a] for a in answered},
                                         profile, meters)
                if summary is not None:
                    await c.summary(summary)
        await _helplines(job, results)
        turn = history_turn(turn_text(own=own, summary=summary,
                                      results=[results[a] for a in agents]), agents)
        writes = turn_writes([(results[a], untrusted[a]) for a in results])
        if job.principal.user_id is None:
            hash_ = profile_hash(job.payload.guest_profile)
            saved = guest_writes(writes)
        else:
            hash_ = profile_hash(profile)

            async def also(session) -> Saved:
                return await commit_writes(session, job.principal.user_id, writes, hash_,
                                           job.admitted.trace_id)

            key = await _keep_image(job)
            try:
                saved = await save_turn(job.principal, job.sessions,
                                        job.payload.client_request_id, job.payload.message,
                                        turn, also, image_key=key)
            except BaseException:
                if key is not None:  # no message points at it: don't leave it behind
                    await _forget_image(job, key)
                raise
        await _writes(job, saved, hash_)
        decisions = [d for r in results.values() for d in r.decisions]
        decisions += [*(own.decisions if own else ()), *(summary.decisions if summary else ())]
        sources = [s for r in results.values() for s in r.sources]
        # Every decision, retries included (C.14 step 6), not only what the person saw
        job.outcome.decisions = [*(d for r in results.values() for d in r.decided),
                                 *(own.decisions if own else ()),
                                 *(summary.decisions if summary else ())]
        await c.done(trace_view(job.trace, decision.kind, agents, decisions, sources,
                                meters.usage()), meters.usage(), turn)
        # Honest (C.5): only when every coach it chose answered, or Holos answered itself
        job.outcome.success = all(results[a].reply is not None for a in agents)
    except RequestEnded:
        raise  # someone ended this request as interrupted: stop quietly
    except Exception:
        log.exception("chat request failed: trace=%s cause=bug", job.admitted.trace_id)
        if not c.ended:
            await c.error("unavailable")


async def _fail(job: ChatJob, code: str, meters: "_Meters") -> None:
    """No answer at all: a spend cap is a notice (C.5), anything else an error."""
    c = job.composer
    if code == "cap_reached":
        await c.notice("cap_reached")
        await c.done(trace_view(job.trace, "coaching", [], [], [], meters.usage()),
                     meters.usage())
    else:
        await c.error(code)


async def _coaches(job: ChatJob, services: Services, agents: list[AgentName],
                   profile: UserProfile | None, history, meters: "_Meters",
                   caveat: str | None
                   ) -> tuple[dict[AgentName, AgentResult], dict[AgentName, bool]]:
    """In parallel; each section goes out as its coach ends (C.2 stage 10). Also, per
    coach, whether a web search entered its turn (its writes then wait, C.17)."""
    c = job.composer
    deadline = min(time.monotonic() + AGENT_DEADLINE_S, job.deadline)
    untrusted: dict[AgentName, bool] = {}

    async def one(agent: AgentName) -> tuple[AgentName, AgentResult]:
        await c.step("agent_started", agent)
        photo = agent == "nutrition" and job.image is not None
        tools = ToolContext(mode="account" if job.principal.user_id else "guest",
                            trace_id=job.admitted.trace_id, user_id=job.principal.user_id,
                            sessions=job.sessions, gate_write=write_gate(profile),
                            search=services.search, search_keys=job.admitted.search_keys)
        result = await services.coaches[agent].run(AgentRun(
            message=job.payload.message, profile=profile, history=history, tools=tools,
            deadline=deadline, principal=job.principal.fairness_key,
            meter=meters.get("meal_photo" if photo else agent),
            images=(job.image,) if photo else (), others=tuple(a for a in agents if a != agent),
            trace=job.trace, crisis_recent=job.crisis_recent))
        if caveat and result.reply is not None and result.reply.kind == "plan":
            result.warnings.append(caveat)
        untrusted[agent] = tools.untrusted
        return agent, result

    results: dict[AgentName, AgentResult] = {}
    composing = False
    tasks = [asyncio.create_task(one(a)) for a in agents]
    try:
        for done in asyncio.as_completed(tasks):
            agent, result = await done
            if not composing:
                await c.step("composing")
                composing = True
            await c.section(agent, result)
            results[agent] = result
    finally:  # a request cut off (hard limit, ended elsewhere) stops its coaches too
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return results, untrusted


async def _keep_image(job: ChatJob) -> str | None:
    """An account's photo, stored before its message so the message can name it. If
    storage fails the turn is still saved, without the photo (logged)."""
    if job.image is None or job.images is None:
        return None
    key = image_key(job.principal.user_id)
    try:
        await job.images.put(key, job.image.data)
    except Exception:
        log.warning("image not stored: trace=%s", job.admitted.trace_id, exc_info=True)
        return None
    return key


async def _forget_image(job: ChatJob, key: str) -> None:
    try:
        await job.images.delete_prefix(key)
    except Exception:
        log.warning("orphan image left: trace=%s", job.admitted.trace_id, exc_info=True)


async def _writes(job: ChatJob, saved: Saved, hash_: str) -> None:
    """After the commit (C.2 stage 14): what was logged, then what waits for the
    person's confirmation."""
    c = job.composer
    if saved.committed:
        await c.committed(saved.committed)
    said = datetime.now(UTC)
    for write, pending in saved.pending:
        if pending is None:  # guest
            await c.pending_write(write, at=said, profile_hash=hash_)
        else:
            await c.pending_write(write, at=pending.at, write_id=str(pending.write_id))


async def _summary(job: ChatJob, services: Services, results: dict[AgentName, AgentResult],
                   profile: UserProfile | None, meters: "_Meters") -> Gated | None:
    """The small model ties two or more answers together; gated like any prose. A
    failed summary is left out, not an error: the answers are already sent."""
    answers = "\n\n".join(f"{agent} coach:\n{history_text(r.reply, 1500)}"
                          for agent, r in results.items())
    style = STYLE_NOTE[writing_style(job.payload.message)]
    prompt = f"The person wrote: {job.payload.message}\n\n{answers}\n\n({style})"
    try:
        reply = await services.summary.generate(
            [Turn("user", prompt)], plan=_plan(job, SUMMARY, "summary", meters),
            system=SUMMARY_PROMPT)
    except ProviderError:
        return None  # on the trace already
    if not reply.text or reply.truncated:
        return None
    text = gated(trim(reply.text.strip(), SUMMARY_CHARS), profile or NO_PROFILE)
    return text if text.text else None


async def _helplines(job: ChatJob, results: dict[AgentName, AgentResult]) -> None:
    if any(r.reply is not None and r.reply.risk_flag for r in results.values()):
        await job.composer.helplines(full=True)
    elif job.crisis_recent:
        await job.composer.helplines(full=False)


def _plan(job: ChatJob, speed, kind: str, meters: "_Meters", within: float | None = None
          ) -> CallPlan:
    deadline = job.deadline if within is None else min(time.monotonic() + within,
                                                       job.deadline)
    return CallPlan(deadline=deadline, speed=speed, principal=job.principal.fairness_key,
                    meter=meters.get(kind), kind=kind, trace=job.trace)


class _Meters:
    """One CallMeter per kind of call (each reserves its own input size), summed for
    the `done` event."""

    def __init__(self, job: ChatJob):
        self._budget = Budget(job.store)
        self._keys = job.admitted.spend_keys
        self._meters: dict[str, CallMeter] = {}

    def get(self, kind: str) -> CallMeter:
        if kind not in self._meters:
            self._meters[kind] = CallMeter(self._budget, self._keys, RESERVE_TOKENS_IN[kind])
        return self._meters[kind]

    def usage(self) -> Usage:
        meters = self._meters.values()
        return Usage(tokens_in=sum(m.tokens_in for m in meters),
                     tokens_out=sum(m.tokens_out for m in meters),
                     cost_usd=float(sum((m.usd for m in meters), start=0)))
