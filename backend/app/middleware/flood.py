"""C.2 stage 1: at most 100 requests per minute per IP key, counted in Postgres so
every process shares one count and a restart doesn't reset it.

Plain ASGI rather than BaseHTTPMiddleware, so streamed responses pass through
untouched. CORS wraps this middleware (main.py), so it answers preflights before
they are counted, and a 429 still carries CORS headers. If the counter can't be
reached the request goes on: the crisis stream (stage 3) needs no database and
must not fail with it, and every later stage that needs the database fails on
its own. The check has its own short deadline, because an unreachable database
(not a refused one) holds a connection attempt for the OS's TCP timeout (75 s
measured on macOS), and after a failure the check is skipped for a few seconds,
so during an outage no request waits for it at all.
"""

import asyncio
import logging
import time
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import limits
from app.config.settings import Settings
from app.data.state_store import StateStore
from app.orchestration.principal import client_ip, ip_key

log = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({"/health"})  # the host's health check calls often, from one IP
CHECK_TIMEOUT_S = 0.5  # a healthy check takes ~2 ms (p95 3 ms on the dev DB)
SKIP_AFTER_FAILURE_S = 5.0
_clock = time.monotonic  # tests move this one, not the event loop's clock


def flood_key(key: str) -> str:
    return f"flood:{key}"


class FloodLimit:
    def __init__(
        self,
        app: ASGIApp,
        store: Callable[[], StateStore],
        settings: Callable[[], Settings],
    ):
        self.app = app
        self._store = store
        self._settings = settings
        self._skip_until = 0.0  # _clock() before which the check is skipped

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        if _clock() < self._skip_until:
            await self.app(scope, receive, send)
            return
        settings = self._settings()
        key = ip_key(client_ip(Request(scope), settings), settings)
        try:
            rate = await asyncio.wait_for(
                self._store().hit_rate(flood_key(key), limits.FLOOD_WINDOW,
                                       limits.FLOOD_REQUESTS_PER_MINUTE),
                CHECK_TIMEOUT_S)
        except Exception as exc:  # includes the timeout
            self._skip_until = _clock() + SKIP_AFTER_FAILURE_S
            log.error("flood counter unavailable, requests let through for %.0f s: %s",
                      SKIP_AFTER_FAILURE_S, type(exc).__name__)
            await self.app(scope, receive, send)
            return
        if not rate.allowed:
            response = JSONResponse(
                {"code": "flood", "message": "Too many requests. Please slow down.",
                 "retry_after": rate.retry_after},
                status_code=429, headers={"Retry-After": str(rate.retry_after)})
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
