"""Saved stream events, so a dropped connection can pick up where it left off (Plan C.5,
C.11, Part E #34).

    store = StreamStore(engine)
    await store.append(trace_id, [(seq, "item", data), ...])   # before sending
    await store.append(trace_id, [(seq, "done", data)], final=True)
    request = await store.find(principal_key, client_request_id)
    events = await store.after(trace_id, seq)

The work belongs to the request, not the connection. The worker beats `heartbeat_at`
while it runs; a request whose heartbeat stopped without a terminal event is ended as
`interrupted` by whoever reconnects. A terminal event and `finished_at` are written in
one transaction, and an append to a finished request saves nothing: a worker that was
presumed dead learns so from its next append and stops.

Every operation is one short transaction on the database clock, like the StateStore.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import JSON, Integer, String

HEARTBEAT_S = 5
DEAD_AFTER_S = 20  # four missed heartbeats
EVENTS_KEPT = timedelta(minutes=10)  # they hold health advice
REQUESTS_KEPT = timedelta(days=1)

Event = tuple[int, str, dict[str, Any]]  # seq, event name, data


class RequestEnded(Exception):
    """The request already has a terminal event: this worker must stop."""


@dataclass(frozen=True)
class RequestState:
    trace_id: str
    finished: bool
    alive: bool  # a worker has beaten within DEAD_AFTER_S (or the request just began)


class StreamStore:
    def __init__(self, engine: AsyncEngine):
        self._engine = engine

    async def start(self, trace_id: str, worker: str) -> None:
        """The worker takes the request: its first heartbeat."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE chat_requests SET worker = :worker, heartbeat_at = now() "
                     "WHERE trace_id = :trace"),
                {"worker": worker, "trace": trace_id})

    async def heartbeat(self, trace_id: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                text("UPDATE chat_requests SET heartbeat_at = now() "
                     "WHERE trace_id = :trace AND finished_at IS NULL"),
                {"trace": trace_id})

    async def append(self, trace_id: str, events: list[Event], final: bool = False) -> None:
        """Save events in order; `final`: the last is terminal and ends the request.
        Raises RequestEnded if the request already ended (or was never claimed)."""
        if not events:
            return
        rows = [{"trace": trace_id, "seq": seq, "event": name, "data": data}
                for seq, name, data in events]
        insert = text(
            "INSERT INTO stream_events (trace_id, seq, event, data) "
            "VALUES (:trace, :seq, :event, :data) ON CONFLICT DO NOTHING"
        ).bindparams(bindparam("data", type_=JSON))
        async with self._engine.begin() as conn:
            # Lock the request so an `interrupted` can't land between the check and the
            # insert
            open_ = await conn.execute(
                text("SELECT 1 FROM chat_requests WHERE trace_id = :trace "
                     "AND finished_at IS NULL FOR UPDATE"), {"trace": trace_id})
            if open_.one_or_none() is None:
                raise RequestEnded(trace_id)
            for row in rows:
                saved = await conn.execute(insert, row)
                if saved.rowcount != 1:
                    raise RequestEnded(trace_id)  # that seq is taken: someone else ended it
            if final:
                await conn.execute(
                    text("UPDATE chat_requests SET finished_at = now() "
                         "WHERE trace_id = :trace"), {"trace": trace_id})

    async def find(self, principal_key: str, client_request_id: uuid.UUID
                   ) -> RequestState | None:
        """The caller's own request, or None (someone else's looks like none)."""
        async with self._engine.connect() as conn:
            row = (await conn.execute(
                text("SELECT trace_id, finished_at IS NOT NULL, "
                     "coalesce(heartbeat_at, created_at) > now() - make_interval(secs => :dead) "
                     "FROM chat_requests WHERE principal_key = :key "
                     "AND client_request_id = :rid"),
                {"key": principal_key, "rid": client_request_id, "dead": DEAD_AFTER_S},
            )).one_or_none()
        return RequestState(*row) if row is not None else None

    async def finished(self, trace_id: str) -> bool:
        async with self._engine.connect() as conn:
            return bool((await conn.execute(
                text("SELECT finished_at IS NOT NULL FROM chat_requests WHERE trace_id = :t"),
                {"t": trace_id})).scalar_one_or_none())

    async def after(self, trace_id: str, seq: int) -> list[Event]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(
                text("SELECT seq, event, data FROM stream_events "
                     "WHERE trace_id = :trace AND seq > :seq ORDER BY seq"
                     ).columns(seq=Integer, event=String, data=JSON),
                {"trace": trace_id, "seq": seq},
            )).all()
        return [(s, e, d) for s, e, d in rows]

    async def interrupt(self, trace_id: str, data: dict[str, Any]) -> Event | None:
        """End a request whose worker is gone with `error` `interrupted`, saved after its
        last event. None if it ended or beat meanwhile (nothing is written then)."""
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                text("SELECT 1 FROM chat_requests WHERE trace_id = :trace "
                     "AND finished_at IS NULL AND coalesce(heartbeat_at, created_at) "
                     "<= now() - make_interval(secs => :dead) FOR UPDATE"),
                {"trace": trace_id, "dead": DEAD_AFTER_S})).one_or_none()
            if row is None:
                return None
            last = (await conn.execute(
                text("SELECT coalesce(max(seq), -1) FROM stream_events WHERE trace_id = :t"),
                {"t": trace_id})).scalar_one()
            event: Event = (last + 1, "error", {"seq": last + 1, **data})
            await conn.execute(
                text("INSERT INTO stream_events (trace_id, seq, event, data) "
                     "VALUES (:trace, :seq, 'error', :data)").bindparams(
                    bindparam("data", type_=JSON)),
                {"trace": trace_id, "seq": event[0], "data": event[2]})
            await conn.execute(
                text("UPDATE chat_requests SET finished_at = now() WHERE trace_id = :trace"),
                {"trace": trace_id})
        return event

    async def purge(self) -> tuple[int, int]:
        """For the 2-minute job (C.19): events after 10 minutes, requests after a day."""
        async with self._engine.begin() as conn:
            events = await conn.execute(
                text("DELETE FROM stream_events WHERE created_at < now() - :kept"),
                {"kept": EVENTS_KEPT})
            requests = await conn.execute(
                text("DELETE FROM chat_requests WHERE created_at < now() - :kept"),
                {"kept": REQUESTS_KEPT})
        return events.rowcount, requests.rowcount
