"""Shared by every test: when a turn is said (Part E #51)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.agents.tools import write
from app.orchestration import coordinator


def lunchtime_said() -> datetime:
    """The latest 12:30 UTC that has passed: a turn's time in the tests."""
    now = datetime.now(UTC)
    said = now.replace(hour=12, minute=30, second=0, microsecond=0)
    return said if said <= now else said - timedelta(days=1)


@pytest.fixture(autouse=True)
def lunchtime(monkeypatch) -> datetime:
    """Turns are said at lunchtime (UTC, the zone when none is sent), whatever the time
    the tests run: a meal said outside its usual hours waits for the person to pick its
    time (Part E #51), so the clock mustn't decide what a test sees. Tests of that rule
    give the time themselves."""
    said = lunchtime_said()

    class _Said(datetime):
        @classmethod
        def now(cls, tz=None):
            return said.astimezone(tz) if tz else said.replace(tzinfo=None)

    monkeypatch.setattr(coordinator, "datetime", _Said)
    monkeypatch.setattr(write, "datetime", _Said)
    return said
