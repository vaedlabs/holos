"""Saved stream events on a real Postgres (Plan C.5, C.11, Part E #34): a reconnect gets
what it missed, a dead worker's request ends as `interrupted` exactly once, and a
worker presumed dead can't add to it afterwards."""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.data.state_store import StateStore
from app.data.stream_store import DEAD_AFTER_S, RequestEnded, StreamStore
from app.orchestration.stream import follow

pytestmark = pytest.mark.asyncio

KEY = "session:abc"
INTERRUPTED = {"trace_id": "t1", "code": "interrupted", "message": "Interrupted."}


@pytest_asyncio.fixture
async def streams(async_engine):
    return StreamStore(async_engine)


@pytest_asyncio.fixture
async def request_id(async_engine):
    rid = uuid.uuid4()
    assert await StateStore(async_engine).claim_request(KEY, rid, None, "t1")
    return rid


async def _sql(engine, sql: str, **params):
    async with engine.begin() as conn:
        result = await conn.execute(text(sql), params)
        return result.all() if result.returns_rows else []


def _ev(seq: int, name: str = "step") -> tuple[int, str, dict]:
    return seq, name, {"seq": seq, "trace_id": "t1", "name": "routed"}


async def _stale(engine) -> None:
    await _sql(engine, "UPDATE chat_requests SET heartbeat_at = now() - make_interval("
               "secs => :s), created_at = now() - make_interval(secs => :s)",
               s=DEAD_AFTER_S + 1)


async def test_saved_events_come_back_after_a_seq(streams, request_id):
    await streams.start("t1", "worker-a")
    await streams.append("t1", [_ev(0, "accepted"), _ev(1), _ev(2)])
    assert [e[0] for e in await streams.after("t1", 0)] == [1, 2]
    assert (await streams.after("t1", -1))[0][2] == {"seq": 0, "trace_id": "t1",
                                                      "name": "routed"}
    state = await streams.find(KEY, request_id)
    assert (state.trace_id, state.finished, state.alive) == ("t1", False, True)


async def test_someone_elses_request_is_not_found(streams, request_id):
    assert await streams.find("session:other", request_id) is None
    assert await streams.find(KEY, uuid.uuid4()) is None


async def test_the_terminal_event_ends_the_request_and_nothing_follows_it(
        streams, request_id):
    await streams.append("t1", [_ev(0), _ev(1, "done")], final=True)
    assert (await streams.find(KEY, request_id)).finished
    with pytest.raises(RequestEnded):
        await streams.append("t1", [_ev(2)])


async def test_a_dead_worker_ends_as_interrupted_once(streams, request_id, async_engine):
    await streams.start("t1", "worker-a")
    await streams.append("t1", [_ev(0), _ev(1)])
    assert await streams.interrupt("t1", INTERRUPTED) is None  # still beating
    await _stale(async_engine)
    assert not (await streams.find(KEY, request_id)).alive
    ended = await streams.interrupt("t1", INTERRUPTED)
    assert ended == (2, "error", {"seq": 2, **INTERRUPTED})
    assert await streams.interrupt("t1", INTERRUPTED) is None  # already ended
    # The worker comes back (a laptop waking up): it learns it must stop
    with pytest.raises(RequestEnded):
        await streams.append("t1", [_ev(2)])
    assert [e[1] for e in await streams.after("t1", -1)] == ["step", "step", "error"]


async def test_a_worker_and_an_interrupt_racing_leave_one_end(streams, request_id,
                                                              async_engine):
    for _ in range(10):
        await _sql(async_engine, "DELETE FROM stream_events")
        await _sql(async_engine, "UPDATE chat_requests SET finished_at = NULL")
        await _stale(async_engine)
        results = await asyncio.gather(
            streams.append("t1", [_ev(0), _ev(1, "done")], final=True),
            streams.interrupt("t1", INTERRUPTED), return_exceptions=True)
        ends = await _sql(async_engine, "SELECT count(*) FROM stream_events "
                          "WHERE event IN ('done', 'error')")
        assert ends == [(1,)], results


