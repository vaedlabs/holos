"""Catalogue and rules version 4 (Part E #38): forward bending of the spine, milk
alternatives, gluten-free versions, flours, and dishes whose name hides an allergen or
a diet conflict."""

import pytest

from app.guardrails.gate import gate
from app.guardrails.matcher import get_matcher
from app.guardrails.types import Profile

pytestmark = pytest.mark.unit

OSTEO = Profile(condition_ids=("osteoporosis",))
BACK_INJURY = Profile(condition_ids=("lower_back_injury",))
BACK_PAIN = Profile(condition_ids=("back_pain",))


def plan(cid: str) -> dict:
    return {"kind": "plan", "summary": "Here you go.", "notes": [], "source_ids": [],
            "follow_up": None, "risk_flag": False,
            "items": [{"catalogue_id": cid, "sets": 3, "reps": 10, "duration_s": None,
                       "intensity": "moderate", "note": ""}]}


def rules(result) -> set[str]:
    return {d.rule_id for d in result.decisions}


@pytest.mark.parametrize(("profile", "cid", "action", "rule"), [
    # Seen live (Part D): sit-ups and crunches reached Linda (osteoporosis) and
    # Ananya (back pain)
    (OSTEO, "sit_up", "block", "EX-BONE-04"),
    (OSTEO, "crunch", "block", "EX-BONE-04"),
    (OSTEO, "bicycle_crunch", "block", "EX-BONE-04"),
    (OSTEO, "v_up", "block", "EX-BONE-04"),
    (OSTEO, "russian_twist", "block", "EX-BONE-04"),
    (OSTEO, "hamstring_stretch", "warn", "EX-BONE-05"),
    (OSTEO, "sun_salutation", "warn", "EX-BONE-05"),
    (BACK_INJURY, "crunch", "block", "EX-BACK-04"),
    (BACK_PAIN, "crunch", "block", "EX-BACK-05"),
    (BACK_PAIN, "sit_up", "block", "EX-BACK-05"),
])
def test_spinal_flexion(profile, cid, action, rule):
    result = gate("physical", plan(cid), profile)
    assert result.items[0].action == action
    assert rule in rules(result)


@pytest.mark.parametrize("cid", ["plank", "bird_dog", "dead_bug", "glute_bridge", "walking"])
def test_a_straight_spine_is_fine_with_osteoporosis(cid):
    result = gate("physical", plan(cid), OSTEO)
    assert not {"EX-BONE-04", "EX-BONE-05"} & rules(result)


def ingredients(text: str) -> dict[str, tuple[set[str], set[str]]]:
    return {e.name: ({a.value for a in e.allergens}, {d.value for d in e.diet_conflicts})
            for e in get_matcher().ingredients(text)}


@pytest.mark.parametrize(("text", "expected"), [
    # False alarms before version 4 (Part D: Sofia, lactose intolerant; Tom, coeliac)
    ("oat milk latte", {"oat milk": ({"gluten"}, set())}),
    ("certified gluten-free oats", {"gluten free oats": (set(), set())}),
    ("lactose-free milk", {"lactose free milk": ({"milk"}, {"animal_product"})}),
    ("cashew milk", {"cashew milk": ({"tree_nut"}, set())}),
    ("rice milk", {"rice milk": (set(), set())}),
    ("plant-based milk", {"plant milk": (set(), set())}),
    ("soy yogurt", {"soy yogurt": ({"soy"}, set())}),
    ("coconut yogurt", {"coconut yogurt": (set(), set())}),
    ("kuttu ka atta", {"buckwheat": (set(), set())}),
    ("rice flour", {"rice flour": (set(), set())}),
    # Unknown before version 4, so never checked
    ("flour", {"flour": ({"gluten"}, set())}),
    ("a croissant", {"pastry": ({"gluten", "milk"}, {"animal_product"})}),
    ("pizza", {"pizza": ({"gluten", "milk"}, {"animal_product"})}),
    ("chocolate cake", {"cake": ({"gluten", "egg", "milk"}, {"animal_product", "egg"})}),
    ("eggless cake", {"eggless cake": ({"gluten", "milk"}, {"animal_product"})}),
    ("cookies", {"biscuits": ({"gluten"}, set())}),
    ("masala dosa", {"masala dosa": (set(), {"root_vegetable"})}),
    ("sambar", {"sambar": ({"gluten"}, set())}),
])
def test_v4_foods(text, expected):
    assert ingredients(text) == expected


def test_a_dish_is_still_read_with_its_other_words():
    # "rava" is semolina: rava dosa keeps its gluten without a dosa entry
    assert "semolina" in ingredients("rava dosa")
    assert ingredients("spelt bread") == {"spelt": ({"gluten"}, set()),
                                          "bread": ({"gluten"}, set())}


def test_a_coeliac_gets_gluten_free_oats_but_not_pizza():
    coeliac = Profile(allergen_tags=("gluten",))
    item = {"kind": "plan", "summary": "Try these.", "notes": [], "source_ids": [],
            "follow_up": None, "risk_flag": False, "items": [
                {"name": "Porridge", "ingredients": ["gluten-free oats", "banana"],
                 "allergen_tags": [], "diet_tags": [], "portion": "1 bowl",
                 "calories": None, "note": ""},
                {"name": "Pizza", "ingredients": ["pizza"], "allergen_tags": [],
                 "diet_tags": [], "portion": "2 slices", "calories": None, "note": ""}]}
    result = gate("nutrition", item, coeliac)
    assert [v.action for v in result.items] == ["allow", "block"]
