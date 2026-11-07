"""The 2-minute job (Plan C.19): every process runs the loop, one at a time runs the tasks.

    jobs = Jobs(engine, images)
    task = start(jobs)            # app startup
    await stop(task)              # shutdown
    await jobs.run_once()         # tests: the tasks once, or None if another process has them

A run holds `pg_try_advisory_xact_lock` on a connection of its own; a process that
doesn't get it skips the run. The transaction ends with the run, or with the connection,
so a process that dies never keeps the lock. Each task is its own short transaction on
the database clock and has its own time limit: one failing or hanging task is logged and
the rest still run.

Day and month caps roll over by themselves: every spend row and rate window is keyed by
its period's start (budget.py), so a new day reads a new row and the month's row runs
on. The job only deletes what has outlived its lifetime (C.11): guest rows after 240
minutes, account rate counters after a day, expired sessions, leases, crisis flags,
decided pending writes and invites, saved streams, old unresolved terms; and retries image
deletions. Account and global spend, account traces and rule hit counts are kept.

It also watches the failure rate (failure library, Part E #55): over 10% of at least 10
requests in the last 5 minutes ended in an error or a partial answer (a spend cap isn't
a failure) → one ERROR line starting "ALERT failure_rate", with the commonest causes,
for monitoring to pick up (Phase 7). The same rows can feed a dashboard later.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import limits
from app.data.state_store import StateStore
from app.data.stream_store import StreamStore
from app.observability import terms
from app.storage.deletion import retry_deletions
from app.storage.images import ImageStore

log = logging.getLogger(__name__)

INTERVAL_S = 120
TASK_LIMIT_S = 60
LOCK_KEY = 0x486F6C6F73  # "Holos": the job's advisory lock
FAILURE_WINDOW = timedelta(minutes=5)
FAILURE_SHARE = 0.10
FAILURE_MIN_REQUESTS = 10  # below this, one or two failures are not a trend
ACCOUNT_COUNTERS_KEPT = timedelta(days=1)  # the longest account window (C.12)

_GUEST = "(starts_with(key, 'session:') OR starts_with(key, 'ip:'))"

# name -> statement; each deletes the rows past their lifetime (C.11)
_DELETES = {
    "leases": "DELETE FROM inflight_leases WHERE expires_at < now()",
    # A waiting entry has no expiry (NULL); a decided one is kept a day
    "pending_writes": "DELETE FROM pending_writes WHERE expires_at <= now()",
    "invites": "DELETE FROM invites WHERE expires_at <= now()",
    # Every window but an account's is at most 240 minutes long (C.12)
    "rate_counters": "DELETE FROM rate_counters WHERE window_start < now() - CASE "
                     "WHEN starts_with(key, 'user:') THEN :account ELSE :guest END",
    "guest_spend": f"DELETE FROM spend WHERE {_GUEST} AND period_start < now() - :guest",
    "guest_traces": "DELETE FROM traces WHERE user_id IS NULL AND created_at < now() - :guest",
    "guest_decisions": "DELETE FROM gate_decisions WHERE user_id IS NULL "
                       "AND created_at < now() - :guest",
}


# A request failed: not a success, and not stopped by a spend cap (a notice, not a fault)
_FAILURES = text(
    "SELECT count(*), count(*) FILTER (WHERE NOT success AND NOT EXISTS ("
    "SELECT 1 FROM json_array_elements(steps->'attempts') a "
    "WHERE a->>'outcome' = 'over_budget')) FROM traces WHERE created_at > now() - :window")
_CAUSES = text(
    "SELECT a->>'outcome' AS cause, count(*) AS n FROM traces, "
    "json_array_elements(steps->'attempts') a WHERE traces.created_at > now() - :window "
    "AND a->>'outcome' NOT IN ('ok', 'running', 'cancelled') "
    "GROUP BY 1 ORDER BY n DESC, cause LIMIT 3")


@dataclass
class Jobs:
    engine: AsyncEngine
    images: ImageStore
    state: StateStore = field(init=False)
    streams: StreamStore = field(init=False)

    def __post_init__(self) -> None:
        self.state = StateStore(self.engine)
        self.streams = StreamStore(self.engine)

    def tasks(self) -> dict[str, Callable[[], Awaitable[int]]]:
        tasks = {"sessions": self.state.purge_expired_sessions,
                 "crisis_flags": self.state.purge_expired_flags}
        tasks |= {name: (lambda sql=sql: self._delete(sql)) for name, sql in _DELETES.items()}
        return tasks | {"streams": self._streams, "unresolved_terms": self._terms,
                        "image_deletions": lambda: retry_deletions(self.engine, self.images),
                        "failure_alert": self._failure_rate}

    async def run_once(self) -> dict[str, int] | None:
        """Each task once; how many rows each removed (None for one that failed)."""
        async with self.engine.connect() as conn, conn.begin():
            if not await conn.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"),
                                     {"k": LOCK_KEY}):
                return None
            done = {}
            for name, task in self.tasks().items():
                try:
                    done[name] = await asyncio.wait_for(task(), TASK_LIMIT_S)
                except Exception:
                    log.exception("job task failed: %s", name)
                    done[name] = None
        if removed := {name: n for name, n in done.items() if n}:
            log.info("jobs: %s", removed)
        return done

    async def _delete(self, sql: str) -> int:
        async with self.engine.begin() as conn:
            result = await conn.execute(text(sql), {
                "guest": limits.GUEST_SESSION_TTL, "account": ACCOUNT_COUNTERS_KEPT})
        return result.rowcount

    async def _streams(self) -> int:
        return sum(await self.streams.purge())

    async def _failure_rate(self) -> int:
        """1 if it logged an alert. Read before this run deletes old guest traces."""
        async with self.engine.connect() as conn:
            total, failed = (await conn.execute(_FAILURES, {"window": FAILURE_WINDOW})).one()
            if total < FAILURE_MIN_REQUESTS or failed <= FAILURE_SHARE * total:
                return 0
            causes = (await conn.execute(_CAUSES, {"window": FAILURE_WINDOW})).all()
        log.error("ALERT failure_rate: %d of %d requests failed in the last %d minutes "
                  "(%d%%); causes: %s", failed, total, FAILURE_WINDOW.seconds // 60,
                  round(100 * failed / total),
                  ", ".join(f"{c} {n}" for c, n in causes) or "none recorded")
        return 1

    async def _terms(self) -> int:
        async with self.engine.begin() as conn:
            return (await conn.execute(terms.PURGE, {"keep": terms.KEEP_DAYS})).rowcount


async def loop(jobs: Jobs, interval_s: float = INTERVAL_S,
               sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
    while True:
        try:
            await jobs.run_once()
        except Exception:  # the database is down: try again next time
            log.exception("job run failed")
        await sleep(interval_s)


def start(jobs: Jobs) -> asyncio.Task:
    return asyncio.get_running_loop().create_task(loop(jobs), name="jobs")


async def stop(task: asyncio.Task) -> None:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
