"""Client IP, IP keys and CSRF tokens (Plan C.6)."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.config.settings import Settings
from app.orchestration.principal import client_ip, csrf_token, ip_key

pytestmark = pytest.mark.unit

CF_PEER = "173.245.48.10"  # inside Cloudflare's 173.245.48.0/20
CF_PEER_V6 = "2606:4700::6810:84e5"


def settings(proxy="cloudflare", salt=b"i" * 40) -> Settings:
    return Settings(session_secret=b"s" * 40, ip_salt_secret=salt, app_origin="http://a:3000",
                    api_origin="http://a:8000", trusted_proxy=proxy, turnstile_secret="x",
                    turnstile_interactive_secret="y", environment="test")


def request(peer: str | None, **headers) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=peer) if peer is not None else None,
                           headers={k.replace("_", "-"): v for k, v in headers.items()})


@pytest.mark.parametrize(("peer", "header", "proxy", "expected"), [
    (CF_PEER, "198.51.100.4", "cloudflare", "198.51.100.4"),  # from Cloudflare: trusted
    (CF_PEER_V6, "2001:db8::1", "cloudflare", "2001:db8::1"),
    ("203.0.113.9", "198.51.100.4", "cloudflare", "203.0.113.9"),  # not Cloudflare: ignored
    (CF_PEER, "198.51.100.4", "none", CF_PEER),  # no proxy configured: always the peer
    (CF_PEER, "not-an-ip", "cloudflare", CF_PEER),  # a bad header falls back to the peer
    (CF_PEER, "", "cloudflare", CF_PEER),
    ("::ffff:203.0.113.9", None, "none", "203.0.113.9"),  # IPv4-mapped IPv6 is IPv4
])
def test_client_ip(peer, header, proxy, expected):
    headers = {"cf_connecting_ip": header} if header is not None else {}
    assert client_ip(request(peer, **headers), settings(proxy)) == expected


def test_x_forwarded_for_is_never_trusted():
    # The red-team bypass of the old rate limiter (Part E #9)
    req = request("203.0.113.9", x_forwarded_for="1.2.3.4", x_real_ip="1.2.3.4")
    assert client_ip(req, settings("cloudflare")) == "203.0.113.9"


def test_no_peer_and_a_non_ip_peer():
    assert client_ip(request(None), settings()) == ""
    assert client_ip(request("testclient"), settings()) == "testclient"


def test_ip_key_hides_the_address_and_is_stable_within_a_day():
    day = date(2026, 10, 26)
    key = ip_key("203.0.113.9", settings(), day)
    assert len(key) == 64 and "203" not in key
    assert key == ip_key("203.0.113.9", settings(), day)
    assert key != ip_key("203.0.113.10", settings(), day)


def test_ip_key_rotates_daily_and_with_the_secret():
    a = ip_key("203.0.113.9", settings(), date(2026, 10, 26))
    assert a != ip_key("203.0.113.9", settings(), date(2026, 10, 27))
    assert a != ip_key("203.0.113.9", settings(salt=b"j" * 40), date(2026, 10, 26))


@pytest.mark.parametrize(("same", "ips"), [
    (True, ["2001:db8:1:2::1", "2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:DB8:1:2:0:0:0:1"]),
    (False, ["2001:db8:1:2::1", "2001:db8:1:3::1"]),
    (True, ["203.0.113.9", "::ffff:203.0.113.9"]),
    (False, ["203.0.113.9", "203.0.113.8"]),  # IPv4 is never grouped
])
def test_ipv6_is_keyed_by_its_slash_64(same, ips):
    keys = {ip_key(ip, settings(), date(2026, 10, 26)) for ip in ips}
    assert (len(keys) == 1) is same


def test_csrf_token_is_bound_to_the_session_and_the_secret():
    token = csrf_token("session-a", settings())
    assert len(token) == 64
    assert token == csrf_token("session-a", settings())
    assert token != csrf_token("session-b", settings())
    other = Settings(**{**settings().__dict__, "session_secret": b"t" * 40})
    assert token != csrf_token("session-a", other)


def test_settings_refuse_weak_or_missing_values(monkeypatch):
    from app.config import settings as module

    base = {"SESSION_SECRET": "s" * 40, "IP_SALT_SECRET": "i" * 40,
            "APP_ORIGIN": "http://localhost:3000", "API_ORIGIN": "http://localhost:8000",
            "TRUSTED_PROXY": "none", "TURNSTILE_SECRET_KEY": "x",
            "TURNSTILE_INTERACTIVE_SECRET_KEY": "y"}
    monkeypatch.setattr(module, "load_dotenv", lambda: None)

    def load(**changes):
        for name, value in {**base, **changes}.items():
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)
        return module.load_settings()

    assert load().session_cookie == "holos_session"
    assert load(API_ORIGIN="https://api.x.com").session_cookie == "__Host-holos_session"
    for bad in ({"SESSION_SECRET": "short"}, {"IP_SALT_SECRET": None},
                {"IP_SALT_SECRET": "s" * 40},  # the same as SESSION_SECRET
                {"APP_ORIGIN": "localhost:3000"}, {"APP_ORIGIN": "http://a.com/path"},
                {"TRUSTED_PROXY": "nginx"}, {"TRUSTED_PROXY": "host"},
                {"TURNSTILE_SECRET_KEY": " "}):
        with pytest.raises(module.SettingsError):
            load(**bad)
