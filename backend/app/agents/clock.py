"""The person's local time (Plan Part E #51, step 1): the server's clock in the time zone
their device sends with each message, never the device's own clock, so a phone with a
wrong clock can't move an entry. No zone means UTC.

    zone("Asia/Kolkata")                 # a ZoneInfo; KeyError for an unknown name
    now_note(tz)                         # "It's Saturday 8 Nov 2026, 8:15 pm for this person."
    when_text(at, tz)                    # "8:15 pm", "yesterday, 1:00 pm", "Mon 3 Nov, 1:00 pm"
"""

from datetime import UTC, datetime, timedelta
from functools import cache
from zoneinfo import ZoneInfo, available_timezones

UTC_ZONE = ZoneInfo("UTC")


@cache
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def known_zone(name: str) -> bool:
    """An IANA name the server knows ("Asia/Kolkata"); never a path or a file."""
    return name in _zones()


def zone(name: str | None) -> ZoneInfo:
    if not name:
        return UTC_ZONE
    if not known_zone(name):
        raise KeyError(name)
    return ZoneInfo(name)


def _time(moment: datetime) -> str:
    return f"{moment.hour % 12 or 12}:{moment.minute:02d} {'am' if moment.hour < 12 else 'pm'}"


def _day(moment: datetime, year: bool) -> str:
    text = f"{moment:%a} {moment.day} {moment:%b}"
    return f"{text} {moment.year}" if year else text


def now_note(tz: ZoneInfo, now: datetime | None = None) -> str:
    """For the coach: what day and time it is where the person is."""
    local = (now or datetime.now(UTC)).astimezone(tz)
    return f"It's {local:%A} {local.day} {local:%b} {local.year}, {_time(local)} for this person."


def when_text(at: datetime, tz: ZoneInfo, now: datetime | None = None) -> str:
    """When an entry happened, as the "Logged" line shows it, in the person's zone."""
    local, today = at.astimezone(tz), (now or datetime.now(UTC)).astimezone(tz).date()
    if local.date() == today:
        return _time(local)
    if local.date() == today - timedelta(days=1):
        return f"yesterday, {_time(local)}"
    return f"{_day(local, year=local.year != today.year)}, {_time(local)}"
