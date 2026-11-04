"""Health phrases that resolve to nothing, counted for the owner's catalogue review
(Plan P4.10, Part E #42 H; P6.2 turns the common ones into aliases).

    count_saved(db, "conditions", old_text, new_text)          # a profile save (sync)
    rows = top_terms(conn)                                     # phrases from >= 3 people
    purge(conn)                                                # older than 90 days

Counted when a phrase first appears in a saved profile, never when a profile is read:
an account's text is read on every chat turn, so reads would count one person many
times. So each person adds 1 per phrase, and a count of 3 is about 3 people (owner,
3 Nov 2026, Part E #47). Rows hold the folded phrase, its field and the day; no user,
session or trace ID. Phrases over 40 characters aren't stored at all.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.storage.profile import unresolved_phrases

FIELDS = ("conditions", "limitations", "dietary_restrictions")
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


TOP = text(
    "SELECT term, field, sum(count) AS people FROM unresolved_terms "
    "WHERE day > current_date - :keep GROUP BY term, field HAVING sum(count) >= :min "
    "ORDER BY people DESC, term LIMIT :n")
PURGE = text("DELETE FROM unresolved_terms WHERE day <= current_date - :keep")
