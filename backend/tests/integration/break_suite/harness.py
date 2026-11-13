"""The break suite's harness (Part E #59): the real chat path on a real Postgres with
scripted models, every time limit scaled by K so hundreds of runs fit in a push, and
the rules every request must keep whatever fails.

    scale_time(monkeypatch)           every deadline, timeout and speed table times K
    models = Models(router=[...], ...)  one fake per call kind, one shared slot pool
    run = await send(app, me, payload, drop_after=None)
    problems = await broken(engine, models, run, user_id=...)   [] when every rule held
"""

import asyncio
import json
import time
from dataclasses import dataclass, replace

import httpx

from app.agents.mental import MentalAgent
from app.agents.nutrition import NutritionAgent
from app.agents.physical import PhysicalAgent
from app.config.speeds import Speed
from app.data import stream_store
from app.orchestration import composer, coordinator, router, stream, worker
from app.orchestration.principal import csrf_token
from app.orchestration.router import Router
from app.orchestration.services import (
    COACHES,
    READER_OPTIONS,
    ROUTER_OPTIONS,
    SUMMARY_OPTIONS,
    Services,
)
from app.providers import Breakers, FakeProvider, ResilientProvider, Route
from app.providers import resilient as resilient_module
from app.providers.resilient import STALL_FIRST_S, STALL_GAP_S, Backups
from app.providers.scheduler import FairScheduler

from ..test_admission import APP, settings, sql
from ..test_intake import form

K = 0.02  # 90 s → 1.8 s; DB calls (a few ms) stay small against the shortest, 0.1 s

# Every time rule on the chat path, by module (data limits such as a workout's longest
# duration and Retry-After header values are not times to scale)
TIMES = {
    coordinator: ("ROUTING_DEADLINE_S", "AGENT_DEADLINE_S", "REQUEST_DEADLINE_S",
                  "LOGGED_NOTE_S", "READER_S"),
    worker: ("HARD_LIMIT_S", "HEARTBEAT_S"),
    composer: ("STILL_WORKING_S",),
    stream_store: ("DEAD_AFTER_S",),
    stream: ("PING_S",),
    resilient_module: ("TIMEOUT_OVERSHOOT_S", "BASE_DELAY_S", "MAX_DELAY_S"),
    router: ("TIMEOUT_OVERSHOOT_S",),
}
SPEEDS = {coordinator: ("ROUTER", "SUMMARY", "LOGGED_NOTE", "READER")}
COACH_SPEEDS = ("speed", "plan_speed", "photo_speed")


def scaled(speed: Speed) -> Speed:
    return replace(speed, p50=speed.p50 * K, p90=speed.p90 * K, p95=speed.p95 * K,
                   p99=speed.p99 * K,
                   first_p90=None if speed.first_p90 is None else speed.first_p90 * K)


def scale_time(monkeypatch) -> None:
    from app.agents import base

    monkeypatch.setattr(base, "TIMEOUT_OVERSHOOT_S", base.TIMEOUT_OVERSHOOT_S * K)
    for module, names in TIMES.items():
        for name in names:
            monkeypatch.setattr(module, name, getattr(module, name) * K)
    for module, names in SPEEDS.items():
        for name in names:
            monkeypatch.setattr(module, name, scaled(getattr(module, name)))
    for cls in (PhysicalAgent, NutritionAgent, MentalAgent):
        for name in COACH_SPEEDS:
            if getattr(cls, name, None) is not None:
                monkeypatch.setattr(cls, name, scaled(getattr(cls, name)))


