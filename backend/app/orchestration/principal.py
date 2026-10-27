"""Who is asking: cookie → session → principal; the client IP and its key; CSRF (Plan C.6).

    principal = await resolve_principal(request, store, settings)   # None: no live session
    check_csrf(request, principal, settings)                        # state-changing requests

A principal is an account (`user:{id}`) or a guest session (`session:{hash}`).
Guests are also counted by IP key, so opening more sessions doesn't buy more.
The IP key never stores the address: it is HMAC(daily salt, address), with IPv6
cut to its /64, because one home or phone can move freely inside its /64.
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, date, datetime
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

from fastapi import Request

from app.config.settings import Settings
from app.data.state_store import SessionInfo, StateStore
from app.routers.errors import ApiError

from .cloudflare_ips import CLOUDFLARE_RANGES

CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


# --- Client IP and IP key ---


def _parse(value: str | None) -> IPv4Address | IPv6Address | None:
    try:
        ip = ip_address((value or "").strip())
    except ValueError:
        return None
    if isinstance(ip, IPv6Address) and ip.ipv4_mapped:  # ::ffff:1.2.3.4 is 1.2.3.4
        return ip.ipv4_mapped
    return ip


def client_ip(request: Request, settings: Settings) -> str:
    """The visitor's address. A forwarded header counts only from the trusted proxy:
    CF-Connecting-IP when the connection comes from Cloudflare's own ranges."""
    peer_text = request.client.host if request.client else ""
    peer = _parse(peer_text)
    if settings.trusted_proxy == "cloudflare" and peer is not None and any(
        peer in network for network in CLOUDFLARE_RANGES
    ):
        forwarded = _parse(request.headers.get("cf-connecting-ip"))
        if forwarded is not None:
            return str(forwarded)
    return str(peer) if peer is not None else peer_text


def _daily_salt(settings: Settings, day: date) -> bytes:
    return hmac.new(settings.ip_salt_secret, day.isoformat().encode(), hashlib.sha256).digest()


def ip_key(ip: str, settings: Settings, day: date | None = None) -> str:
    """HMAC(daily salt, address or IPv6 /64). The salt rotates at 00:00 UTC."""
    parsed = _parse(ip)
    if isinstance(parsed, IPv6Address):
        subject = str(ip_network(f"{parsed}/64", strict=False))
    else:
        subject = str(parsed) if parsed is not None else ip
    day = day or datetime.now(UTC).date()
    return hmac.new(_daily_salt(settings, day), subject.encode(), hashlib.sha256).hexdigest()


# Counter keys shared with admission (P4.3), which counts every guest request per IP key
def ip_requests_key(key: str) -> str:
    return f"ip:{key}:requests"


def ip_new_sessions_key(key: str) -> str:
    return f"ip:{key}:new_sessions"


# Login limits (C.12, Part E #25): attempts per IP key, failures per account
def login_ip_key(key: str) -> str:
    return f"login:ip:{key}"


def login_account_key(email: str, settings: Settings) -> str:
    """Keyed by the email typed, known account or not, and never stored in clear."""
    digest = hmac.new(settings.ip_salt_secret, b"login:" + email.encode(), hashlib.sha256)
    return f"login:account:{digest.hexdigest()}"


# --- Principal ---


@dataclass(frozen=True)
class Principal:
    session: SessionInfo
    raw_session_id: str  # the cookie value: the CSRF token is derived from it
    ip_key: str  # of this request, not of the session's start

    @property
    def mode(self) -> str:
        return self.session.mode

    @property
    def user_id(self) -> int | None:
        return self.session.user_id

    @property
    def principal_key(self) -> str:
        """Leases, flags and caps (C.13)."""
        if self.session.user_id is not None:
            return f"user:{self.session.user_id}"
        return f"session:{self.session.id_hash}"

    @property
    def fairness_key(self) -> str:
        """LLM slots (C.9): a guest is the session and its IP together."""
        if self.session.user_id is not None:
            return f"user:{self.session.user_id}"
        return f"guest:{self.session.id_hash}:{self.ip_key}"


async def resolve_principal(
    request: Request, store: StateStore, settings: Settings
) -> Principal | None:
    raw = request.cookies.get(settings.session_cookie)
    if not raw or len(raw) > 128:
        return None
    session = await store.touch_session(raw)
    if session is None:
        return None
    return Principal(session, raw, ip_key(client_ip(request, settings), settings))


# --- CSRF (C.6) ---


def csrf_token(raw_session_id: str, settings: Settings) -> str:
    """HMAC-SHA256(SESSION_SECRET, session ID): no lookup needed to check it."""
    return hmac.new(settings.session_secret, raw_session_id.encode(), hashlib.sha256).hexdigest()


def check_origin(request: Request, settings: Settings) -> None:
    """A state-changing request must come from the app's own origin."""
    if request.headers.get("origin") != settings.app_origin:
        raise ApiError(403, "bad_origin", "This request must come from the Holos app.")


def check_csrf(request: Request, principal: Principal, settings: Settings) -> None:
    check_origin(request, settings)
    sent = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(sent.encode(), csrf_token(principal.raw_session_id,
                                                         settings).encode()):
        raise ApiError(403, "bad_csrf", "Your session token is missing or out of date. "
                       "Reload the page and try again.")
