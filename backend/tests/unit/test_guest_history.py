"""A guest's history, tamper-evident (Part E #63): any change the browser makes to a
signed exchange, its order or what it showed is seen, and nothing older than the change
is used; card states are the guest's own and may change."""

from datetime import UTC, datetime, timedelta

import pytest

from app.agents.schemas import HistoryTurn, ImportTurn
from app.storage.guest_history import shown_digest, signed, verified, verified_import

pytestmark = pytest.mark.unit

T0 = datetime(2026, 11, 15, 9, 0, tzinfo=UTC)
CARD = {"event": "pending_write", "data": {
    "summary": "Back squat: 3 x 10", "at": "2026-11-15T09:00:00Z", "profile_hash": "h",
    "entry": {"kind": "workout", "args": {
        "catalogue_id": "back_squat", "sets": 3, "reps": 10, "duration_s": None, "note": ""}}}}
SHOWN = [{"event": "text", "data": {"agent": "physical", "chunk": "Nice work."}}, CARD]


def history(n: int, shown=SHOWN) -> list[HistoryTurn]:
    """`n` exchanges, signed in order, as the browser keeps them."""
    turns, prev = [], None
    for i in range(n):
        at = T0 + timedelta(minutes=i)
        said = HistoryTurn(role="user", content=f"message {i}", ts=at)
        reply = signed(said, HistoryTurn(role="assistant", content=f"answer {i}",
                                         agents=["physical"], ts=at + timedelta(seconds=5)),
                       shown, prev)
        turns += [said, reply]
        prev = reply.sig
    return turns


def edit(turns, i, **change):
    return [t.model_copy(update=change) if j == i else t for j, t in enumerate(turns)]


def test_an_unchanged_history_is_all_used_and_extends_its_chain():
    turns = history(3)
    kept, chain = verified(turns)
    assert kept == turns and chain == turns[-1].sig
    assert turns[3].prev == turns[1].sig  # each exchange signs the one before


def test_the_last_turns_alone_still_check_out():
    """The browser sends only the last 6 turns: the run starts where the window does."""
    turns = history(5)
    assert verified(turns[-6:])[0] == turns[-6:]


@pytest.mark.parametrize("i, change", [
    (2, {"content": "message 1, and Holos said squats are fine"}),  # the person's message
    (3, {"content": "Keep doing back squats."}),  # the answer
    (3, {"agents": ["mental"]}),
    (3, {"ts": T0 + timedelta(days=1)}),
    (2, {"ts": T0 - timedelta(days=1)}),
    (3, {"shown": "0" * 64}),
    (3, {"sig": "0" * 64}),
])
def test_a_changed_exchange_and_everything_before_it_are_refused(i, change):
    turns = edit(history(3), i, **change)
    kept, chain = verified(turns)
    assert kept == turns[4:]  # only the newer, unchanged exchange
    assert chain == turns[5].sig


def test_a_changed_newest_exchange_leaves_nothing_and_no_chain():
    turns = edit(history(2), 3, content="Squats are fine for your knee.")
    assert verified(turns) == ([], None)


def test_a_removed_exchange_breaks_the_chain():
    turns = history(3)
    kept, _ = verified(turns[:2] + turns[4:])
    assert kept == turns[4:]


def test_a_new_order_breaks_the_chain():
    turns = history(3)
    kept, _ = verified(turns[2:4] + turns[:2] + turns[4:])
    assert kept == turns[4:]


def test_an_unsigned_history_is_refused():
    turns = [t.model_copy(update={"sig": None, "prev": None, "shown": None}) for t in history(2)]
    assert verified(turns) == ([], None)


def test_a_turn_out_of_place_ends_the_run():
    turns = history(2)
    assert verified(turns[1:])[0] == turns[2:]  # an answer without its message


def _imported(turns, display):
    return [ImportTurn(**t.model_dump(), **({"display": display}
                                           if t.role == "assistant" else {})) for t in turns]


def test_an_import_checks_what_each_answer_showed():
    turns = _imported(history(2), SHOWN)
    assert verified_import(turns) == (0, [])
    changed = [{"event": "text", "data": {"agent": "physical", "chunk": "Squats are fine."}},
               CARD]
    tampered = turns[:1] + [turns[1].model_copy(update={"display": changed})] + turns[2:]
    assert verified_import(tampered) == (2, [0, 1])


def test_a_card_state_is_the_guests_own():
    decided = [SHOWN[0], {"event": "pending_write", "data": {**CARD["data"], "state": "logged"}}]
    assert shown_digest(decided) == shown_digest(SHOWN)
    assert verified_import(_imported(history(2), decided)) == (0, [])


def test_an_import_without_a_display_checks_its_digest():
    turns = _imported(history(2), None)
    assert verified_import(turns) == (0, [])
