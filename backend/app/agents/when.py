"""When a logged entry happened (Part E #51 step 2), worked out by the server.

    resolved = resolve(args.when, meal, said, tz)   # Resolved(at, guessed)
    # NotLoggable: ahead of now, or more than 30 days back (owner: nothing is staged)

The coach copies what the person said into fixed choices (`When`); the date arithmetic
is here, in the person's zone, so a model never does it. Owner's rules (9 Nov 2026):

- Nothing said about when: now. A meal outside its usual hours ("breakfast" at 8 pm)
  gets its usual time instead.
- A clock time: that time. "At 7" with no am or pm is the latest 7 o'clock that has
  passed today; on another day, the more likely one, as a guess.
- No clock time (a day, a part of it, or a meal out of hours): the usual time, marked
  as a guess, so the entry waits on the card for the person to pick the time (owner, B).
  Usual times: breakfast 8:00, lunch 13:00, dinner 20:00, whatever part of the day is
  named; otherwise a part of the day its middle (morning 9:00, afternoon 15:00, evening
  18:30, night 21:30), else a snack 16:30 and anything else noon. Today's guess is never
  later than now.
- Ahead of now (5 minutes' allowance) or more than 30 days back: not logged (owner, B).
- A local time a clock change skips or repeats: Python's first reading (fold 0), so
  2:30 on a spring-forward night is 3:30, and a repeated 1:30 is the first one.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.agents.schemas import WEEKDAYS, When
from app.config import limits

USUAL = {"breakfast": time(8), "lunch": time(13), "snack": time(16, 30), "dinner": time(20)}
PART = {"morning": time(9), "afternoon": time(15), "evening": time(18, 30),
        "night": time(21, 30)}
# A meal said with no time is now while now is within these hours (dinner runs past
# midnight); a snack is any time
MEAL_HOURS = {"breakfast": (4, 11), "lunch": (11, 16), "dinner": (17, 26)}
AHEAD = ("Entries can't be logged ahead of time, only something already done or eaten. "
         "Nothing was staged: tell the person, and that they can log it once it's done.")
TOO_OLD = (f"That is more than {limits.LOG_DATE_BACK.days} days ago, and entries can only "
           "be logged up to then. Nothing was staged: tell the person.")
NOT_A_DATE = "That date doesn't exist. Nothing was staged: ask the person which day."


class NotLoggable(Exception):
    """The time is ahead of now or too far back: nothing is staged. str() is for the
    coach."""


@dataclass(frozen=True)
class Resolved:
    at: datetime  # UTC
    guessed: bool  # no time was given: the person picks it on the card


def resolve(when: When, meal: str | None, said: datetime, tz: ZoneInfo) -> Resolved:
    now = said.astimezone(tz)
    if when.day in (None, "today") and when.time is None and when.part is None:
        if meal is None or meal == "snack" or _in_hours(meal, now):
            return Resolved(said, guessed=False)
        usual = _local(now.date(), USUAL[meal], tz)
        if usual > said:  # breakfast said before it's usual today: yesterday's
            usual = _local(now.date() - timedelta(days=1), USUAL[meal], tz)
        return _checked(usual, True, said)
    day = _day(when.day or "today", now.date())
    if when.time is None:
        at = _local(day, _usual(meal, when.part), tz)
        if day == now.date():
            at = min(at, said)
        return _checked(at, True, said)
    hour, minute = (int(n) for n in when.time.split(":"))
    if when.ampm is not None:
        hour = hour % 12 + (12 if when.ampm == "pm" else 0)
        return _checked(_local(day, time(hour, minute), tz), False, said)
    if hour == 0 or hour > 12:  # a 24-hour clock time says which
        return _checked(_local(day, time(hour, minute), tz), False, said)
    am, pm = (_local(day, time(hour % 12 + half, minute), tz) for half in (0, 12))
    if when.part is not None:
        return _checked(am if when.part == "morning" else pm, False, said)
    if day == now.date():  # the latest that has passed; neither: ahead of now
        return _checked(pm if pm <= said else am, False, said)
    return _checked(_likelier(am, pm, meal, tz), True, said)


def _usual(meal: str | None, part: str | None) -> time:
    """A main meal keeps its usual time ("Saturday's breakfast", "kal raat ka dinner");
    a part of the day places anything else."""
    if meal in USUAL and meal != "snack":
        return USUAL[meal]
    if part is not None:
        return PART[part]
    return USUAL.get(meal, time(12))


def _in_hours(meal: str, now: datetime) -> bool:
    start, end = MEAL_HOURS[meal]
    hour = now.hour if now.hour >= start else now.hour + 24
    return start <= hour < end


def _day(text: str, today: date) -> date:
    if text == "today":
        return today
    if text == "yesterday":
        return today - timedelta(days=1)
    if text == "tomorrow":  # ahead of now: not logged
        return today + timedelta(days=1)
    if text in WEEKDAYS:  # the last one before today
        return today - timedelta(days=(today.weekday() - WEEKDAYS.index(text) - 1) % 7 + 1)
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise NotLoggable(NOT_A_DATE) from None


def _local(day: date, at: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, at, tzinfo=tz).astimezone(UTC)


def _likelier(am: datetime, pm: datetime, meal: str | None, tz: ZoneInfo) -> datetime:
    """"Yesterday at 7", no am or pm: the one nearer the meal's usual time; for an
    activity, morning hours (5 to 11) are am."""
    local_am = am.astimezone(tz)
    if meal is None:
        return am if 5 <= local_am.hour <= 11 else pm
    usual = datetime.combine(local_am.date(), USUAL[meal], tzinfo=tz).astimezone(UTC)
    return min((am, pm), key=lambda t: abs(t - usual))


def _checked(at: datetime, guessed: bool, said: datetime) -> Resolved:
    if at > said + limits.LOG_DATE_AHEAD:
        raise NotLoggable(AHEAD)
    if at < said - limits.LOG_DATE_BACK:
        raise NotLoggable(TOO_OLD)
    return Resolved(at, guessed)