async def test_heartbeats_keep_a_request_alive(streams, request_id, async_engine):
    await _stale(async_engine)
    await streams.heartbeat("t1")
    assert (await streams.find(KEY, request_id)).alive
    assert await streams.interrupt("t1", INTERRUPTED) is None


async def test_follow_replays_then_waits_for_live_events(streams, request_id):
    await streams.start("t1", "worker-a")
    await streams.append("t1", [_ev(0), _ev(1)])
    seen: list[int] = []

    async def reader():
        async for event in follow(streams, "t1", 0, poll_s=0.01):
            seen.append(event[0])

    task = asyncio.create_task(reader())
    await asyncio.sleep(0.05)
    assert seen == [1]
    await streams.append("t1", [_ev(2), _ev(3, "done")], final=True)
    await asyncio.wait_for(task, 2)
    assert seen == [1, 2, 3]



async def test_follow_keeps_the_events_saved_as_the_request_ends():
    """The read finds nothing, then the request saves its last events and finishes
    before `follow` asks whether it has: those events still reach the person."""

    class Ending:
        reads = 0

        async def after(self, trace_id, seq):
            self.reads += 1
            return [] if self.reads == 1 else [_ev(2), _ev(3, "done")]

        async def interrupt(self, trace_id, data):
            return None

        async def finished(self, trace_id):
            return True

    assert [e[0] async for e in follow(Ending(), "t1", 1, poll_s=0.01)] == [2, 3]

async def test_follow_ends_a_dead_request_as_interrupted(streams, request_id, async_engine):
    await streams.append("t1", [_ev(0)])
    await _stale(async_engine)
    events = [e async for e in follow(streams, "t1", 0, poll_s=0.01)]
    assert [(e[0], e[1], e[2]["code"]) for e in events] == [(1, "error", "interrupted")]


async def test_purge_keeps_recent_events_and_requests(streams, request_id, async_engine):
    await streams.append("t1", [_ev(0)])
    assert await streams.purge() == (0, 0)
    await _sql(async_engine, "UPDATE stream_events SET created_at = now() - interval '11 min'")
    assert await streams.purge() == (1, 0)
    await _sql(async_engine, "UPDATE chat_requests SET created_at = now() - interval '25 hours'")
    assert await streams.purge() == (0, 1)


async def test_deleting_a_user_deletes_their_requests_and_events(streams, async_engine):
    user = (await _sql(async_engine, "INSERT INTO users (email, username, password_hash) "
                       "VALUES ('d@x.io', 'd', 'h') RETURNING id"))[0][0]
    await StateStore(async_engine).claim_request(f"user:{user}", uuid.uuid4(), user, "t2")
    await streams.append("t2", [(0, "step", {"seq": 0})])
    await _sql(async_engine, "DELETE FROM users WHERE id = :u", u=user)
    assert await _sql(async_engine, "SELECT count(*) FROM stream_events") == [(0,)]


async def test_a_seq_already_saved_is_refused(streams, request_id):
    # Two writers on one request (a bug, or a worker resumed after a takeover): the
    # second gets RequestEnded rather than silently losing its event
    await streams.append("t1", [_ev(0)])
    with pytest.raises(RequestEnded):
        await streams.append("t1", [_ev(0)])


async def test_follow_stops_at_the_terminal_event_without_asking_again():
    class Store:
        calls: list[str] = []

        async def after(self, trace_id, seq):
            await asyncio.sleep(0)  # a real query yields, so the time limit can stop it
            self.calls.append("after")
            return [(seq + 1, "step", {}), (seq + 2, "done", {})]

        async def interrupt(self, *a):
            self.calls.append("interrupt")

        async def finished(self, *a):
            self.calls.append("finished")
            return True

    async def read():
        return [e async for e in follow(store, "t1", 0, poll_s=0)]  # type: ignore[arg-type]

    store = Store()
    events = await asyncio.wait_for(read(), 1)  # a follow that never stops fails here
    assert [e[1] for e in events] == ["step", "done"] and store.calls == ["after"]
