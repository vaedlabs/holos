"""The person's local time (Part E #51): the zone their device sends, the server's clock."""

from datetime import UTC, datetime

import pytest

from app.agents.clock import UTC_ZONE, known_zone, now_note, when_text, zone

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 9, 4, 0, tzinfo=UTC)  # 9:30 am in India, 11 pm on the 8th in New York
INDIA, NEW_YORK = zone("Asia/Kolkata"), zone("America/New_York")


@pytest.mark.parametrize("name", ["Mars/Olympus", "../../etc/passwd", "/etc/localtime",
                                  "asia/kolkata", " Asia/Kolkata", ""])
def test_only_names_the_server_knows_are_zones(name):
    assert not known_zone(name)


def test_no_zone_is_utc_and_an_unknown_one_is_an_error():
    assert zone(None) is UTC_ZONE and zone("") is UTC_ZONE
    with pytest.raises(KeyError):
        zone("Mars/Olympus")


def test_the_coach_hears_the_persons_own_day():
    assert now_note(INDIA, NOW) == "It's Monday 9 Nov 2026, 9:30 am for this person."
    assert now_note(NEW_YORK, NOW) == "It's Sunday 8 Nov 2026, 11:00 pm for this person."


@pytest.mark.parametrize(("at", "tz", "text"), [
    (NOW, INDIA, "9:30 am"),
    (datetime(2026, 11, 8, 18, 30, tzinfo=UTC), INDIA, "12:00 am"),  # India's midnight
    (datetime(2026, 11, 8, 18, 29, tzinfo=UTC), INDIA, "yesterday, 11:59 pm"),
    (datetime(2026, 11, 8, 17, 0, tzinfo=UTC), NEW_YORK, "12:00 pm"),  # still the 8th there
    (datetime(2026, 11, 3, 7, 30, tzinfo=UTC), INDIA, "Tue 3 Nov, 1:00 pm"),
    (datetime(2025, 12, 31, 7, 30, tzinfo=UTC), INDIA, "Wed 31 Dec 2025, 1:00 pm"),
])
def test_when_an_entry_happened_reads_in_the_persons_zone(at, tz, text):
    assert when_text(at, tz, NOW) == text


def test_a_clock_change_day_keeps_the_local_time():
    # New York left daylight time on 1 Nov 2026: 9 am local was 13:00 UTC before, 14:00 after
    now = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
    assert when_text(datetime(2026, 10, 31, 13, 0, tzinfo=UTC), NEW_YORK, now) == (
        "Sat 31 Oct, 9:00 am")
    assert when_text(datetime(2026, 11, 1, 14, 0, tzinfo=UTC), NEW_YORK, now) == (
        "yesterday, 9:00 am")
