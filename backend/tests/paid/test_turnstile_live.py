"""Cloudflare's real siteverify answers its published test secrets the way the fake in
tests/integration/test_sessions.py assumes (Plan Part D). Free, but it uses the
network, so it runs with the paid set: nightly or by hand.

    cd backend && pytest -m paid tests/paid/test_turnstile_live.py
"""

import httpx
import pytest

from app.orchestration.sessions import Turnstile
from app.routers.errors import ApiError

pytestmark = [pytest.mark.paid, pytest.mark.asyncio]

TOKEN = "XXXX.DUMMY.TOKEN.XXXX"


@pytest.mark.parametrize(("secret", "passes"), [
    ("1x0000000000000000000000000000000AA", True),
    ("2x0000000000000000000000000000000AA", False),
    ("3x0000000000000000000000000000000AA", False),  # "token already spent"
])
async def test_test_secrets_behave_as_documented(secret, passes):
    async with httpx.AsyncClient() as client:
        assert await Turnstile(client).verify(TOKEN, secret, "203.0.113.7") is passes


async def test_a_wrong_secret_is_a_deployment_error():
    # Cloudflare answers HTTP 400 invalid-input-secret; the server fails closed with 503
    async with httpx.AsyncClient() as client:
        with pytest.raises(ApiError) as exc:
            await Turnstile(client).verify(TOKEN, "not-a-real-secret", "203.0.113.7")
    assert exc.value.status == 503


async def test_an_unreachable_endpoint_fails_closed(monkeypatch):
    from app.orchestration import sessions

    monkeypatch.setattr(sessions, "SITEVERIFY_URL", "https://127.0.0.1:9/siteverify")
    async with httpx.AsyncClient() as client:
        with pytest.raises(ApiError) as exc:
            await Turnstile(client).verify(TOKEN, "1x0000000000000000000000000000000AA", "")
    assert exc.value.status == 503
