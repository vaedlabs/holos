"""A guest's history as the browser keeps it: each exchange signed by the server, in a
chain (Part E #63)."""

from datetime import UTC, datetime, timedelta

from app.agents.schemas import HistoryTurn
from app.storage.guest_history import signed


def signed_history(*exchanges: tuple) -> list[dict]:
    """(message, answer, agents, display or None, when) per exchange, oldest first, as
    JSON; an answer with a display carries it, as the import sends it."""
    turns, prev = [], None
    for message, answer, agents, display, at in exchanges:
        said = HistoryTurn(role="user", content=message, ts=at)
        reply = signed(said, HistoryTurn(role="assistant", content=answer, agents=agents,
                                         ts=at + timedelta(seconds=5)), display or [], prev)
        prev = reply.sig
        turns.append(said.model_dump(mode="json", exclude_none=True))
        turns.append({**reply.model_dump(mode="json", exclude_none=True),
                      **({"display": display} if display is not None else {})})
    return turns


def at(minute: int) -> datetime:
    """A guest's turn time: 2 Nov 2026, 8:mm UTC."""
    return datetime(2026, 11, 2, 8, minute, tzinfo=UTC)
