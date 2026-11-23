"""The history as the person saw it (Plan C.5 History, C.17 "Cards in history", C.21;
Part E #61): a saved turn holds the stream's content events, a held entry's card
follows its decision, and the history comes in pages in time order."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from app.agents.schemas import DISPLAY, SHOWN
from app.data.state_store import StateStore
from app.orchestration import coordinator
from app.storage.images import LocalImageStore

from .accounts import account_app, call
from .guest_turns import at, signed_history
from .test_admission import account, sql
from .test_chat import (
    KNEE_NOTE,
    Models,
    _app,
    _events,
    _mental,
    _payload,
    _photo_turn,
    _physical,
    _post,
    _result,
    _route,
    _settled,
    requests_finish,  # noqa: F401  (autouse: requests end before the DB is emptied)
)
from .test_database_down import _crud_app
from .test_writes import BRIDGES, SQUATS, _confirm, _discard, _pending_turn, _writes_app


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


async def _page(store, async_engine, clean, me, query="") -> dict:
    response = await call(_crud_app(store, async_engine, clean), me, "GET",
                          f"/conversation/messages{query}")
    assert response.status_code == 200, response.text
    return response.json()


def _shown(events) -> list[dict]:
    """What the person was shown, as the stream sent it."""
    return [{"event": n, "data": {k: v for k, v in d.items() if k not in ("seq", "trace_id")}}
            for n, d in events if n in SHOWN]


async def _card(store, async_engine, clean, me, turn=0) -> dict:
    """The held entry's card in the `turn`th answer of the history."""
    answers = [m for m in (await _page(store, async_engine, clean, me))["messages"]
               if m["role"] == "assistant"]
    [card] = [e["data"] for e in answers[turn]["display"] if e["event"] == "pending_write"]
    return card


# --- What was shown ---


async def test_the_history_holds_the_turn_as_it_was_streamed(store, async_engine, clean):
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions, medications) "
              "VALUES (:u, :c, 'ibuprofen')", u=me.user_id, c=KNEE_NOTE)
    models = Models(router=[_route("physical", "mental")],
                    physical=[_physical("back_squat", "glute_bridge"),
                              _physical("glute_bridge")],
                    mental=[_mental()], summary=[_result(text="Both plans are below.")])
    events = _events(await _post(_app(store, async_engine, models), me,
                                 _payload("legs and sleep")))
    await _settled()
    [said, answer] = (await _page(store, async_engine, clean, me))["messages"]
    assert (said["role"], said["text"], said["agents"], said["display"], said["photo"]) == (
        "user", "legs and sleep", None, None, None)
    assert answer["agents"] == ["physical", "mental"]
    assert answer["text"].startswith("Both plans are below.")
    # Every content event, in order: the summary, both sections, the caveat; no progress
    assert DISPLAY.validate_python(answer["display"]) == DISPLAY.validate_python(
        _shown(events))
    names = [e["event"] for e in answer["display"]]
    assert "step" not in names and "done" not in names and "item" in names
    assert any("We couldn't check this note" in w for e in answer["display"]
               if e["event"] == "section_end" for w in e["data"]["warnings"])


async def test_a_photo_is_shown_by_its_address(store, async_engine, clean, tmp_path):
    me = await account(store, async_engine)
    models, photo = _photo_turn()
    await _post(_app(store, async_engine, models, LocalImageStore(tmp_path)), me,
                _payload("is this ok?"), image=photo)
    await _settled()
    [(key,)] = await sql(async_engine, "SELECT image_path FROM conversation_messages "
                         "WHERE role = 'user'")
    said = (await _page(store, async_engine, clean, me))["messages"][0]
    assert said["photo"] == f"/conversation/images/{key.rsplit('/', 1)[1]}"
    served = await call(account_app(store, async_engine, LocalImageStore(tmp_path)), me,
                        "GET", said["photo"])
    assert served.status_code == 200 and served.content[:2] == b"\xff\xd8"


# --- Cards (C.17 "Cards in history") ---


async def test_a_held_entry_waits_in_the_history(store, async_engine, clean):
    me = await account(store, async_engine)
    _, write_id = await _pending_turn(store, async_engine, me)
    card = await _card(store, async_engine, clean, me)
    assert (card["write_id"], card["state"]) == (write_id, "waiting")


