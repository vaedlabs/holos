"""The reconnect endpoint (Plan C.5, Part E #34) and the stream writer, on a real
Postgres: the phone gets what it missed after its last `seq`, only for its own
request; a request whose worker is gone ends as `interrupted`; a database that can't
save still lets the live stream through."""

import asyncio
import json
import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text

from app.config.settings import get_settings
from app.data.state_store import StateStore
from app.data.stream_store import DEAD_AFTER_S, RequestEnded, StreamStore
from app.dependencies import get_state_store, get_stream_store
from app.orchestration.composer import Composer, Gated
from app.orchestration.stream import (
    HEADERS,
    LiveSink,
    SavedSink,
    format_event,
    with_pings,
)
from app.routers import chat
from app.routers.errors import ApiError, api_error_handler

from .test_admission import guest, settings

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


@pytest_asyncio.fixture
async def streams(async_engine):
    return StreamStore(async_engine)


def _app(store, streams) -> FastAPI:
    cfg = settings()
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(chat.router)
    app.dependency_overrides.update({get_settings: lambda: cfg, get_state_store: lambda: store,
                                     get_stream_store: lambda: streams})
    return app


async def _request(store, streams, principal, events: int, final: bool) -> uuid.UUID:
    """A request with `events` saved events, sent by a real Composer."""
    rid = uuid.uuid4()
    await store.claim_request(principal.principal_key, rid, None, "tr_1")
    await streams.start("tr_1", "worker-a")
    c = Composer("tr_1", "guest", SavedSink(streams, "tr_1", LiveSink()))
    await c.accepted(1)
    for _ in range(events - 1 - final):
        await c.step("composing")
    if final:
        await c.error("busy")
    return rid


async def _get(app, principal, path: str, **headers) -> httpx.Response:
    cfg = settings()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://testserver") as client:
        return await client.get(path, headers=headers,
                                cookies={cfg.session_cookie: principal.raw_session_id})


def _seqs(body: str) -> list[int]:
    return [int(line[4:]) for line in body.splitlines() if line.startswith("id: ")]


async def test_a_reconnect_gets_the_events_after_its_last_seq(store, streams):
    me = await guest(store)
    rid = await _request(store, streams, me, 5, final=True)
    response = await _get(_app(store, streams), me, f"/agents/chat/stream/{rid}?after=2")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == HEADERS["Cache-Control"]
    assert response.headers["x-accel-buffering"] == "no"
    assert _seqs(response.text) == [3, 4]
    assert "event: error" in response.text
    # Last-Event-ID, as a browser's EventSource sends it, counts too
    response = await _get(_app(store, streams), me, f"/agents/chat/stream/{rid}",
                          **{"last-event-id": "3"})
    assert _seqs(response.text) == [4]


async def test_someone_elses_request_is_404(store, streams):
    me, other = await guest(store), await guest(store, "ipk-b")
    rid = await _request(store, streams, me, 2, final=True)
    response = await _get(_app(store, streams), other, f"/agents/chat/stream/{rid}")
    assert response.status_code == 404 and response.json()["code"] == "not_found"


async def test_no_session_is_401(store, streams):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(store, streams)),
                                 base_url="http://testserver") as client:
        response = await client.get(f"/agents/chat/stream/{uuid.uuid4()}")
    assert response.status_code == 401


async def test_a_request_whose_worker_died_ends_as_interrupted(store, streams, async_engine):
    me = await guest(store)
    rid = await _request(store, streams, me, 3, final=False)
    async with async_engine.begin() as conn:
        await conn.execute(text("UPDATE chat_requests SET heartbeat_at = now() - "
                                "make_interval(secs => :s)"), {"s": DEAD_AFTER_S + 1})
    response = await _get(_app(store, streams), me, f"/agents/chat/stream/{rid}?after=2")
    assert _seqs(response.text) == [3]
    assert '"code":"interrupted"' in response.text
    # Saved: the next reconnect sees the same end
    again = await _get(_app(store, streams), me, f"/agents/chat/stream/{rid}?after=-1")
    assert _seqs(again.text) == [0, 1, 2, 3]


async def test_expired_events_are_410(store, streams, async_engine):
    me = await guest(store)
    rid = await _request(store, streams, me, 2, final=True)
    async with async_engine.begin() as conn:
        await conn.execute(text("DELETE FROM stream_events"))
    response = await _get(_app(store, streams), me, f"/agents/chat/stream/{rid}")
    assert response.status_code == 410 and response.json()["code"] == "expired"


# --- The stream writer ---


async def test_an_unsaved_event_still_goes_out_live(store):
    class Down:
        async def append(self, *a, **k):
            raise ConnectionError("database down")

    live = LiveSink()
    sink = SavedSink(Down(), "tr_1", live)  # type: ignore[arg-type]
    c = Composer("tr_1", "guest", sink)
    await c.accepted(1)
    await c.error("busy")
    assert [e[1] async for e in live.events()] == ["accepted", "error"]
    assert sink.saving is False


async def test_a_worker_told_its_request_ended_stops(store, streams):
    rid = uuid.uuid4()
    await store.claim_request("session:x", rid, None, "tr_2")
    c = Composer("tr_2", "guest", SavedSink(streams, "tr_2", LiveSink()))
    await streams.append("tr_2", [(0, "error", {"seq": 0})], final=True)  # interrupted
    with pytest.raises(RequestEnded):
        await c.accepted(1)


async def test_pings_fill_the_silence_and_events_keep_their_ids():
    async def slow():
        yield (0, "accepted", {"seq": 0})
        await asyncio.sleep(0.05)
        yield (1, "done", {"seq": 1})

    chunks = [c async for c in with_pings(slow(), ping_s=0.02)]
    assert chunks[0] == format_event((0, "accepted", {"seq": 0}))
    assert b": ping\n\n" in chunks[1:-1]
    assert chunks[-1] == b'id: 1\nevent: done\ndata: {"seq":1}\n\n'


async def test_hindi_text_comes_back_unchanged_from_a_reconnect(store, streams):
    me = await guest(store)
    rid = uuid.uuid4()
    await store.claim_request(me.principal_key, rid, None, "tr_hi")
    c = Composer("tr_hi", "guest", SavedSink(streams, "tr_hi", LiveSink()))
    hindi = "आज शाम 20 मिनट टहलिए।\nरात को हल्का खाना 🙂"
    await c.accepted(1)
    await c.reply(Gated(hindi))
    await c.error("busy")
    response = await _get(_app(store, streams), me, f"/agents/chat/stream/{rid}?after=0")
    data = [line for line in response.text.splitlines() if line.startswith("data: ")]
    assert json.loads(data[0][6:])["chunk"] == hindi  # the newline stayed inside the JSON
    assert "आज शाम" in response.text  # sent as UTF-8, not \u escapes
