"""Sports and "other activity" (catalogue version 6, rules version 5; owner, 9 Nov 2026,
Part E #53): the coach logs a sport by its catalogue entry, checked like any exercise,
and anything else in the person's words, marked as not checked and never in a plan."""

import pytest
from pydantic import ValidationError

from app.agents.display import item_display
from app.agents.prefix import prefix
from app.agents.schemas import ExerciseItem, LogWorkoutArgs
from app.guardrails.gate import UNCHECKED_RULE, gate, gate_text
from app.guardrails.loader import get_guardrails
from app.guardrails.matcher import get_matcher
from app.guardrails.types import OTHER_ACTIVITY, Profile

from .test_gate import exercise, physical

pytestmark = pytest.mark.unit

PREGNANT = Profile(condition_ids=("pregnancy",))
BONES = Profile(condition_ids=("osteoporosis",))
NECK = Profile(condition_ids=("neck_injury",))
BACK = Profile(condition_ids=("back_pain",))
NONE = Profile()

SPORTS = ["badminton", "tennis", "table_tennis", "squash", "pickleball", "padel", "cricket",
          "football", "basketball", "volleyball", "kabaddi", "kho_kho", "field_hockey",
          "rugby", "american_football", "baseball", "handball", "ultimate_frisbee", "boxing",
          "kickboxing", "martial_arts", "wrestling", "golf", "climbing", "skating", "skiing",
          "surfing", "kayaking", "horse_riding"]


def test_the_owners_list_is_in_the_catalogue():
    ids = set(get_guardrails().catalogue.exercise_ids)
    assert set(SPORTS) <= ids and OTHER_ACTIVITY not in ids


@pytest.mark.parametrize(("words", "cid"), [
    ("ping pong", "table_tennis"), ("soccer", "football"), ("kushti", "wrestling"),
    ("karate", "martial_arts"), ("bouldering", "climbing"), ("gully cricket", "cricket"),
    ("muay thai", "kickboxing"), ("horseback riding", "horse_riding"),
    ("a squash game", "squash"), ("a surf session", "surfing"),
])
def test_the_words_people_use_find_the_sport(words, cid):
    [mention] = get_matcher().find(words)
    assert mention.entry.key == cid


@pytest.mark.parametrize(("profile", "text"), [
    (Profile(condition_ids=("knee_ligament_injury",)),
     "Roasted squash with dal makes a good dinner."),
    (PREGNANT, "Stop surfing your phone an hour before bed."),
])
def test_everyday_words_are_not_the_sport(profile, text):
    """The vegetable and web surfing: a sport's name is also matched in replies."""
    assert gate_text(text, profile).content == text


# --- Rules: contact and fall risk ---


@pytest.mark.parametrize(("profile", "cid", "rule"), [
    (PREGNANT, "kabaddi", "EX-PREG-05"), (PREGNANT, "football", "EX-PREG-05"),
    (PREGNANT, "skating", "EX-PREG-06"), (PREGNANT, "horse_riding", "EX-PREG-06"),
    (BONES, "climbing", "EX-BONE-06"), (BONES, "skiing", "EX-BONE-06"),
])
def test_contact_or_falls_are_left_out_of_a_plan(profile, cid, rule):
    result = gate("physical", physical(cid), profile)
    assert result.blocked_items == [0]
    assert rule in {d.rule_id for d in result.decisions if d.action == "block"}


@pytest.mark.parametrize(("profile", "cid", "rule"), [
    (NECK, "football", "EX-NECK-03"), (BACK, "basketball", "EX-BACK-06"),
])
def test_contact_with_a_neck_or_back_problem_is_a_caution(profile, cid, rule):
    result = gate("physical", physical(cid), profile)
    assert result.blocked_items == [] and result.items[0].action == "warn"
    assert rule in {d.rule_id for d in result.decisions if d.action == "warn"}


def test_a_safe_sport_passes_and_a_logged_one_is_held_with_its_warning():
    assert gate("physical", physical("table_tennis"), PREGNANT).action == "allow"
    logged = gate("physical", {"catalogue_id": "kabaddi", "sets": None, "reps": None,
                               "duration_s": 1800, "note": ""}, PREGNANT)
    assert ("EX-PREG-05", ("contact",)) in logged.items[0].attributes


# --- Long sessions ---


def _log(cid, seconds, activity=None) -> LogWorkoutArgs:
    return LogWorkoutArgs(catalogue_id=cid, activity=activity, sets=None, reps=None,
                          duration_s=seconds, note="")


@pytest.mark.parametrize("cid", ["cricket", "golf", "skiing", "horse_riding"])
def test_a_long_sport_may_run_for_hours(cid):
    assert _log(cid, 4 * 3600).duration_s == 4 * 3600


def test_other_sports_stop_at_90_minutes():
    with pytest.raises(ValidationError):
        _log("badminton", 3 * 3600)


# --- Other activity ---


def test_another_activity_is_named_in_the_persons_words():
    args = _log(OTHER_ACTIVITY, 3600, "  Archery ")
    assert args.activity == "Archery"
    assert item_display(args) == "Archery: 60 min"
    with pytest.raises(ValidationError):
        _log(OTHER_ACTIVITY, 3600, " ")


def test_a_catalogue_entry_keeps_its_own_name():
    assert _log("badminton", 2700, "Shuttle").activity is None


def test_a_plan_never_suggests_another_activity():
    with pytest.raises(ValidationError):
        ExerciseItem(**exercise(OTHER_ACTIVITY))


def _other(activity="Archery", note=""):
    return {"catalogue_id": OTHER_ACTIVITY, "activity": activity, "sets": None, "reps": None,
            "duration_s": 3600, "note": note}


def test_with_no_health_condition_it_is_saved_as_it_is():
    result = gate("physical", _other(), NONE)
    assert result.action == "allow" and result.items[0].attributes == ()


def test_with_a_health_condition_it_is_marked_not_checked_but_never_held():
    result = gate("physical", _other(), PREGNANT)
    [verdict] = result.items
    assert verdict.attributes == ((UNCHECKED_RULE, ("Archery",)),)
    assert verdict.caveats == ("Not checked against your health conditions: Archery",)
    assert not result.malformed


def test_its_name_is_checked_like_a_note():
    result = gate("physical", _other("Archery https://evil.example"), NONE)
    assert result.content["activity"] == "Archery"


def test_only_the_exercise_coach_is_told_to_use_it():
    assert ("log it as other_activity with what they did in `activity`, never as the "
            "nearest entry") in prefix("physical")
    assert "other_activity" not in prefix("mental") + prefix("nutrition")