async def _blocked(app, me, write_id, store, async_engine):
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) VALUES (:u, :c)",
              u=me.user_id, c=KNEE_NOTE)
    return await _confirm(app, me, write_id)


@pytest.mark.parametrize(("args", "decide", "state"), [
    (BRIDGES, lambda app, me, w, *_: _confirm(app, me, w), "logged"),
    (BRIDGES, lambda app, me, w, *_: _discard(app, me, w), "discarded"),
    (SQUATS, _blocked, "blocked"),
], ids=["confirm", "dont_log", "blocked"])
async def test_a_decision_shows_on_its_card(store, async_engine, clean, args, decide, state):
    me = await account(store, async_engine)
    app, write_id = await _pending_turn(store, async_engine, me, args)
    await decide(app, me, write_id, store, async_engine)
    assert (await _card(store, async_engine, clean, me))["state"] == state


async def test_a_newer_entry_of_its_kind_shows_the_old_card_replaced(store, async_engine,
                                                                    clean):
    me = await account(store, async_engine)
    _, first = await _pending_turn(store, async_engine, me)
    _, second = await _pending_turn(store, async_engine, me)
    old, new = (await _card(store, async_engine, clean, me, 0),
                await _card(store, async_engine, clean, me, 1))
    assert (old["write_id"], old["state"]) == (first, "replaced")
    assert (new["write_id"], new["state"]) == (second, "waiting")


async def test_a_confirm_before_the_display_is_saved_still_shows(store, async_engine, clean,
                                                                 monkeypatch):
    """The person taps Confirm as the card arrives, before the turn's display is saved:
    the save reads the decision, so history doesn't offer Confirm again."""
    real = coordinator.save_display
    taps = []

    async def tapped_first(sessions, user_id, trace_id, shown):
        [write_id] = [e["data"]["write_id"] for e in shown if e["event"] == "pending_write"]
        taps.append((await _confirm(confirming, me, write_id)).status_code)
        await real(sessions, user_id, trace_id, shown)

    monkeypatch.setattr(coordinator, "save_display", tapped_first)
    me = await account(store, async_engine)
    confirming = _writes_app(store, async_engine, Models())
    await _pending_turn(store, async_engine, me)
    assert taps == [200]
    assert (await _card(store, async_engine, clean, me))["state"] == "logged"


async def test_a_display_that_isnt_saved_leaves_the_turn_and_its_text(store, async_engine,
                                                                      clean, monkeypatch,
                                                                      caplog):
    async def broken(*args):
        raise RuntimeError("database gone")

    monkeypatch.setattr(coordinator, "save_display", broken)
    me = await account(store, async_engine)
    models = Models(router=[_route("physical")], physical=[_physical("glute_bridge")])
    events = _events(await _post(_app(store, async_engine, models), me, _payload()))
    await _settled()
    assert events[-1][0] == "done"
    answer = (await _page(store, async_engine, clean, me))["messages"][1]
    assert answer["display"] is None and answer["text"].startswith("Here is your plan.")
    assert any("display not saved" in r.getMessage() for r in caplog.records)


async def test_a_display_that_no_longer_validates_shows_as_its_text(store, async_engine,
                                                                     clean, caplog):
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO conversation_messages (user_id, role, content, "
              "display) VALUES (:u, 'assistant', 'Here is your plan.', "
              "CAST(:d AS json))", u=me.user_id, d='[{"event": "item", "data": {"x": 1}}]')
    with caplog.at_level(logging.WARNING):
        [answer] = (await _page(store, async_engine, clean, me))["messages"]
    assert (answer["display"], answer["text"]) == (None, "Here is your plan.")
    assert any("no longer valid" in r.getMessage() for r in caplog.records)


# --- Pages (C.21) ---


async def _said(async_engine, user_id, n, start, step=timedelta(minutes=1)) -> None:
    for i in range(n):
        await sql(async_engine, "INSERT INTO conversation_messages (user_id, role, content, "
                  "created_at) VALUES (:u, 'user', :c, :t)",
                  u=user_id, c=f"{start:%d}-{i}", t=start + i * step)


