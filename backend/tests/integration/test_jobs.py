"""The 2-minute job (Plan C.19): each task deletes exactly the rows past their lifetime,
one process at a time runs it (advisory lock), and a new day resets the day caps only.

Every lifetime is on the database clock, so rows are placed either side of their
boundary by their timestamps; the loop's own clock is its `sleep`."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.agents.schemas import Decision
from app.data.state_store import StateStore
from app.data.stream_store import StreamStore
from app.jobs import scheduler
from app.jobs.scheduler import Jobs
from app.observability import background
from app.observability.tracer import Trace
from app.orchestration.budget import spend_keys

from .test_admission import account, make_user, sql

pytestmark = pytest.mark.asyncio


class Images:
    """Deletes every prefix but the ones listed as failing."""

    def __init__(self, failing=()):
        self.failing, self.deleted = set(failing), []

    async def delete_prefix(self, prefix):
        if prefix in self.failing:
            raise OSError("storage down")
        self.deleted.append(prefix)


@pytest_asyncio.fixture
async def jobs(async_engine):
    return Jobs(async_engine, Images())


async def keys(engine, statement):
    return sorted(row[0] for row in await sql(engine, statement))


async def test_sessions_leases_flags_writes_and_invites_go_when_expired(jobs, async_engine):
    user = await make_user(async_engine)
    for name, mode, uid, ends in (("guest-old", "guest", None, "-1 second"),
                                  ("guest-new", "guest", None, "1 minute"),
                                  ("account-old", "account", user, "-1 second"),
                                  ("account-new", "account", user, "7 days")):
        await sql(async_engine, "INSERT INTO sessions (id_hash, mode, user_id, ip_key, "
                  "expires_at) VALUES (:h, :m, :u, 'ipk', now() + CAST(:e AS interval))",
                  h=name, m=mode, u=uid, e=ends)
    for key, ends in (("user:1", "-1 second"), ("user:2", "30 seconds"),
                      ("global:0", "-1 second"), ("ip:k:0", "30 seconds")):
        await sql(async_engine, "INSERT INTO inflight_leases (principal_key, trace_id, "
                  "expires_at) VALUES (:k, :k, now() + CAST(:e AS interval))", k=key, e=ends)
    for key, at in (("old", "31 minutes"), ("new", "29 minutes")):
        await sql(async_engine, "INSERT INTO principal_flags (principal_key, crisis_at) "
                  "VALUES (:k, now() - CAST(:a AS interval))", k=key, a=at)
    # A waiting entry has no expiry however old (Part E #50); a decided one is kept a day
    for kind, status, ends, age in (("meal", "pending", None, "400 days"),
                                    ("practice", "committed", "-1 second", "1 day"),
                                    ("workout", "discarded", "-1 second", "1 day"),
                                    ("workout", "discarded", "20 hours", "4 hours")):
        await sql(async_engine, "INSERT INTO pending_writes (id, user_id, kind, payload, "
                  "profile_hash, trace_id, status, created_at, expires_at) VALUES (:i, :u, :k, "
                  "'{}', 'h', 't', :s, now() - CAST(:a AS interval), "
                  "now() + CAST(:e AS interval))",
                  i=uuid.uuid4(), u=user, k=kind, s=status, a=age, e=ends)
    for token, ends, used in (("old", "-1 second", None), ("live", "1 day", None),
                              ("used", "1 day", user)):
        await sql(async_engine, "INSERT INTO invites (id, token_hash, created_by, expires_at, "
                  "used_by) VALUES (:i, :t, 'owner', now() + CAST(:e AS interval), :u)",
                  i=uuid.uuid4(), t=token, e=ends, u=used)

    done = await jobs.run_once()

    assert await keys(async_engine, "SELECT id_hash FROM sessions") == ["account-new",
                                                                         "guest-new"]
    assert await keys(async_engine, "SELECT principal_key FROM inflight_leases") == [
        "ip:k:0", "user:2"]
    assert await keys(async_engine, "SELECT principal_key FROM principal_flags") == ["new"]
    assert await keys(async_engine, "SELECT status || ':' || kind FROM pending_writes") == [
        "discarded:workout", "pending:meal"]
    assert await keys(async_engine, "SELECT token_hash FROM invites") == ["live", "used"]
    assert {k: done[k] for k in ("sessions", "leases", "crisis_flags", "pending_writes",
                                 "invites")} == {"sessions": 2, "leases": 2, "crisis_flags": 1,
                                                 "pending_writes": 2, "invites": 1}


async def test_guest_rows_go_after_240_minutes_account_rows_stay(jobs, async_engine):
    user = await make_user(async_engine)
    # Rate counters: guests' and everyone else's windows end within 240 minutes, accounts'
    # within a day
    for key, age in (("session:a:requests", "241 minutes"), ("session:b:requests", "239 minutes"),
                     ("ip:k:requests", "241 minutes"), ("flood:k", "241 minutes"),
                     ("login:account:x", "239 minutes"),
                     ("user:1:requests", "25 hours"), ("user:2:requests", "241 minutes")):
        await sql(async_engine, "INSERT INTO rate_counters (key, window_start, count) "
                  "VALUES (:k, now() - CAST(:a AS interval), 1)", k=key, a=age)
    for key, period, age in (("session:a", "day", "241 minutes"),
                             ("session:b", "day", "239 minutes"),
                             ("ip:k", "day", "241 minutes"), ("ip:j", "day", "239 minutes"),
                             ("user:1", "day", "400 days"), ("global", "month", "400 days"),
                             ("tavily", "day", "400 days")):
        await sql(async_engine, "INSERT INTO spend (key, period, period_start) "
                  "VALUES (:k, :p, now() - CAST(:a AS interval))", k=key, p=period, a=age)
    for trace, uid, age in (("guest-old", None, "241 minutes"), ("guest-new", None, "239 minutes"),
                            ("account-old", user, "400 days")):
        await sql(async_engine, "INSERT INTO traces (trace_id, user_id, route, steps, usage, "
                  "success, created_at) VALUES (:t, :u, 'coaching', '{}', '{}', true, "
                  "now() - CAST(:a AS interval))", t=trace, u=uid, a=age)
        await sql(async_engine, "INSERT INTO gate_decisions (trace_id, user_id, rule_id, "
                  "rules_version, action, reason, created_at) VALUES (:t, :u, 'R', 1, 'block', "
                  "'r', now() - CAST(:a AS interval))", t=trace, u=uid, a=age)

    done = await jobs.run_once()

    assert await keys(async_engine, "SELECT key FROM rate_counters") == [
        "login:account:x", "session:b:requests", "user:2:requests"]
    assert await keys(async_engine, "SELECT key FROM spend") == [
        "global", "ip:j", "session:b", "tavily", "user:1"]
    for table in ("traces", "gate_decisions"):
        assert await keys(async_engine, f"SELECT trace_id FROM {table}") == [
            "account-old", "guest-new"]
    assert (done["rate_counters"], done["guest_spend"], done["guest_traces"],
            done["guest_decisions"]) == (4, 2, 1, 1)


async def test_streams_terms_and_queued_image_deletions(async_engine):
    streams = StreamStore(async_engine)
    for trace, age in (("t-old", "25 hours"), ("t-new", "1 hour")):
        await StateStore(async_engine).claim_request(f"session:{trace}", uuid.uuid4(), None,
                                                     trace)
        await streams.append(trace, [(0, "step", {})])
        await sql(async_engine, "UPDATE chat_requests SET created_at = now() - "
                  "CAST(:a AS interval) WHERE trace_id = :t", a=age, t=trace)
    await sql(async_engine, "UPDATE stream_events SET created_at = now() - interval '11 min' "
              "WHERE trace_id = 't-new'")
    await streams.append("t-new", [(1, "step", {})])
    for term, age in (("old", 90), ("new", 89)):
        await sql(async_engine, "INSERT INTO unresolved_terms (term, field, day, count) "
                  "VALUES (:t, 'conditions', current_date - :a, 3)", t=term, a=age)
    for prefix in ("users/1/", "users/2/"):
        await sql(async_engine, "INSERT INTO deletion_queue (prefix, attempts) "
                  "VALUES (:p, 1)", p=prefix)
    images = Images(failing={"users/2/"})

    done = await Jobs(async_engine, images).run_once()

    assert await sql(async_engine, "SELECT trace_id FROM chat_requests") == [("t-new",)]
    assert await sql(async_engine, "SELECT trace_id, seq FROM stream_events") == [("t-new", 1)]
    assert await sql(async_engine, "SELECT term FROM unresolved_terms") == [("new",)]
    assert images.deleted == ["users/1/"]
    assert await sql(async_engine, "SELECT prefix, attempts FROM deletion_queue") == [
        ("users/2/", 2)]
    # t-new's old event, and t-old with its events
    assert (done["streams"], done["unresolved_terms"], done["image_deletions"]) == (2, 1, 1)


async def test_a_run_with_nothing_expired_deletes_nothing(jobs, async_engine):
    me = await account(StateStore(async_engine), async_engine)
    await sql(async_engine, "INSERT INTO spend (key, period, period_start) "
              "VALUES (:k, 'day', now())", k=me.principal_key)
    done = await jobs.run_once()
    assert set(done.values()) == {0}
    assert await sql(async_engine, "SELECT count(*) FROM sessions") == [(1,)]
    assert await sql(async_engine, "SELECT count(*) FROM spend") == [(1,)]


async def _hold_lock(engine, held: asyncio.Event, release: asyncio.Event):
    async with engine.connect() as conn, conn.begin():
        await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": scheduler.LOCK_KEY})
        held.set()
        await release.wait()


async def test_only_one_process_runs_the_tasks(jobs, async_engine):
    await sql(async_engine, "INSERT INTO principal_flags (principal_key, crisis_at) "
              "VALUES ('old', now() - interval '1 hour')")
    held, release = asyncio.Event(), asyncio.Event()
    other = asyncio.create_task(_hold_lock(async_engine, held, release))
    await held.wait()
    assert await jobs.run_once() is None  # another process is running them
    assert await sql(async_engine, "SELECT count(*) FROM principal_flags") == [(1,)]
    release.set()
    await other
    assert (await jobs.run_once())["crisis_flags"] == 1  # the lock went with its transaction


async def test_two_schedulers_at_once_run_the_tasks_once(async_engine, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    runs = []

    async def slow(self):
        runs.append(1)
        started.set()
        await release.wait()
        return 0

    monkeypatch.setattr(Jobs, "_terms", slow)
    first = asyncio.create_task(Jobs(async_engine, Images()).run_once())
    await started.wait()
    second = await Jobs(async_engine, Images()).run_once()
    release.set()
    assert second is None and (await first)["unresolved_terms"] == 0
    assert runs == [1]


async def test_a_failing_or_hanging_task_doesnt_stop_the_others(jobs, async_engine,
                                                                monkeypatch):
    async def fails(self):
        raise RuntimeError("boom")

    async def hangs(self):
        await asyncio.Event().wait()

    monkeypatch.setattr(Jobs, "_streams", fails)
    monkeypatch.setattr(Jobs, "_terms", hangs)
    monkeypatch.setattr(scheduler, "TASK_LIMIT_S", 0.2)
    await sql(async_engine, "INSERT INTO deletion_queue (prefix, attempts) VALUES ('p/', 1)")
    done = await asyncio.wait_for(jobs.run_once(), 10)
    assert (done["streams"], done["unresolved_terms"], done["image_deletions"]) == (None, None, 1)
    assert await jobs.run_once() is not None  # and the lock was let go


async def test_the_loop_runs_every_interval_and_survives_a_failed_run(async_engine):
    runs, waits = [], []

    class Flaky(Jobs):
        async def run_once(self):
            runs.append(1)
            if len(runs) == 2:
                raise ConnectionError("database down")
            return {}

    async def sleep(seconds):
        waits.append(seconds)
        if len(waits) == 3:
            raise asyncio.CancelledError  # the app stopping

    with pytest.raises(asyncio.CancelledError):
        await scheduler.loop(Flaky(async_engine, Images()), sleep=sleep)
    assert (len(runs), waits) == (3, [scheduler.INTERVAL_S] * 3)


async def test_stop_ends_a_run_in_progress(async_engine, monkeypatch):
    started = asyncio.Event()

    async def hangs(self):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(Jobs, "_terms", hangs)
    task = scheduler.start(Jobs(async_engine, Images()))
    await asyncio.wait_for(started.wait(), 5)
    await asyncio.wait_for(scheduler.stop(task), 5)
    assert task.cancelled()
    monkeypatch.undo()
    assert await Jobs(async_engine, Images()).run_once() is not None  # its lock is gone


async def test_a_new_day_resets_the_day_caps_only(async_engine, jobs):
    store = StateStore(async_engine)
    me = await account(store, async_engine)
    evening = datetime(2026, 11, 5, 23, 59, tzinfo=UTC)
    morning = evening + timedelta(minutes=2)
    for now in (evening, morning):
        await store.settle(await store.reserve(spend_keys(me, now), Decimal("0.01")),
                           Decimal("0.03"))
    account_day = [k for k in spend_keys(me, evening) if k.name == "account"]
    await store.settle(await store.reserve(account_day, Decimal("0")), Decimal("0.02"))

    assert (await store.first_over_cap(spend_keys(me, evening))).name == "account"  # $0.05
    assert await store.first_over_cap(spend_keys(me, morning)) is None
    await jobs.run_once()  # yesterday's account and global rows are kept
    rows = await sql(async_engine, "SELECT key, period, period_start, cost_usd FROM spend "
                     "ORDER BY key, period, period_start")
    nov5, nov6 = (datetime(2026, 11, d, tzinfo=UTC) for d in (5, 6))
    assert [(k, p, s.astimezone(UTC), c) for k, p, s, c in rows] == [
        ("global", "day", nov5, Decimal("0.03")),
        ("global", "day", nov6, Decimal("0.03")),
        ("global", "month", datetime(2026, 11, 1, tzinfo=UTC), Decimal("0.06")),
        (me.principal_key, "day", nov5, Decimal("0.05")),
        (me.principal_key, "day", nov6, Decimal("0.03")),
    ]


async def test_rule_hits_are_counted_once_and_outlive_guest_rows(async_engine, jobs):
    blocked = Decision(action="block", rule_id="DI-NUT-01", rules_version=1, reason="nuts",
                       offending_items=["Peanuts", "Cashews"])
    warned = Decision(action="warn", rule_id="EX-KNEE-01", rules_version=1, reason="knee")
    for trace in ("t1", "t2"):
        await background.write(async_engine, background.Outcome(
            Trace(trace), None, None, decisions=[blocked, warned, blocked]))
    await background.write(async_engine, background.Outcome(Trace("t3"), None, None))
    await sql(async_engine, "UPDATE gate_decisions SET created_at = now() - interval '5 hours'")
    await sql(async_engine, "UPDATE traces SET created_at = now() - interval '5 hours'")

    await jobs.run_once()
    assert await sql(async_engine, "SELECT count(*) FROM gate_decisions") == [(0,)]
    assert await sql(async_engine, "SELECT rule_id, count FROM rule_hit_counts "
                     "WHERE day = current_date ORDER BY rule_id") == [
        ("DI-NUT-01", 4), ("EX-KNEE-01", 2)]


# --- The failure-rate alert (failure library, Part E #55) ---


async def _traces(engine, n, success, outcome="ok", age="1 minute"):
    steps = json.dumps({"steps": [], "attempts": [{"call": "physical", "outcome": outcome}]})
    for _ in range(n):
        await sql(engine, "INSERT INTO traces (trace_id, route, steps, usage, success, "
                  "created_at) VALUES (:t, 'coaching', CAST(:s AS json), '{}', :ok, "
                  "now() - CAST(:a AS interval))",
                  t=uuid.uuid4().hex, s=steps, ok=success, a=age)


def _alerts(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "ALERT failure_rate" in r.getMessage()]


async def test_a_failure_rate_over_ten_percent_alerts_with_its_causes(jobs, async_engine,
                                                                      caplog):
    await _traces(async_engine, 17, True)
    await _traces(async_engine, 2, False, "deadline_waiting")
    await _traces(async_engine, 1, False, "unavailable")
    with caplog.at_level("ERROR"):
        assert (await jobs.run_once())["failure_alert"] == 1
    assert _alerts(caplog) == ["ALERT failure_rate: 3 of 20 requests failed in the last 5 "
                               "minutes (15%); causes: deadline_waiting 2, unavailable 1"]


@pytest.mark.parametrize(("good", "bad", "why"), [
    (18, 2, "exactly 10% is not over it"),
    (0, 9, "fewer than 10 requests: not a trend"),
])
async def test_no_alert_at_or_below_the_line(jobs, async_engine, caplog, good, bad, why):
    await _traces(async_engine, good, True)
    await _traces(async_engine, bad, False, "unavailable")
    with caplog.at_level("ERROR"):
        assert (await jobs.run_once())["failure_alert"] == 0, why
    assert _alerts(caplog) == []


async def test_spend_caps_and_old_requests_are_not_failures(jobs, async_engine, caplog):
    await _traces(async_engine, 10, True)
    await _traces(async_engine, 5, False, "over_budget")  # a cap: a notice, not a fault
    await _traces(async_engine, 5, False, "unavailable", age="6 minutes")  # outside the window
    with caplog.at_level("ERROR"):
        assert (await jobs.run_once())["failure_alert"] == 0
    assert _alerts(caplog) == []
