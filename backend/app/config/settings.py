"""Environment settings for sessions, origins and the client IP (Plan B.3, C.6).

Read once at startup. A missing or weak value fails loudly here, not on the
first request.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv

TrustedProxy = Literal["cloudflare", "host", "none"]
MIN_SECRET_BYTES = 32


class SettingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    session_secret: bytes
    ip_salt_secret: bytes
    app_origin: str
    api_origin: str
    trusted_proxy: TrustedProxy
    turnstile_secret: str
    turnstile_interactive_secret: str
    environment: str

    @property
    def secure_cookies(self) -> bool:
        """`Secure` cookies and the `__Host-` prefix need https; local dev runs on http."""
        return self.api_origin.startswith("https://")

    @property
    def session_cookie(self) -> str:
        return "__Host-holos_session" if self.secure_cookies else "holos_session"


def _secret(name: str) -> bytes:
    value = os.getenv(name, "").encode()
    if len(value) < MIN_SECRET_BYTES:
        raise SettingsError(f"{name} must be at least {MIN_SECRET_BYTES} bytes")
    return value


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SettingsError(f"{name} is not set")
    return value


def _origin(name: str) -> str:
    value = _required(name).rstrip("/")
    if not value.startswith(("http://", "https://")) or value.count("/") != 2:
        raise SettingsError(f"{name} must be a scheme and host, like https://app.example.com")
    return value


def load_settings() -> Settings:
    load_dotenv()
    proxy = os.getenv("TRUSTED_PROXY", "none").strip()
    if proxy not in ("cloudflare", "host", "none"):
        raise SettingsError("TRUSTED_PROXY must be cloudflare, host or none")
    if proxy == "host":
        # The host's own client-IP header is decided with the host (Plan P7.1)
        raise SettingsError("TRUSTED_PROXY=host isn't supported until the host is chosen (P7.1)")
    session_secret, ip_salt = _secret("SESSION_SECRET"), _secret("IP_SALT_SECRET")
    if session_secret == ip_salt:
        raise SettingsError("SESSION_SECRET and IP_SALT_SECRET must be different")
    return Settings(
        session_secret=session_secret,
        ip_salt_secret=ip_salt,
        app_origin=_origin("APP_ORIGIN"),
        api_origin=_origin("API_ORIGIN"),
        trusted_proxy=proxy,
        turnstile_secret=_required("TURNSTILE_SECRET_KEY"),
        turnstile_interactive_secret=_required("TURNSTILE_INTERACTIVE_SECRET_KEY"),
        environment=os.getenv("ENVIRONMENT", "development"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