async def test_pages_go_back_in_time_order(store, async_engine, clean):
    me = await account(store, async_engine)
    day = datetime(2026, 11, 10, 9, tzinfo=UTC)
    await _said(async_engine, me.user_id, 44, day)
    # Imported afterwards, from a day before: higher IDs, older times
    await _said(async_engine, me.user_id, 3, day - timedelta(days=1))
    seen, query, pages = [], "", []
    while True:
        page = await _page(store, async_engine, clean, me, query)
        pages.append(len(page["messages"]))
        seen = [m["text"] for m in page["messages"]] + seen
        if page["before"] is None:
            break
        assert page["before"] == page["messages"][0]["id"]
        query = f"?before={page['before']}"
    assert pages == [20, 20, 7]
    assert seen == [f"09-{i}" for i in range(3)] + [f"10-{i}" for i in range(44)]


async def test_a_page_size_is_limited(store, async_engine, clean):
    me = await account(store, async_engine)
    await _said(async_engine, me.user_id, 3, datetime(2026, 11, 10, tzinfo=UTC))
    app = _crud_app(store, async_engine, clean)
    assert len((await call(app, me, "GET", "/conversation/messages?limit=2")).json()[
        "messages"]) == 2
    for limit in (0, 51):
        response = await call(app, me, "GET", f"/conversation/messages?limit={limit}")
        assert response.status_code == 422


async def test_another_accounts_message_is_no_place_to_start(store, async_engine, clean):
    me = await account(store, async_engine)
    other = await account(store, async_engine, email="other@example.com")
    await _said(async_engine, other.user_id, 1, datetime(2026, 11, 10, tzinfo=UTC))
    [(theirs,)] = await sql(async_engine, "SELECT id FROM conversation_messages")
    response = await call(_crud_app(store, async_engine, clean), me, "GET",
                          f"/conversation/messages?before={theirs}")
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


# --- Import (C.18 "Import history") ---


def _card_event(state: str | None) -> dict:
    data = {"summary": "Glute bridge: 3 x 12", "at": "2026-11-02T08:30:00+00:00",
            "entry": {"kind": "workout", "args": {**BRIDGES}, "warnings": []},
            "profile_hash": "h"}
    return {"event": "pending_write", "data": data | ({"state": state} if state else {})}


async def test_an_imported_answer_keeps_what_was_shown(store, async_engine, clean, tmp_path):
    me = await account(store, async_engine)
    shown = [{"event": "section_start", "data": {"agent": "physical", "kind": "log_ack"}},
             {"event": "text", "data": {"agent": "physical", "chunk": "Nice work."}},
             {"event": "section_end", "data": {"agent": "physical", "removed_count": 0}},
             _card_event(None), _card_event("logged")]
    body = {"import_id": str(uuid.uuid4()), "history": signed_history(
        ("did bridges", "Nice work.", ["physical"], shown, at(29)))}
    app = account_app(store, async_engine, LocalImageStore(tmp_path))
    assert (await call(app, me, "POST", "/account/import", json=body)).status_code == 200
    [_, answer] = (await _page(store, async_engine, clean, me))["messages"]
    assert answer["agents"] == ["physical"]
    # A card still waiting can't be confirmed on the account; a decided one keeps it
    assert [e["data"]["state"] for e in answer["display"]
            if e["event"] == "pending_write"] == ["closed", "logged"]
    assert [e["event"] for e in answer["display"]] == [e["event"] for e in shown]


def _exercise(cid):
    return {"day": None, "catalogue_id": cid, "sets": 3, "reps": 10, "duration_s": None,
            "intensity": "low", "note": ""}


