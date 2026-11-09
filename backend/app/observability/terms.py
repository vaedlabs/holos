"""Health phrases that resolve to nothing, counted for the owner's catalogue review
(Plan P4.10, Part E #42 H; P6.2 turns the common ones into aliases), and activities
logged as "other activity" (Part E #53), which the job also flags to the developer.

    count_saved(db, "conditions", old_text, new_text)          # a profile save (sync)
    await count_activities(conn, ["Archery"])                  # a turn's other activities
    new = await new_activities(conn)                           # {"archery": 3}, once each
    rows = top_terms(conn)                                     # phrases from >= 3 people
    purge(conn)                                                # older than 90 days

Counted when a phrase first appears in a saved profile, never when a profile is read:
an account's text is read on every chat turn, so reads would count one person many
times. So each person adds 1 per phrase, and a count of 3 is about 3 people (owner,
3 Nov 2026, Part E #47). Rows hold the folded phrase, its field and the day; no user,
session or trace ID. Phrases over 40 characters aren't stored at all. An activity counts
each time it is logged, not once per person.
"""

from collections import Counter

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.orm import Session

from app.guardrails.normalise import fold_for_matching
from app.storage.profile import unresolved_phrases

FIELDS = ("conditions", "limitations", "dietary_restrictions")
ACTIVITY = "activity"
TERM_MAX = 40
MIN_PEOPLE = 3
KEEP_DAYS = 90

_UPSERT = text(
    "INSERT INTO unresolved_terms (term, field, day, count) VALUES (:t, :f, current_date, 1) "
    "ON CONFLICT (term, field, day) DO UPDATE SET count = unresolved_terms.count + 1")


def new_terms(old: str | None, new: str | None) -> list[str]:
    before = set(unresolved_phrases(old))
    return sorted({t for t in unresolved_phrases(new)
                   if t not in before and 0 < len(t) <= TERM_MAX})


def _rows(field: str, old: str | None, new: str | None) -> list[dict]:
    if field not in FIELDS:
        raise ValueError(f"not a counted field: {field}")
    return [{"t": t, "f": field} for t in new_terms(old, new)]


def count_saved(db: Session, field: str, old: str | None, new: str | None) -> None:
    if rows := _rows(field, old, new):
        db.execute(_UPSERT, rows)


async def count_activities(conn: AsyncConnection, names: list[str]) -> None:
    rows = [{"t": t, "f": ACTIVITY} for t in (fold_for_matching(n) for n in names)
            if 0 < len(t) <= TERM_MAX]
    if rows:
        await conn.execute(_UPSERT, rows)


# What is new since the last alert, marked as alerted in the same statement: the rows
# are locked, so a count added meanwhile waits and is flagged next time
_NEW_ACTIVITIES = text(
    "WITH new AS (SELECT term, field, day, count - alerted AS n FROM unresolved_terms "
    "WHERE field = :f AND count > alerted FOR UPDATE) "
    "UPDATE unresolved_terms u SET alerted = u.count FROM new WHERE u.term = new.term "
    "AND u.field = new.field AND u.day = new.day RETURNING new.term, new.n")


async def new_activities(conn: AsyncConnection) -> Counter[str]:
    """Each activity logged since the last call, with how many times (over its days)."""
    found: Counter[str] = Counter()
    for term, n in (await conn.execute(_NEW_ACTIVITIES, {"f": ACTIVITY})).all():
        found[term] += n
    return found


TOP = text(
    "SELECT term, field, sum(count) AS people FROM unresolved_terms "
    "WHERE day > current_date - :keep GROUP BY term, field HAVING sum(count) >= :min "
    "ORDER BY people DESC, term LIMIT :n")
PURGE = text("DELETE FROM unresolved_terms WHERE day <= current_date - :keep")
