"""How a plan item reads as text, in one place: the stream's `display` (C.5), the
conversation history (C.8) and a staged write's summary (C.17).

    item_display(item)        # "Plank: 3 x 30 s", "Dal (1 bowl, about 300 kcal)"
    history_text(reply)       # summary, numbered items with their days, notes
"""

from pydantic import BaseModel

from app.agents.schemas import FoodItem, PracticeItem
from app.config.limits import HISTORY_TURN_CHARS
from app.guardrails.loader import get_guardrails
from app.providers.base import trim

NAMES = {i.id: i.name for i in [*get_guardrails().catalogue.exercises,
                                *get_guardrails().catalogue.practices]}


def duration(seconds: int, sets: int | None = None) -> str:
    """"30 s", "2 x 45 s", "20 min": seconds under a minute were shown as "0.2 min"."""
    one = f"{seconds} s" if seconds < 60 else f"{round(seconds / 60, 1):g} min"
    return f"{sets} x {one}" if sets and sets > 1 else one


def item_name(item: BaseModel) -> str:
    """An exercise or practice by its catalogue name; another activity by the person's
    words (Part E #53)."""
    return getattr(item, "activity", None) or NAMES[item.catalogue_id]


def item_display(item: BaseModel) -> str:
    """An item or a write's arguments: exercises and practices by catalogue name."""
    if isinstance(item, FoodItem):
        kcal = f", about {round(item.calories)} kcal" if item.calories else ""
        return f"{item.name} ({item.portion}{kcal})"
    name = item_name(item)
    if isinstance(item, PracticeItem) or hasattr(item, "duration_min"):
        return f"{name}: {item.duration_min} min"
    if item.sets and item.reps:
        return f"{name}: {item.sets} x {item.reps}"
    return f"{name}: {duration(item.duration_s, item.sets)}" if item.duration_s else name


def history_text(reply: BaseModel, limit: int = HISTORY_TURN_CHARS) -> str:
    """A gated reply as conversation history: the summary, then each item, then the
    notes, so a follow-up ("change Wednesday", "make the second one easier") can see the
    plan, not only its summary."""
    lines = [reply.summary] if reply.summary else []
    for n, item in enumerate(reply.items, 1):
        day = f"{item.day}: " if item.day else ""
        lines.append(f"{n}. {day}{item_display(item)}")
    lines += [f"- {note}" for note in reply.notes]
    return keep_lines(lines, limit)


def keep_lines(lines: list[str], limit: int) -> str:
    """Whole lines only, so no item is cut in half; a first line over the limit is
    trimmed."""
    kept: list[str] = []
    for line in lines:
        if len("\n".join([*kept, line])) > limit:
            break
        kept.append(line)
    return "\n".join(kept) if kept else trim(lines[0], limit) if lines else ""
