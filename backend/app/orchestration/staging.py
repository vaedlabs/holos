"""A chat turn's writes (Plan C.17): gated when a coach stages them, then committed or
held for the person's confirmation once the coach's reply passed the gate.

    tools.gate_write = write_gate(profile)            # a coach's log_* calls, gated
    writes = turn_writes([(result, tools.untrusted)])  # after the sections
    saved = await commit_writes(session, user_id, writes, profile_hash, trace_id)
    saved = guest_writes(writes)                       # guests: the browser stores them
    reason = recheck(kind, payload, profile)           # confirm: the current profile

Nothing is committed during the tool loop. A logged entry is something the person
already ate or did, so a conflict with the profile doesn't refuse it: the entry keeps
its warnings and waits for the person's confirmation, where they may say what they left
out (the peanuts picked out of the poha). Only an entry the gate can't read is refused
(owner, 3 Nov 2026, Part E #45). A coach whose reply failed the gate (it failed, or its
final reply still had blocked items) loses its writes: the turn they came from wasn't
safe. A web search makes the coach's writes wait too, since search results could have
steered its log calls; a search only reaches the coach that ran it, so the other
coaches' writes commit as usual.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import schemas
from app.agents.display import NAMES
from app.agents.schemas import (
    WRITE_ARGS,
    AgentResult,
    StagedWrite,
    UserProfile,
    WriteKind,
    WriteWarning,
)
from app.agents.tools import GateHook, GateResult, ToolContext
from app.data.state_store import Pending, stage_pending
from app.guardrails import types
from app.guardrails.gate import UNCHECKED_RULE, gate
from app.storage.logs import insert_log

DOMAIN: dict[WriteKind, str] = {"workout": "physical", "meal": "nutrition",
                                "practice": "mental"}
NO_PROFILE = UserProfile(condition_ids=[], allergen_tags=[], diet_tags=[], notes="")
UNCHECKABLE = "this entry can no longer be checked"


def check_write(kind: WriteKind, args: BaseModel, profile: UserProfile | None
                ) -> types.GateResult:
    """C.14 step 3: a write is gated like a plan's items, on its own content."""
    return gate(DOMAIN[kind], args.model_dump(mode="json"), profile or NO_PROFILE)


def refusal(checked: types.GateResult) -> str | None:
    """Why the entry can't be saved at all, or None: only an entry the gate can't read
    (an unknown catalogue ID). A conflict is a warning to confirm, and a blocked
    sentence in the note is already removed, like prose in a reply (Part E #18)."""
    if not checked.malformed:
        return None
    return "; ".join(sorted({d.reason for d in checked.decisions if d.action == "block"}))


def warnings_of(kind: WriteKind, args: BaseModel, checked: types.GateResult
                ) -> list[WriteWarning]:
    """Each rule that fired on an item, with what set it off."""
    names = ([f.name for f in args.foods] if kind == "meal"
             else [_item_name(args)])
    reasons = {d.rule_id: d.reason for d in checked.decisions}
    out = []
    for verdict in checked.items:
        for rule_id, attributes in verdict.attributes:
            out.append(WriteWarning(
                kind="unchecked" if rule_id == UNCHECKED_RULE else "conflict",
                item=names[verdict.index][:60], rule_id=rule_id,
                attributes=[a[:40] for a in attributes[:10]],
                reason=reasons.get(rule_id, "")[:200]))
    return out


def _item_name(args: BaseModel) -> str:
    return NAMES.get(args.catalogue_id, str(args.catalogue_id))


def warning_text(warning: WriteWarning) -> str:
    """"Poha: contains peanut, which is in your allergies"; "…: left out peanut"."""
    named = ", ".join(a.replace("_", " ") for a in warning.attributes)
    if warning.left_out:
        return f"{warning.item}: left out {named}"
    if warning.rule_id.startswith("DI-ALG"):
        return f"{warning.item}: contains {named}, which is in your allergies"
    return f"{warning.item}: {warning.reason[0].lower()}{warning.reason[1:]}"


def confirm_attributes(write: StagedWrite) -> list[str]:
    """What the person may say they left out: the conflicting allergens and diet
    conflicts of a meal (a picked-out ingredient). An exercise's knee load can't be
    left out of the squats."""
    if write.kind != "meal":
        return []
    return sorted({a for w in write.conflicts if w.rule_id.startswith("DI-")
                   for a in w.attributes})


