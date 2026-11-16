"""A repeated entry (Plan C.17, Part E #67): the log tools' check for an entry already
logged that a new one matches.

    tools.find_repeat = repeat_finder(guest_logs(payload.guest_logs))   # guest
    tools.find_repeat = repeat_finder()                                 # account

A coach can log what the person logged before: asked "is my breakfast logged?", after a
message sent again, or with a time given afterwards ("the chai was at 11:30"). Wording
only steers the model, so the match is code (Part E #65): a meal with the same meal slot
on the same day and a food in common (names folded as the gate folds them); a workout or
practice with the same catalogue ID within 2 hours (another activity: also the same
name). A food is in common when every word of one food's name is in the other's (owner,
16 Nov 2026, Part E #67): live, one lunch sent twice came back as "Dal", "Rice",
"Cucumber salad" and then as one food, "Dal, rice and cucumber salad". A match isn't
saved: it waits on the repeat card. An account's entries are read from its logs; a
guest's are the ones the browser sent (the last 7 days, at most 50), which only the
guest could change, and only for their own card. Entries staged earlier in the same
answer count too: one activity logged twice in one turn.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from app.agents.display import NAMES
from app.agents.schemas import ImportLog, RepeatOf, StagedWrite, WriteKind
from app.agents.tools import RepeatHook, ToolContext
from app.agents.tools.write import summarise
from app.config.limits import REPEAT_WINDOW
from app.data.repositories import (
    MentalLogRepository,
    NutritionLogRepository,
    WorkoutLogRepository,
)
from app.guardrails.normalise import WORD_CHAR, fold_for_matching
from app.guardrails.types import OTHER_ACTIVITY

log = logging.getLogger(__name__)

_REPOS = {"workout": WorkoutLogRepository, "meal": NutritionLogRepository,
          "practice": MentalLogRepository}
WORD = re.compile(f"{WORD_CHAR}+")


@dataclass(frozen=True)
class Logged:
    """An entry as the match reads it: `key` is the meal slot or the catalogue ID (and an
    other activity's name), `foods` the words of each of a meal's foods."""

    kind: WriteKind
    key: str
    foods: frozenset[frozenset[str]]
    at: datetime
    summary: str
    log_id: str | None = None
    this_turn: bool = False


def same_entry(new: Logged, old: Logged, tz: ZoneInfo) -> bool:
    if new.kind != old.kind or new.key != old.key:
        return False
    if new.kind == "meal":
        return (new.at.astimezone(tz).date() == old.at.astimezone(tz).date()
                and any(a <= b or b <= a for a in new.foods for b in old.foods))
    return abs(new.at - old.at) <= REPEAT_WINDOW


def entry_of(write: StagedWrite, at: datetime, log_id: str | None = None,
             this_turn: bool = False) -> Logged:
    args = write.args
    if write.kind == "meal":
        names = [f.name for f in args.foods]
        return Logged(write.kind, args.meal, _food_words(names), at,
                      _meal_summary(args.meal, names), log_id, this_turn)
    key = _activity_key(args.catalogue_id, getattr(args, "activity", None))
    return Logged(write.kind, key, frozenset(), at, summarise(write.kind, args)[:300], log_id,
                  this_turn)


def _food_words(names: list[str]) -> frozenset[frozenset[str]]:
    """Each food's words, folded as the gate folds them ("Dal-Chawal" is dal, chawal)."""
    words = (frozenset(WORD.findall(fold_for_matching(n))) for n in names)
    return frozenset(w for w in words if w)


def _meal_summary(meal: str, names: list[str]) -> str:
    """"Lunch: Dal, Rice": the card names the earlier meal by its foods, without amounts,
    whether it came from a log row or the browser."""
    return f"{meal.capitalize()}: {', '.join(names)}"[:300]


def _activity_key(catalogue_id: str, name: str | None) -> str:
    """Archery and a dance class are both other_activity: their names tell them apart."""
    if catalogue_id == OTHER_ACTIVITY:
        return f"{catalogue_id}:{fold_for_matching(name or '')}"
    return catalogue_id


def guest_logs(raw: list[dict[str, Any]] | None) -> list[ImportLog]:
    """The entries a guest's browser sent, each read on its own: one the schema no
    longer reads is skipped, not fatal to the message."""
    out = []
    for entry in raw or []:
        try:
            out.append(ImportLog.model_validate(entry))
        except ValidationError:
            continue
    return out


def repeat_finder(guest: list[ImportLog] | None = None) -> RepeatHook:
    """The check for one message: a guest's entries from the browser, else the account's
    logs. An entry already logged comes first, since only that one can be replaced."""

    async def find_repeat(write: StagedWrite, ctx: ToolContext) -> RepeatOf | None:
        new = entry_of(write, write.at or ctx.said or datetime.now(UTC))
        earlier = ([entry_of(g.entry, g.at, g.id) for g in guest if g.entry.kind == write.kind]
                   if guest is not None else await _account_entries(new, ctx))
        for old in [*earlier, *_this_turn(ctx)]:
            if same_entry(new, old, ctx.tz):
                return RepeatOf(summary=old.summary, at=old.at, log_id=old.log_id,
                                this_turn=old.this_turn)
        return None

    return find_repeat


def _this_turn(ctx: ToolContext) -> list[Logged]:
    contexts = ctx.turn.contexts if ctx.turn is not None else [ctx]
    return [entry_of(w, w.at or ctx.said or datetime.now(UTC), this_turn=True)
            for c in contexts for w in c.staged_writes]


async def _account_entries(new: Logged, ctx: ToolContext) -> list[Logged]:
    """The account's entries that could match: the meal's day, or 2 hours either side.
    If the database can't answer, nothing matches: the entry saves as before, and the
    turn's own commit will meet the same outage."""
    if ctx.mode == "guest" or ctx.sessions is None or ctx.user_id is None:
        return []
    if new.kind == "meal":
        day = new.at.astimezone(ctx.tz).date()
        start = datetime.combine(day, time(), ctx.tz)
        end = start + timedelta(days=1)
    else:
        start, end = new.at - REPEAT_WINDOW, new.at + REPEAT_WINDOW
    try:
        async with ctx.sessions() as session:
            rows = await _REPOS[new.kind](session, ctx.user_id).between(start, end)
    except (OperationalError, InterfaceError, PoolTimeout):
        log.warning("repeat check unavailable: trace=%s", ctx.trace_id)
        return []
    return [e for e in (_row_entry(new.kind, r) for r in rows) if e is not None]


def _row_entry(kind: WriteKind, row: Any) -> Logged | None:
    """A log row as the match reads it. Rows from before the rebuild may not read: they
    match nothing."""
    log_id = str(row.id)
    if kind == "meal":
        names = [f.get("name") for f in _json_list(row.foods) if isinstance(f, dict)]
        names = [n for n in names if isinstance(n, str) and n]
        if not row.meal_type or not names:
            return None
        return Logged(kind, row.meal_type, _food_words(names), row.meal_date,
                      _meal_summary(row.meal_type, names), log_id)
    if kind == "workout":
        if not row.exercise_type:
            return None
        first = next((e for e in _json_list(row.exercises) if isinstance(e, dict)), {})
        name = first.get("name") or NAMES.get(row.exercise_type, row.exercise_type)
        return Logged(kind, _activity_key(row.exercise_type, name), frozenset(),
                      row.workout_date, str(name)[:300], log_id)
    if not row.activity_type:
        return None
    name = NAMES.get(row.activity_type, row.activity_type)
    minutes = f": {round(row.duration_minutes)} min" if row.duration_minutes else ""
    return Logged(kind, row.activity_type, frozenset(), row.activity_date,
                  f"{name}{minutes}"[:300], log_id)


def _json_list(text: str | None) -> list:
    try:
        value = json.loads(text or "[]")
    except ValueError:
        return []
    return value if isinstance(value, list) else []
