"""After the response (Plan C.2 stage 15): a request's trace and gate decisions go to the
database in a task of their own, so `done` never waits on them.

    record(engine, Outcome(...))       # the worker, once the request has ended
    await settled()                    # tests and a planned restart

`traces`: the route, every step and model attempt (no prompts, no person's text: the
Trace never holds them), usage and an honest success flag (an error reply is never a
success). `gate_decisions`: one row per decision and offending item. `rule_hit_counts`:
each decision counted once per rule and day, with no user or trace. A failed write is
logged and dropped: losing a trace must never fail a request.
"""

import asyncio
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.observability.tracer import Trace

log = logging.getLogger(__name__)

ITEM_MAX = 200
# Each decision once, outliving the guest rows the job deletes (C.19)
_HIT = text("INSERT INTO rule_hit_counts (rule_id, day, count) VALUES (:rule, current_date, :n) "
            "ON CONFLICT (rule_id, day) DO UPDATE SET count = rule_hit_counts.count + :n")
_pending: set[asyncio.Task] = set()


@dataclass
class Outcome:
    """What a request ended with, filled in as it runs."""

    trace: Trace
    session_id_hash: str | None
    user_id: int | None
    route: str = "coaching"  # the turn's kind (C.15) or "crisis"
    decisions: list[Any] = field(default_factory=list)  # schemas.Decision
    usage: dict[str, Any] = field(default_factory=dict)
    # Only a request that ended in `done` with every chosen coach answering
    success: bool = False


def record(engine: AsyncEngine, outcome: Outcome) -> asyncio.Task:
    task = asyncio.get_running_loop().create_task(_write(engine, outcome))
    _pending.add(task)
    task.add_done_callback(_pending.discard)
    return task


async def settled(timeout: float = 10) -> None:
    loop = asyncio.get_running_loop()
    if mine := {t for t in _pending if t.get_loop() is loop}:  # another loop's can't be awaited
        await asyncio.wait(mine, timeout=timeout)


async def _write(engine: AsyncEngine, outcome: Outcome) -> None:
    trace_id = outcome.trace.trace_id
    try:
        await write(engine, outcome)
    except Exception:
        log.exception("trace not stored: trace=%s", trace_id)


async def write(engine: AsyncEngine, outcome: Outcome) -> None:
    trace = outcome.trace.as_dict()
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO traces (trace_id, session_id_hash, user_id, route, steps, usage, "
            "success) VALUES (:t, :s, :u, :r, CAST(:steps AS json), CAST(:usage AS json), "
            ":ok) ON CONFLICT (trace_id) DO NOTHING"),
            {"t": outcome.trace.trace_id, "s": outcome.session_id_hash, "u": outcome.user_id,
             "r": outcome.route, "steps": json.dumps(
                 {"steps": trace["steps"], "attempts": trace["attempts"]}),
             "usage": json.dumps(outcome.usage), "ok": outcome.success})
        rows = [{"t": outcome.trace.trace_id, "u": outcome.user_id, "rule": d.rule_id,
                 "v": d.rules_version, "a": d.action, "item": (item or None) and item[:ITEM_MAX],
                 "reason": d.reason}
                for d in outcome.decisions for item in (list(d.offending_items) or [None])]
        if rows:
            await conn.execute(text(
                "INSERT INTO gate_decisions (trace_id, user_id, rule_id, rules_version, "
                "action, item, reason) VALUES (:t, :u, :rule, :v, :a, :item, :reason)"), rows)
            await conn.execute(_HIT, [{"rule": rule, "n": n} for rule, n in sorted(
                Counter(d.rule_id for d in outcome.decisions).items())])