def write_gate(profile: UserProfile | None) -> GateHook:
    """The gate hook for one turn's write tools, against the profile the coach sees."""

    async def gate_write(kind: WriteKind, args: BaseModel, ctx: ToolContext) -> GateResult:
        checked = check_write(kind, args, profile)
        decisions = tuple(schemas.Decision(**asdict(d)) for d in checked.decisions)
        reason = refusal(checked)
        if reason is not None:
            return GateResult(allowed=False, reason=reason, decisions=decisions)
        return GateResult(allowed=True, decisions=decisions,
                          args=type(args).model_validate(checked.content),
                          warnings=tuple(warnings_of(kind, args, checked)))

    return gate_write


def recheck(write: StagedWrite, profile: UserProfile | None) -> str | None:
    """Confirm time (C.17 step 2): the held entry against the current profile. The
    person confirms the warnings they were shown; a conflict they weren't shown (the
    profile changed since) means they haven't confirmed it, so the entry isn't saved."""
    checked = check_write(write.kind, write.args, profile)
    if (reason := refusal(checked)) is not None:
        return reason
    seen = {(w.item, w.rule_id) for w in write.conflicts}
    new = [w for w in warnings_of(write.kind, write.args, checked)
           if w.kind == "conflict" and (w.item, w.rule_id) not in seen]
    if new:
        return "your profile changed since: " + "; ".join(warning_text(w) for w in new)
    return None


def held_entry(kind: WriteKind, payload: dict) -> StagedWrite | None:
    """A held write as stored ({"args", "warnings"}), or None if it no longer reads
    (an entry held before a schema change can't be checked, so it isn't saved)."""
    try:
        return StagedWrite(kind=kind, args=WRITE_ARGS[kind].model_validate(payload["args"]),
                           warnings=payload.get("warnings") or [])
    except (ValidationError, KeyError, TypeError):
        return None


def held_payload(write: StagedWrite) -> dict:
    return {"args": write.args.model_dump(mode="json"),
            "warnings": [w.model_dump(mode="json") for w in write.warnings]}


def with_left_out(write: StagedWrite, left_out: set[str]) -> StagedWrite:
    """The entry as logged: the conflicts the person left out are marked."""
    marked = [w.model_copy(update={"left_out": bool(set(w.attributes) & left_out)})
              if w.kind == "conflict" else w for w in write.warnings]
    return write.model_copy(update={"warnings": marked})


def profile_hash(profile: UserProfile | None) -> str:
    """sha256 of the profile as compact JSON with sorted keys (null for none). A guest's
    is the profile the browser sent, so the browser can tell whether it changed before
    it saves a pending entry (C.17); an account's is the resolved profile."""
    data = profile.model_dump(mode="json") if profile is not None else None
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class TurnWrites:
    commit: list[StagedWrite] = field(default_factory=list)
    pending: list[StagedWrite] = field(default_factory=list)


def turn_writes(coached: list[tuple[AgentResult, bool]]) -> TurnWrites:
    """Each coach's result with whether a web search entered its turn."""
    writes = TurnWrites()
    for result, untrusted in coached:
        if result.reply is None or result.removed_count:
            continue  # the reply failed the gate: its writes are discarded
        for write in result.staged_writes:
            held = untrusted or bool(write.conflicts)
            (writes.pending if held else writes.commit).append(write)
    return writes


@dataclass
class Saved:
    committed: list[tuple[StagedWrite, str | None]] = field(default_factory=list)
    pending: list[tuple[StagedWrite, Pending | None]] = field(default_factory=list)


async def commit_writes(session: AsyncSession, user_id: int, writes: TurnWrites,
                        hash_: str, trace_id: str) -> Saved:
    """Account: inside the turn's transaction, with its messages (C.2 stage 13)."""
    saved = Saved()
    for write in writes.commit:
        saved.committed.append((write, str(await insert_log(session, user_id, write))))
    conn = await session.connection()
    for write in writes.pending:
        saved.pending.append((write, await stage_pending(
            conn, user_id, write.kind, held_payload(write), hash_, trace_id)))
    return saved


def guest_writes(writes: TurnWrites) -> Saved:
    """Guest: nothing is stored here; the events carry the entries."""
    return Saved([(w, None) for w in writes.commit], [(w, None) for w in writes.pending])
