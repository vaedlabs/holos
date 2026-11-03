"""Save to an account (Plan C.18): a guest's browser data into the account they signed
in to, in one transaction.

    status, body = await import_guest(sessions, user_id, payload)

- Once per `import_id`: a resend gets the first result (`account_imports`, Part E #46).
- Profile: what the guest's profile names is added to the account's saved text, in the
  words the account's profile resolution reads back (every catalogue term round-trips,
  Part D); nothing the account already says is removed. Over-matching is the safe way.
- History: the turns in order, with their times.
- Logs: each entry is read and gated again against the account profile, now updated.
  An entry that can't be read is skipped and listed. A conflict is never a reason to
  skip: the entry is what the person did. Its browser warnings keep their left-out
  marks; a conflict the browser never showed is imported with its warning and listed
  for review (owner, 3 Nov 2026, Part E #46).

The guest session already ended when the person signed in (no session fixation, P4.2);
the browser clears its own copy once the import succeeds (P5).
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text

from app.agents.schemas import ImportLog, ImportPayload, StagedWrite, UserProfile
from app.data.repositories import MessageRepository, ProfileRepository
from app.guardrails.loader import get_guardrails
from app.orchestration.staging import check_write, refusal, warning_text, warnings_of
from app.storage.context import Sessions
from app.storage.logs import insert_log
from app.storage.profile import resolve_profile

FUTURE_SLACK = timedelta(days=1)  # a phone's clock may run ahead; more is a bad entry


async def import_guest(sessions: Sessions, user_id: int,
                       payload: ImportPayload) -> dict[str, Any]:
    async with sessions() as session, session.begin():
        first = (await session.execute(text(
            "INSERT INTO account_imports (user_id, import_id) VALUES (:u, :i) "
            "ON CONFLICT DO NOTHING RETURNING import_id"),
            {"u": user_id, "i": payload.import_id})).first()
        if first is None:  # a resend: waits for the first one's commit, then reads it
            return (await session.execute(text(
                "SELECT result FROM account_imports WHERE user_id = :u AND import_id = :i"),
                {"u": user_id, "i": payload.import_id})).scalar_one()

        profiles = ProfileRepository(session, user_id)
        if payload.profile is not None:
            await _merge_profile(profiles, payload.profile)
        profile = resolve_profile(await profiles.get_medical(),
                                  await profiles.get_preferences()).profile

        messages = MessageRepository(session, user_id)
        for turn in payload.history:
            agents = ",".join(turn.agents or [])
            await messages.add(turn.role, turn.content,
                               agent_type="user" if turn.role == "user" else agents or "holos",
                               created_at=turn.ts)

        skipped, review, logged = [], [], 0
        for index, raw in enumerate(payload.logs):
            entry, problem = _read(raw)
            if entry is None:
                skipped.append({"index": index, "reason": problem})
                continue
            checked = check_write(entry.entry.kind, entry.entry.args, profile)
            if (reason := refusal(checked)) is not None:
                skipped.append({"index": index, "reason": reason})
                continue
            write, new = _rewarned(entry.entry, warnings_of(entry.entry.kind,
                                                            entry.entry.args, checked))
            await insert_log(session, user_id, write, at=entry.at)
            logged += 1
            if new:
                review.append({"index": index, "warnings": [warning_text(w) for w in new]})

        result = {"imported": {"history": len(payload.history), "logs": logged},
                  "skipped": skipped, "review": review}
        await session.execute(text(
            "UPDATE account_imports SET result = CAST(:r AS json) "
            "WHERE user_id = :u AND import_id = :i"),
            {"r": _json(result), "u": user_id, "i": payload.import_id})
        return result


def _read(raw: dict) -> tuple[ImportLog | None, str]:
    try:
        entry = ImportLog.model_validate(raw)
    except ValidationError:
        return None, "this entry can't be read"
    if entry.at > datetime.now(UTC) + FUTURE_SLACK:
        return None, "this entry is dated in the future"
    return entry, ""


def _rewarned(write: StagedWrite, now: list) -> tuple[StagedWrite, list]:
    """The account's warnings, with the browser's left-out marks; and the conflicts the
    browser never showed."""
    seen = {(w.item, w.rule_id): w for w in write.conflicts}
    marked = [w.model_copy(update={"left_out": seen[(w.item, w.rule_id)].left_out})
              if w.kind == "conflict" and (w.item, w.rule_id) in seen else w for w in now]
    new = [w for w in now if w.kind == "conflict" and (w.item, w.rule_id) not in seen]
    return write.model_copy(update={"warnings": marked}), new


async def _merge_profile(profiles: ProfileRepository, guest: UserProfile) -> None:
    medical, preferences = await profiles.get_medical(), await profiles.get_preferences()
    have = resolve_profile(medical, preferences).profile
    catalogue = get_guardrails().catalogue
    names = {c.id: c.name for c in catalogue.conditions}
    terms = catalogue.profile_terms
    conditions = [names[c] for c in guest.condition_ids
                  if c in names and c not in have.condition_ids]
    food = [f"{terms.allergens[a][0]} allergy" for a in guest.allergen_tags
            if a not in have.allergen_tags]
    food += [terms.diets[d][0] for d in guest.diet_tags if d not in have.diet_tags]
    old_notes = getattr(medical, "notes", None) or ""
    notes = guest.notes.strip()
    medical_fields = {}
    if conditions:
        medical_fields["conditions"] = _joined(getattr(medical, "conditions", None), conditions)
    if notes and notes not in old_notes:
        medical_fields["notes"] = "; ".join(p for p in (old_notes.strip(), notes) if p)
    if medical_fields:
        await profiles.save_medical(**medical_fields)
    if food:
        await profiles.save_preferences(dietary_restrictions=_joined(
            getattr(preferences, "dietary_restrictions", None), food))


def _joined(old: str | None, new: list[str]) -> str:
    return ", ".join(p for p in ((old or "").strip(), *new) if p)


def _json(value: Any) -> str:
    return json.dumps(value, default=str)
