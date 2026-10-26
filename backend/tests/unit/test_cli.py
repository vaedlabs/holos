"""python -m app.cli create-invite prints the link (Plan C.18)."""

from datetime import UTC, datetime

import pytest

from app import cli
from app.config.settings import Settings

pytestmark = pytest.mark.unit


def test_create_invite_prints_the_link(monkeypatch, capsys):
    async def fake(created_by, sessions=None):
        assert created_by == "ved"
        return "tok123", datetime(2026, 11, 2, tzinfo=UTC)

    settings = Settings(session_secret=b"s" * 40, ip_salt_secret=b"i" * 40,
                        app_origin="https://app.example.com", api_origin="https://api.example.com",
                        trusted_proxy="none", turnstile_secret="x",
                        turnstile_interactive_secret="y",
                        environment="test")
    monkeypatch.setattr(cli, "create_invite", fake)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert cli.main(["create-invite", "--by", "ved"]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "https://app.example.com/invite/tok123"  # stdout: only the link
    assert "2026-11-02" in out.err


def test_an_unknown_command_fails():
    with pytest.raises(SystemExit):
        cli.main(["make-coffee"])