class Models:
    """One fake per call kind, as in test_chat, but every call shares one slot pool and
    one backup ledger, so a slot never given back shows after the request."""

    def __init__(self, router=(), physical=(), nutrition=(), mental=(), summary=(),
                 reader=None):
        self.fakes = {name: FakeProvider(list(script), name="openai")
                      for name, script in (("router", router), ("physical", physical),
                                           ("nutrition", nutrition), ("mental", mental),
                                           ("summary", summary), ("reader", reader or ()))}
        self.scheduler = FairScheduler()
        backups = Backups()
        breakers = Breakers()

        def llm(name, options):
            return ResilientProvider(Route(self.fakes[name], options), None, breakers,
                                     scheduler=self.scheduler, backups=backups,
                                     stall_first_s=STALL_FIRST_S * K,
                                     stall_gap_s=STALL_GAP_S * K)

        self.services = Services(
            router=Router(llm("router", ROUTER_OPTIONS)),
            coaches={n: cls(llm(n, cls.options())) for n, cls in COACHES.items()},
            summary=llm("summary", SUMMARY_OPTIONS), search=None,
            breaker=breakers["openai"],
            reader=llm("reader", READER_OPTIONS) if reader is not None else None)


@dataclass
class Run:
    status: int
    events: list[tuple[str, dict]]  # what the person received (all of it unless dropped)
    elapsed: float
    dropped: bool = False


def _parse(body: str) -> list[tuple[str, dict]]:
    out, name = [], None
    for line in body.splitlines():
        if line.startswith("event: "):
            name = line[7:]
        elif line.startswith("data: "):
            try:
                out.append((name, json.loads(line[6:])))
            except json.JSONDecodeError:  # cut mid-event by a dropped connection
                break
    return out


async def send(app, principal, payload, drop_after: int | None = None) -> Run:
    """Post one chat request. drop_after=n: the person's connection goes after n
    events (the phone switches networks); the request must still finish."""
    cfg = settings()
    started = time.monotonic()
    if drop_after is None:
        headers = {"content-type": "multipart/form-data; boundary=holosboundary",
                   "origin": APP, "x-csrf-token": csrf_token(principal.raw_session_id, cfg)}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://testserver", timeout=30) as client:
            r = await client.post("/agents/chat/stream", content=form(payload),
                                  headers=headers,
                                  cookies={cfg.session_cookie: principal.raw_session_id})
        return Run(r.status_code, _parse(r.text), time.monotonic() - started)
    body = form(payload)
    chunks = [{"type": "http.request", "body": body, "more_body": False}]
    disconnect = asyncio.Event()
    received: list[bytes] = []
    status = 0

    async def receive():
        if chunks:
            return chunks.pop(0)
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send_(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message.get("body"):
            received.append(message["body"])
            if len(_parse(b"".join(received).decode())) >= drop_after:
                disconnect.set()

    headers = [(b"content-type", b"multipart/form-data; boundary=holosboundary"),
               (b"content-length", str(len(body)).encode()), (b"origin", APP.encode()),
               (b"x-csrf-token", csrf_token(principal.raw_session_id, cfg).encode()),
               (b"cookie", f"{cfg.session_cookie}={principal.raw_session_id}".encode())]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": "/agents/chat/stream",
             "raw_path": b"/agents/chat/stream", "query_string": b"", "root_path": "",
             "headers": headers, "client": ("203.0.113.7", 5000),
             "server": ("testserver", 80)}
    await asyncio.wait_for(app(scope, receive, send_), 30)
    return Run(status, _parse(b"".join(received).decode()), time.monotonic() - started,
               dropped=disconnect.is_set())


async def settled(limit: float = 10.0) -> bool:
    """Every spawned request has ended."""
    end = time.monotonic() + limit
    while worker.running():
        if time.monotonic() > end:
            return False
        await asyncio.sleep(0.01)
    return True


TERMINAL = ("done", "error")


