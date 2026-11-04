"""Chat requests run as tasks of their own, not of the connection (Plan C.5, Part E #34).

    spawn(run_job(job, services, streams))   # the endpoint returns the live stream
    await drain(timeout)                     # a planned restart: let running ones end

While a request runs, a heartbeat every 5 s marks it alive for reconnects
(`chat_requests.heartbeat_at`) and renews its leases. The lease TTL (60 s, C.13)
bounds how long a dead worker's lease lasts, not how long a request may run (90 s).
"""

import asyncio
import contextlib
import logging
import os
import socket
import uuid

from app.config.limits import REQUEST_DEADLINE_S
from app.data.stream_store import HEARTBEAT_S, RequestEnded, StreamStore
from app.observability.background import record
from app.orchestration.coordinator import ChatJob, run_chat
from app.orchestration.services import Services

log = logging.getLogger(__name__)

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
HARD_LIMIT_S = REQUEST_DEADLINE_S + 5  # every call already ends by the deadline

_running: set[asyncio.Task] = set()
_draining = False


def draining() -> bool:
    return _draining


def running() -> int:
    return len(_running)


def spawn(coro) -> asyncio.Task:
    task = asyncio.get_running_loop().create_task(coro)
    _running.add(task)
    task.add_done_callback(_running.discard)
    return task


async def drain(timeout: float = HARD_LIMIT_S) -> int:
    """Take no new requests and wait for the running ones; how many were still running
    at the timeout."""
    global _draining
    _draining = True
    if _running:
        _, pending = await asyncio.wait(set(_running), timeout=timeout)
        return len(pending)
    return 0


def _reset_for_tests() -> None:
    global _draining
    _draining = False


async def run_job(job: ChatJob, services: Services, streams: StreamStore,
                  contract_version: int) -> None:
    trace_id = job.admitted.trace_id
    c = job.composer
    beat = watch = None
    try:
        await streams.start(trace_id, WORKER_ID)
        beat = asyncio.create_task(_heartbeat(job, streams))
        watch = asyncio.create_task(c.still_working())
        await c.accepted(contract_version)
        try:
            await asyncio.wait_for(run_chat(job, services), HARD_LIMIT_S)
        except TimeoutError:
            log.error("chat request passed its hard limit: trace=%s", trace_id)
            if not c.ended:
                await c.error("unavailable")
    except RequestEnded:
        log.warning("chat request ended elsewhere (interrupted): trace=%s", trace_id)
    except Exception:
        log.exception("chat worker failed: trace=%s cause=bug", trace_id)
        if not c.ended:
            with contextlib.suppress(Exception):
                await c.error("unavailable")
    finally:
        for task in (beat, watch):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await job.admitted.release()
        record(job.store.engine, job.outcome)  # after the response; never delays it


async def _heartbeat(job: ChatJob, streams: StreamStore) -> None:
    trace_id = job.admitted.trace_id
    while True:
        await asyncio.sleep(HEARTBEAT_S)
        try:
            await streams.heartbeat(trace_id)
            await job.store.renew_leases(trace_id)
        except Exception:
            log.warning("heartbeat failed: trace=%s", trace_id, exc_info=True)
