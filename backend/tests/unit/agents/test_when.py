"""When a logged entry happened (Part E #51 step 2): the coach's fixed choices, resolved
by the server in the person's zone (owner's rules, 9 Nov 2026)."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.agents.clock import zone
from app.agents.schemas import When
from app.agents.when import AHEAD, NOT_A_DATE, TOO_OLD, NotLoggable, resolve

pytestmark = pytest.mark.unit

UTC_ZONE, INDIA, NEW_YORK = zone(None), zone("Asia/Kolkata"), zone("America/New_York")
MONDAY = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)  # Monday 8 pm in UTC


def _when(day=None, time=None, ampm=None, part=None) -> When:
    return When(day=day, time=time, ampm=ampm, part=part)


def _at(said, *args, meal=None, tz=UTC_ZONE, **kw):
    resolved = resolve(_when(*args, **kw), meal, said, tz)
    return resolved.at, resolved.guessed


def _utc(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


# --- Nothing said about when ---


@pytest.mark.parametrize("meal", [None, "snack"])
def test_nothing_said_is_now(meal):
    assert _at(MONDAY, meal=meal) == (MONDAY, False)
    assert _at(MONDAY, "today", meal=meal) == (MONDAY, False)


@pytest.mark.parametrize(("hour", "meal"), [(9, "breakfast"), (13, "lunch"), (20, "dinner"),
                                            (1, "dinner")])  # dinner runs past midnight
def test_a_meal_in_its_hours_is_now(hour, meal):
    said = _utc(9, hour)
    assert _at(said, meal=meal) == (said, False)


def test_a_meal_out_of_its_hours_waits_at_its_usual_time():
    # "poha for breakfast" said at 8 pm: today's breakfast, for the person to check
    assert _at(MONDAY, meal="breakfast") == (_utc(9, 8), True)
    # "dinner" said at 3 pm: last night's
    assert _at(_utc(9, 15), meal="dinner") == (_utc(8, 20), True)


# --- No clock time: the usual time, a guess ---


def test_a_day_without_a_time_is_noon_or_the_meals_usual_time():
    assert _at(MONDAY, "yesterday") == (_utc(8, 12), True)
    assert _at(MONDAY, "yesterday", meal="lunch") == (_utc(8, 13), True)
    assert _at(MONDAY, "yesterday", meal="snack") == (_utc(8, 16, 30), True)


@pytest.mark.parametrize(("part", "hour", "minute"), [("morning", 9, 0), ("afternoon", 15, 0),
                                                      ("evening", 18, 30), ("night", 21, 30)])
def test_a_part_of_the_day_is_its_middle(part, hour, minute):
    assert _at(MONDAY, "yesterday", part=part) == (_utc(8, hour, minute), True)


def test_a_main_meal_keeps_its_usual_time_whatever_the_part_and_a_snack_follows_it():
    # Live, 9 Nov 2026: "breakfast on Saturday" came with part "morning"
    assert _at(MONDAY, "yesterday", part="morning", meal="breakfast") == (_utc(8, 8), True)
    assert _at(MONDAY, "yesterday", part="night", meal="dinner") == (_utc(8, 20), True)
    assert _at(MONDAY, "yesterday", part="morning", meal="snack") == (_utc(8, 9), True)


def test_todays_guess_is_never_later_than_now():
    said = _utc(9, 18, 10)  # "I walked this evening", at 6:10 pm
    assert _at(said, "today", part="evening") == (said, True)
    assert _at(said, part="night") == (said, True)


# --- A clock time ---


def test_a_clock_time_with_am_or_pm_or_on_a_24_hour_clock_is_that_time():
    assert _at(MONDAY, "yesterday", "7:00", "am") == (_utc(8, 7), False)
    assert _at(MONDAY, "yesterday", "7:30", "pm") == (_utc(8, 19, 30), False)
    assert _at(MONDAY, "yesterday", "12:15", "am") == (_utc(8, 0, 15), False)
    assert _at(MONDAY, "today", "19:30") == (_utc(9, 19, 30), False)
    assert _at(MONDAY, "today", "0:30") == (_utc(9, 0, 30), False)


@pytest.mark.parametrize(("said_hour", "hour"), [(20, 19), (8, 7), (12, 0)])
def test_at_7_today_is_the_latest_7_that_has_passed(said_hour, hour):
    said = _utc(9, said_hour)
    if said_hour == 12:  # "at 12:30" at noon: half past midnight
        assert _at(said, None, "12:30") == (_utc(9, 0, 30), False)
    else:
        assert _at(said, None, "7:00") == (_utc(9, hour), False)


def test_a_part_of_the_day_says_am_or_pm():
    assert _at(MONDAY, "yesterday", "9:00", part="evening") == (_utc(8, 21), False)
    assert _at(MONDAY, "yesterday", "9:00", part="morning") == (_utc(8, 9), False)


def test_at_7_on_another_day_is_the_likelier_one_and_a_guess():
    assert _at(MONDAY, "yesterday", "8:00", meal="dinner") == (_utc(8, 20), True)
    assert _at(MONDAY, "yesterday", "8:00", meal="breakfast") == (_utc(8, 8), True)
    assert _at(MONDAY, "yesterday", "6:00") == (_utc(8, 6), True)  # a morning workout
    assert _at(MONDAY, "yesterday", "4:00") == (_utc(8, 16), True)


# --- Days ---


@pytest.mark.parametrize(("day", "date"), [("sunday", 8), ("monday", 2), ("tuesday", 3),
                                           ("2026-11-05", 5)])
def test_a_weekday_is_the_last_one_before_today(day, date):
    assert _at(MONDAY, day, "10:00", "am") == (_utc(date, 10), False)


def test_yesterday_is_the_persons_own_yesterday():
    said = _utc(9, 20)  # Tue 1:30 am in India, Mon 3 pm in New York
    assert _at(said, "yesterday", "10:00", "am", tz=INDIA) == (_utc(9, 4, 30), False)
    assert _at(said, "yesterday", "10:00", "am", tz=NEW_YORK) == (_utc(8, 15), False)


# --- Out of range: nothing is staged (owner, B) ---


@pytest.mark.parametrize(("args", "reason"), [
    (("today", "9:00", "pm"), AHEAD),  # said at 8 pm
    (("tomorrow",), AHEAD),  # live, 9 Nov 2026: written as the weekday, it became last week's
    (("tomorrow", None, None, "morning"), AHEAD),
    (("2026-11-10", "7:00", "am"), AHEAD),
    (("2026-10-09", "7:00", "am"), TOO_OLD),
    (("2026-02-30", "7:00", "am"), NOT_A_DATE),
])
def test_ahead_of_now_or_too_far_back_is_not_logged(args, reason):
    with pytest.raises(NotLoggable) as err:
        _at(MONDAY, *args)
    assert str(err.value) == reason


def test_at_7_said_at_6_is_ahead():
    with pytest.raises(NotLoggable):
        _at(_utc(9, 6), None, "7:00")


def test_a_phone_a_little_ahead_still_logs():
    assert _at(MONDAY, "today", "20:04") == (MONDAY + timedelta(minutes=4), False)


def test_thirty_days_back_is_the_limit():
    assert _at(MONDAY, "2026-10-10", "21:00") == (datetime(2026, 10, 10, 21, tzinfo=UTC), False)


# --- Clock changes (New York, 2026) ---


def test_a_skipped_time_reads_after_the_change_and_a_repeated_one_is_the_first():
    after_spring = datetime(2026, 3, 9, 12, tzinfo=UTC)
    # 2:30 am on 8 Mar doesn't exist: it reads as 3:30 am EDT
    assert _at(after_spring, "yesterday", "2:30", "am", tz=NEW_YORK)[0] == (
        datetime(2026, 3, 8, 7, 30, tzinfo=UTC))
    after_fall = datetime(2026, 11, 2, 12, tzinfo=UTC)
    # 1:30 am on 1 Nov happens twice: the first, still EDT
    assert _at(after_fall, "yesterday", "1:30", "am", tz=NEW_YORK)[0] == (
        datetime(2026, 11, 1, 5, 30, tzinfo=UTC))


# --- The coach's choices are checked when the reply is read ---


@pytest.mark.parametrize("fields", [{"day": "next monday"}, {"day": "last week"},
                                    {"time": "25:00"}, {"time": "7"}, {"time": "7pm"},
                                    {"part": "noon"}, {"ampm": "AM"}])
def test_only_the_fixed_choices_are_read(fields):
    with pytest.raises(ValidationError):
        When(**{"day": None, "time": None, "ampm": None, "part": None, **fields})
