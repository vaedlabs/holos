"""The repeat match (Plan C.17, Part E #67): what counts as an entry already logged."""

from datetime import UTC, datetime, timedelta

import pytest

from app.agents.clock import zone
from app.agents.schemas import WRITE_ARGS, StagedWrite
from app.orchestration.repeats import entry_of, guest_logs, same_entry

pytestmark = pytest.mark.unit

AT = datetime(2026, 11, 16, 6, 30, tzinfo=UTC)  # noon in India
INDIA = zone("Asia/Kolkata")


def _meal(meal: str, *names: str):
    foods = [{"day": None, "name": n, "ingredients": ["x"], "allergen_tags": [],
              "diet_tags": [], "portion": "1 bowl", "calories": 100, "note": "",
              "protein_g": None, "carbs_g": None, "fat_g": None} for n in names]
    return StagedWrite(kind="meal", args=WRITE_ARGS["meal"].model_validate(
        {"meal": meal, "foods": foods}))


def _workout(catalogue_id: str, activity: str | None = None):
    return StagedWrite(kind="workout", args=WRITE_ARGS["workout"].model_validate(
        {"catalogue_id": catalogue_id, "activity": activity, "sets": None, "reps": None,
         "duration_s": 1800, "note": ""}))


def _same(new, old, new_at=AT, old_at=AT, tz=INDIA) -> bool:
    return same_entry(entry_of(new, new_at), entry_of(old, old_at), tz)


@pytest.mark.parametrize("new, old, same", [
    (("lunch", "Dal", "Rice"), ("lunch", "Dal"), True),
    (("lunch", "Masala-Chai"), ("lunch", "masala chai"), True),  # folded like the gate
    (("lunch", "Dal"), ("dinner", "Dal"), False),  # the slot matters
    (("lunch", "Dal"), ("lunch", "Rice"), False),  # no food in common
    # Live (Part E #67): one lunch sent twice, the foods split differently
    (("lunch", "Dal, rice and cucumber salad"), ("lunch", "Dal", "Rice", "Cucumber salad"),
     True),
    (("lunch", "Dal chawal aur salad"), ("lunch", "Chawal"), True),
    (("lunch", "दाल-चावल"), ("lunch", "दाल"), True),  # Devanagari vowel signs stay in words
    (("snack", "Chai"), ("snack", "Masala chai"), True),
    # A shared "and" isn't a food
    (("snack", "Chai and biscuits"), ("snack", "Apple and banana"), False),
    (("lunch", "Paneer tikka"), ("lunch", "Chicken tikka"), False),  # one word in common
])
def test_a_meal_is_the_same_slot_that_day_with_a_food_in_common(new, old, same):
    assert _same(_meal(*new), _meal(*old)) is same


def test_a_meals_day_is_the_persons_own():
    """11:30 pm and 12:30 am in India are an hour apart and two days."""
    late = datetime(2026, 11, 15, 18, 0, tzinfo=UTC)  # 11:30 pm in India
    early = late + timedelta(hours=1)  # 12:30 am
    snack = _meal("snack", "Chai")
    assert not _same(snack, snack, early, late)
    assert _same(snack, snack, early, late, tz=zone("Europe/London"))  # one day there


@pytest.mark.parametrize("hours, same", [(0, True), (2, True), (2.01, False), (-2, True),
                                         (-3, False)])
def test_a_workout_is_the_same_catalogue_id_within_2_hours(hours, same):
    run = _workout("running")
    assert _same(run, run, AT + timedelta(hours=hours)) is same


def test_other_activities_differ_by_name():
    archery = _workout("other_activity", "Archery")
    assert _same(archery, _workout("other_activity", "archery"))
    assert not _same(archery, _workout("other_activity", "Salsa class"))
    assert not _same(_workout("running"), _workout("cycling"))


def test_a_guests_unreadable_entries_are_skipped():
    good = {"entry": _workout("running").model_dump(mode="json"), "at": AT.isoformat(),
            "id": "g1"}
    read = guest_logs([good, {"entry": {"kind": "nope"}}, {"at": "x"}])
    assert [g.id for g in read] == ["g1"]
    assert guest_logs(None) == []