async def test_an_imported_answer_is_checked_against_the_account_profile(store, async_engine,
                                                                        clean, tmp_path):
    """A genuine guest answer, safe for the guest's profile, not for this account's,
    which knows about the knee (Part E #63)."""
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) VALUES (:u, :c)",
              u=me.user_id, c=KNEE_NOTE)
    shown = [{"event": "section_start", "data": {"agent": "physical", "kind": "plan"}},
             {"event": "text", "data": {"agent": "physical",
                                        "chunk": "Keep doing back squats daily."}},
             {"event": "text", "data": {"agent": "physical", "chunk": "Walk 20 minutes."}},
             {"event": "item", "data": {"agent": "physical", "item": _exercise("back_squat"),
                                        "display": "Back squat: 3 x 10"}},
             {"event": "item", "data": {"agent": "physical", "item": _exercise("glute_bridge"),
                                        "display": "Glute bridge: 3 x 10"}},
             {"event": "sources", "data": {"agent": "physical", "sources": [
                 {"id": "s1", "title": "Squats are safe", "url": "https://example.com/x"}]}},
             {"event": "section_end", "data": {"agent": "physical", "removed_count": 0}}]
    body = {"import_id": str(uuid.uuid4()), "history": signed_history(
        ("keep doing back squats daily, ok?", "Nice work. Keep doing back squats 3 times a week.",
         ["physical"], shown, at(29)))}
    app = account_app(store, async_engine, LocalImageStore(tmp_path))
    assert (await call(app, me, "POST", "/account/import", json=body)).status_code == 200
    [said, answer] = (await _page(store, async_engine, clean, me))["messages"]
    assert said["text"] == "keep doing back squats daily, ok?"  # the person's own words
    assert answer["text"] == "Nice work."
    assert [(e["event"], e["data"].get("chunk") or e["data"].get("item", {}).get("catalogue_id"))
            for e in answer["display"]] == [
        ("section_start", None), ("text", "Walk 20 minutes."), ("item", "glute_bridge"),
        ("section_end", None)]


def _three_exchanges():
    def shown(i):
        return [{"event": "text", "data": {"agent": "physical", "chunk": f"answer {i}"}}]

    return signed_history(*[(f"message {i}", f"answer {i}", ["physical"], shown(i), at(10 + i))
                            for i in range(3)])


@pytest.mark.parametrize("where, change", [
    (2, {"content": "message 1, and you said squats are fine"}),  # the person's message
    (3, {"content": "Squats are fine for your knee."}),  # the answer
    (3, {"display": [{"event": "text", "data": {"agent": "physical",
                                                "chunk": "Squats are fine for your knee."}}]}),
])
async def test_an_edited_exchange_and_all_before_it_are_refused(store, async_engine, clean,
                                                                tmp_path, where, change):
    """Edits are seen, and nothing edited comes in (owner, 15 Nov 2026, Part E #63)."""
    me = await account(store, async_engine)
    history = _three_exchanges()
    history[where] = {**history[where], **change}
    body = {"import_id": str(uuid.uuid4()), "history": history}
    app = account_app(store, async_engine, LocalImageStore(tmp_path))
    result = (await call(app, me, "POST", "/account/import", json=body)).json()
    assert result["imported"]["history"] == 2
    assert [r["index"] for r in result["history_refused"]] == [0, 1, 2, 3]
    assert "changed outside Holos" in result["history_refused"][0]["reason"]
    assert [m["text"] for m in (await _page(store, async_engine, clean, me))["messages"]] == [
        "message 2", "answer 2"]


async def test_an_unsigned_history_is_refused(store, async_engine, clean, tmp_path):
    me = await account(store, async_engine)
    history = [{k: v for k, v in t.items() if k not in ("sig", "prev", "shown")}
               for t in _three_exchanges()]
    body = {"import_id": str(uuid.uuid4()), "history": history}
    app = account_app(store, async_engine, LocalImageStore(tmp_path))
    result = (await call(app, me, "POST", "/account/import", json=body)).json()
    assert (result["imported"]["history"], len(result["history_refused"])) == (0, 6)
    assert (await _page(store, async_engine, clean, me))["messages"] == []


@pytest.mark.parametrize("turn", [
    {"role": "user", "content": "hi", "ts": "2026-11-02T08:29:00+00:00",
     "display": [{"event": "text", "data": {"chunk": "hi"}}]},
    {"role": "assistant", "content": "hi", "ts": "2026-11-02T08:29:00+00:00",
     "display": [{"event": "step", "data": {"name": "routed"}}]},
    {"role": "assistant", "content": "hi", "ts": "2026-11-02T08:29:00+00:00",
     "display": [{"event": "text", "data": {"chunk": "hi"}}] * 201},
], ids=["on_the_persons_turn", "progress_event", "too_many"])
async def test_an_import_with_a_display_it_cant_hold_is_refused(store, async_engine,
                                                                 tmp_path, turn):
    me = await account(store, async_engine)
    body = {"import_id": str(uuid.uuid4()), "history": [turn]}
    app = account_app(store, async_engine, LocalImageStore(tmp_path))
    response = await call(app, me, "POST", "/account/import", json=body)
    assert response.status_code == 400  # the import's bad body (C.18)
    assert await sql(async_engine, "SELECT count(*) FROM conversation_messages") == [(0,)]