async def broken(engine, models: Models, run: Run, *, user_id: int | None,
                 bugs: list[str], crisis: bool = False) -> list[str]:
    """Every rule a request keeps, whatever failed on the way; [] when all held.
    `bugs`: the app's ERROR log lines during the run (a caught crash is still a crash).
    A crisis stream isn't saved (C.16): a dropped one has nothing to check here."""
    problems: list[str] = []
    if not await settled():
        problems.append("a request still runs after 10 s (hard limit not kept)")
    if crisis and run.dropped:
        return problems + [f"app error logged: {b}" for b in bugs]
    names = [n for n, _ in run.events]
    trace_ids = {d.get("trace_id") for _, d in run.events}
    if run.status != 200 or not run.events:
        return [*problems, f"status {run.status}, {len(run.events)} events"]
    if len(trace_ids) != 1:
        problems.append(f"events from several traces: {trace_ids}")
    trace_id = run.events[0][1]["trace_id"]
    # What was sent, or for a dropped connection what was kept for the reconnect
    rows = await sql(engine, "SELECT seq, event FROM stream_events WHERE trace_id = :t "
                     "ORDER BY seq", t=trace_id)
    full = [e for _, e in rows] if run.dropped and not crisis else names
    seqs = [s for s, _ in rows] if run.dropped and not crisis else [
        d["seq"] for _, d in run.events]
    if seqs != list(range(len(seqs))):
        problems.append(f"seq not 0..n: {seqs}")
    ends = [i for i, n in enumerate(full) if n in TERMINAL]
    if len(ends) != 1 or ends[0] != len(full) - 1:
        problems.append(f"not exactly one final event, last: {full[-3:]}")
    if not run.dropped and not crisis and [(s, e) for s, e in rows] != list(
            zip(seqs, names, strict=False)):
        problems.append(f"saved events differ from sent: {len(rows)} saved, {len(names)} sent")
    if run.elapsed > worker.HARD_LIMIT_S + 1.0 and not run.dropped:
        problems.append(f"took {run.elapsed:.2f} s, hard limit {worker.HARD_LIMIT_S:.2f} s")
    # The trace, written after the end
    trace = None
    for _ in range(100):
        trace = await sql(engine, "SELECT success FROM traces WHERE trace_id = :t",
                          t=trace_id)
        if trace:
            break
        await asyncio.sleep(0.02)
    if not trace:
        problems.append("no trace stored")
    elif full and full[-1] in TERMINAL:
        events = run.events if not run.dropped else []
        failed = any(n == "section_end" and d.get("error") for n, d in events)
        capped = any(n == "notice" and d.get("code") == "cap_reached" for n, d in events)
        honest = full[-1] == "done" and not failed and not capped
        if not run.dropped and trace[0][0] != honest:
            problems.append(f"trace success={trace[0][0]}, the stream says {honest}")
    # Nothing left held
    if (await sql(engine, "SELECT count(*) FROM inflight_leases"))[0][0]:
        problems.append("a lease was not released")
    for _ in range(50):  # a hold settled from a cancelled call may land just after
        held = (await sql(engine, "SELECT coalesce(sum(reserved_usd), 0), "
                          "coalesce(sum(reserved_credits), 0) FROM spend"))[0]
        if not (held[0] or held[1]):
            break
        await asyncio.sleep(0.02)
    if held[0] or held[1]:
        steps = await sql(engine, "SELECT steps FROM traces WHERE trace_id = :t", t=trace_id)
        calls = [(a["call"], a["role"], a["outcome"]) for a in steps[0][0]["attempts"]
                 ] if steps else []
        problems.append(f"spend still reserved: ${held[0]}, {held[1]} credits; calls {calls}")
    if models.scheduler.in_use():
        problems.append(f"{models.scheduler.in_use()} model slots not given back")
    # Saved exactly when said
    if user_id is not None and not run.dropped:
        said = sum(len(d["writes"]) for n, d in run.events if n == "committed")
        logs = (await sql(engine, "SELECT (SELECT count(*) FROM workout_logs WHERE user_id = :u)"
                          " + (SELECT count(*) FROM nutrition_logs WHERE user_id = :u)"
                          " + (SELECT count(*) FROM mental_fitness_logs WHERE user_id = :u)",
                          u=user_id))[0][0]
        if logs != said:
            problems.append(f"{logs} entries saved, {said} said to be logged")
        waiting = sum(1 for n, _ in run.events if n == "pending_write")
        pending = (await sql(engine, "SELECT count(*) FROM pending_writes WHERE user_id = :u "
                             "AND status = 'pending'", u=user_id))[0][0]
        if pending != waiting:
            problems.append(f"{pending} entries waiting, {waiting} cards sent")
    problems += [f"app error logged: {b}" for b in bugs]
    return problems
