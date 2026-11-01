"""The SSE stream (Plan C.5) and resumable requests (Part E #34).

    live = LiveSink()                                  # this connection's queue
    composer = Composer(trace_id, mode, SavedSink(store, trace_id, live))
    return sse_response(live.events())                 # the first connection
    return sse_response(follow(store, trace_id, after))  # a reconnect

Every event is saved before it is sent (`SavedSink`), so a reconnect from any worker
replays what was missed and then follows the live ones from the database. If the
database can't save an event, the person still gets it live; the request is just no
longer resumable (logged). A crisis stream is sent without saving (C.16).
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from app.data.stream_store import Event, RequestEnded, StreamStore
from app.orchestration.composer import ERRORS

log = logging.getLogger(__name__)

PING_S = 15
POLL_S = 0.25
HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
_END = object()
INTERRUPTED = {"code": "interrupted", "message": ERRORS["interrupted"]}


def format_event(event: Event) -> bytes:
    seq, name, data = event
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {seq}\nevent: {name}\ndata: {body}\n\n".encode()


class LiveSink:
    """The connection's own queue: events in the order the composer sent them."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()

    async def emit(self, events: list[Event], final: bool) -> None:
        for event in events:
            self._queue.put_nowait(event)
        if final:
            self._queue.put_nowait(_END)

    async def events(self) -> AsyncIterator[Event]:
        while (event := await self._queue.get()) is not _END:
            yield event


class SavedSink:
    """Save, then send. A RequestEnded (someone ended the request as interrupted)
    reaches the worker, which must stop."""

    def __init__(self, store: StreamStore, trace_id: str, live: LiveSink):
        self._store, self._trace_id, self._live = store, trace_id, live
        self.saving = True

    async def emit(self, events: list[Event], final: bool) -> None:
        if self.saving:
            try:
                await self._store.append(self._trace_id, events, final=final)
            except RequestEnded:
                raise
            except Exception:
                self.saving = False
                log.exception("stream events not saved: trace=%s; not resumable",
                              self._trace_id)
        await self._live.emit(events, final)


async def follow(store: StreamStore, trace_id: str, after: int,
                 poll_s: float = POLL_S) -> AsyncIterator[Event]:
    """A reconnect: the saved events after `after`, then new ones as they are saved,
    until the terminal event. A request whose worker is gone ends as `interrupted`."""
    while True:
        events = await store.after(trace_id, after)
        for event in events:
            yield event
            after = event[0]
            if event[1] in ("done", "error"):
                return
        if not events:
            ended = await store.interrupt(trace_id, {"trace_id": trace_id, **INTERRUPTED})
            if ended is not None:
                yield ended
                return
            if await store.finished(trace_id):
                return  # its events have expired (10 minutes)
            await asyncio.sleep(poll_s)


async def with_pings(events: AsyncIterator[Event], ping_s: float = PING_S
                     ) -> AsyncIterator[bytes]:
    """The SSE body: each event, and `: ping` after `ping_s` without one."""
    source = aiter(events)
    next_event = asyncio.ensure_future(anext(source))
    try:
        while True:
            done, _ = await asyncio.wait({next_event}, timeout=ping_s)
            if not done:
                yield b": ping\n\n"
                continue
            try:
                event = next_event.result()
            except StopAsyncIteration:
                return
            yield format_event(event)
            next_event = asyncio.ensure_future(anext(source))
    finally:
        next_event.cancel()


def sse_response(events: AsyncIterator[Event]) -> StreamingResponse:
    return StreamingResponse(with_pings(events), media_type="text/event-stream",
                             headers=HEADERS)
