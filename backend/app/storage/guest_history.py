"""A guest's history, tamper-evident (Plan C.8, C.18; owner, 15 Nov 2026, Part E #63).

    turn = signed(said, turn, shown, prev)      # at a guest's `done`
    kept, chain = verified(history)             # a chat request's guest_history
    kept, refused = verified_import(history)    # an import's history

The browser keeps a guest's conversation, so the server signs each exchange as it ends:
HMAC-SHA256, with a key derived from SESSION_SECRET, over the person's message as the
server took it, the answer (text, coaches, times), a digest of what the answer showed,
and `prev`, the signature of the exchange before. The chain makes a change, a removed
exchange or a new order show. The server accepts the unbroken signed run that ends at
the newest exchange and refuses everything older than its first break: an edit can
always be seen, and nothing edited is used. Card states (logged, "Don't log") are the
guest's own decisions after the fact, so they are outside the digest.

The key isn't bound to a session (a guest comes back after theirs ended), so a
genuine history can be copied between guests; changing SESSION_SECRET refuses every
guest history kept so far.
"""

import hashlib
import hmac
import json
from functools import lru_cache
from typing import Any

from app.agents.schemas import DISPLAY, HistoryTurn
from app.config.settings import get_settings

LABEL = b"holos guest history v1"


@lru_cache(maxsize=1)
def _key() -> bytes:
    return hmac.new(get_settings().session_secret, LABEL, hashlib.sha256).digest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode()


def shown_digest(shown: list[dict] | None) -> str:
    """What an answer showed, as the stream's models read it, card states left out."""
    events = []
    for event in DISPLAY.validate_python(shown or []):
        dumped = _unset_dropped(event.model_dump(mode="json"))
        if dumped["event"] == "pending_write":
            dumped["data"].pop("state", None)
        events.append(dumped)
    return hashlib.sha256(_canonical(events)).hexdigest()


# Fields added after answers were signed: unset, they are left out, so the digests of
# answers signed before them don't change (Part E #67)
ADDED = {"repeat_of"}


def _unset_dropped(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _unset_dropped(v) for k, v in value.items()
                if not (k in ADDED and v is None)}
    if isinstance(value, list):
        return [_unset_dropped(v) for v in value]
    return value


def _sig(said: HistoryTurn, reply: HistoryTurn, shown: str, prev: str | None) -> str:
    body = {"prev": prev, "shown": shown,
            "said": said.model_dump(mode="json", include={"content", "ts"}),
            "reply": reply.model_dump(mode="json", include={"content", "agents", "ts"})}
    return hmac.new(_key(), _canonical(body), hashlib.sha256).hexdigest()


def signed(said: HistoryTurn, reply: HistoryTurn, shown: list[dict],
           prev: str | None) -> HistoryTurn:
    """The answer as the browser keeps it: signed with the message before it."""
    digest = shown_digest(shown)
    return reply.model_copy(update={"sig": _sig(said, reply, digest, prev), "prev": prev,
                                    "shown": digest})


def _pairs(history: list[HistoryTurn]) -> list[tuple[int, HistoryTurn, HistoryTurn]]:
    """(index of the message, message, answer), newest first; a turn out of place ends
    the run."""
    pairs = []
    i = len(history) - 2
    while i >= 0 and history[i].role == "user" and history[i + 1].role == "assistant":
        pairs.append((i, history[i], history[i + 1]))
        i -= 2
    return pairs


def _run(history: list, digest_of) -> tuple[int, str | None]:
    """Where the unbroken signed run ending at the newest exchange starts, and the
    newest signature (the chain the next exchange extends)."""
    start, newest, expected = len(history), None, None
    for i, said, reply in _pairs(history):
        if reply.sig is None or (expected is not None and reply.sig != expected):
            break
        if not hmac.compare_digest(reply.sig, _sig(said, reply, digest_of(reply), reply.prev)):
            break
        start, newest = i, newest or reply.sig
        expected = reply.prev
    return start, newest


def verified(history: list[HistoryTurn]) -> tuple[list[HistoryTurn], str | None]:
    """A chat request's guest_history: what checks out, and the chain to extend."""
    start, chain = _run(history, lambda reply: reply.shown or "")
    return list(history[start:]), chain


def verified_import(history: list) -> tuple[int, list[int]]:
    """An import's turns: where the accepted run starts, and the refused indexes. An
    answer's display, when it came, must match its signed digest."""
    def digest(reply) -> str:
        return shown_digest(reply.display) if reply.display is not None else reply.shown or ""

    start, _ = _run(history, digest)
    return start, list(range(start))
