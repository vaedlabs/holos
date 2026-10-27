"""Start, rotate and end sessions; Turnstile for guests (Plan C.6, C.12).

Guest sessions start only after a Cloudflare Turnstile check. Each IP key may
start 10 per hour. An IP key that has made 60 requests or spent $0.10 in the
current 240-minute window must pass the interactive widget instead (verified with
its own secret), so people behind one shared mobile IP still get in while bots
mostly don't; at 3x either, the IP key is refused until the window ends.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import Request, Response

from app.config import limits
from app.config.settings import Settings
from app.data.state_store import SessionInfo, StateStore
from app.routers.errors import ApiError

from .budget import ip_window_usd
from .principal import client_ip, csrf_token, ip_key, ip_new_sessions_key, ip_requests_key

log = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TIMEOUT_S = 5.0
TURNSTILE_TOKEN_MAX = 2048  # Cloudflare's documented maximum token length
NEW_SESSION_WINDOW = timedelta(hours=1)  # C.12: 10 new guest sessions per IP key per hour


# Error codes that mean our configuration is wrong, whatever the visitor did
CONFIG_ERRORS = frozenset({"missing-input-secret", "invalid-input-secret"})


def _unavailable() -> ApiError:
    return ApiError(503, "turnstile_unavailable",
                    "We couldn't check that you're human. Please try again.", retry_after=5)


class Turnstile:
    """Calls Cloudflare's siteverify. Any failure to get an answer fails closed."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def verify(self, token: str, secret: str, remote_ip: str) -> bool:
        if not token or len(token) > TURNSTILE_TOKEN_MAX:
            return False
        try:
            response = await self._client.post(
                SITEVERIFY_URL,
                data={"secret": secret, "response": token, "remoteip": remote_ip},
                timeout=TURNSTILE_TIMEOUT_S,
            )
            if response.status_code >= 500:
                raise httpx.HTTPStatusError("server error", request=response.request,
                                            response=response)
            # Cloudflare answers a bad secret with HTTP 400 and a JSON body (Part D)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("turnstile siteverify failed: %s", type(exc).__name__)
            raise _unavailable() from None
        if not isinstance(body, dict):
            raise _unavailable()
        codes = body.get("error-codes") or []
        if CONFIG_ERRORS.intersection(codes if isinstance(codes, list) else []):
            # Our secret is wrong or missing: a deployment error, not a failed human check
            log.error("turnstile secret rejected by Cloudflare: %s", codes)
            raise _unavailable()
        if body.get("success") is not True:
            log.info("turnstile refused: %s", codes)
            return False
        return True


def utc_iso(moment: datetime) -> str:
    """API times are UTC, whatever time zone the database connection uses."""
    return moment.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class Started:
    raw_session_id: str
    session: SessionInfo

    def body(self, settings: Settings) -> dict:
        return {"mode": self.session.mode,
                "csrf_token": csrf_token(self.raw_session_id, settings),
                "expires_at": utc_iso(self.session.expires_at)}


def set_session_cookie(response: Response, started: Started, settings: Settings) -> None:
    """HttpOnly, SameSite=Lax, Path=/, no Domain; Secure and __Host- on https (C.6).
    The browser keeps it as long as the session can live; the server decides."""
    max_age = (limits.GUEST_SESSION_TTL if started.session.mode == "guest"
               else limits.ACCOUNT_SESSION_MAX)
    response.set_cookie(settings.session_cookie, started.raw_session_id,
                        max_age=int(max_age.total_seconds()), path="/", httponly=True,
                        secure=settings.secure_cookies, samesite="lax")


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.session_cookie, path="/", httponly=True,
                           secure=settings.secure_cookies, samesite="lax")


async def _end_cookie_session(request: Request, store: StateStore, settings: Settings) -> None:
    """A new session always gets a new ID; the one the browser had stops working."""
    raw = request.cookies.get(settings.session_cookie)
    if raw and len(raw) <= 128:
        await store.end_session(raw)


async def start_guest(
    request: Request, token: str, store: StateStore, turnstile: Turnstile, settings: Settings
) -> Started:
    ip = client_ip(request, settings)
    key = ip_key(ip, settings)
    requests = await store.peek_rate(ip_requests_key(key), limits.GUEST_IP_WINDOW)
    usd = await ip_window_usd(store, key)
    factor = limits.GUEST_IP_HARD_STOP_FACTOR
    if requests >= limits.GUEST_IP_REQUESTS * factor or usd >= limits.GUEST_IP_USD * factor:
        raise ApiError(429, "ip_limit", "Too many requests from your network. "
                       "Please come back later.", retry_after=_window_left())
    if requests >= limits.GUEST_IP_REQUESTS or usd >= limits.GUEST_IP_USD:
        # Escalated: only the interactive widget's token passes, checked with its secret
        if not await turnstile.verify(token, settings.turnstile_interactive_secret, ip):
            raise ApiError(403, "turnstile_interactive", "Please complete the check to "
                           "continue.")
    elif not await turnstile.verify(token, settings.turnstile_secret, ip):
        raise ApiError(403, "turnstile_failed", "We couldn't check that you're human. "
                       "Please try again.")
    rate = await store.hit_rate(ip_new_sessions_key(key), NEW_SESSION_WINDOW,
                                limits.NEW_GUEST_SESSIONS_PER_IP_HOUR)
    if not rate.allowed:
        raise ApiError(429, "too_many_sessions", "Too many new sessions from your network. "
                       "Please try again later.", retry_after=rate.retry_after)
    await _end_cookie_session(request, store, settings)
    raw, session = await store.create_session("guest", key)
    return Started(raw, session)


async def start_account(
    request: Request, user_id: int, store: StateStore, settings: Settings
) -> Started:
    """After a login or an accepted invite. Ends any session the browser already had,
    so a guest session can't be carried into an account (no session fixation)."""
    await _end_cookie_session(request, store, settings)
    raw, session = await store.create_session(
        "account", ip_key(client_ip(request, settings), settings), user_id=user_id)
    return Started(raw, session)


def _window_left() -> int:
    window = int(limits.GUEST_IP_WINDOW.total_seconds())
    now = int(datetime.now().timestamp())
    return window - now % window
