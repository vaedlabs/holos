"""The gate decides allow, warn or block with a rule ID, and cleans prose (Plan C.14)."""

import copy

import pytest

from app.agents.schemas import MentalReply, NutritionReply, PhysicalReply
from app.guardrails.gate import MALFORMED_RULE, UNCHECKED_RULE, gate, gate_text
from app.guardrails.loader import get_guardrails
from app.guardrails.types import Profile

pytestmark = pytest.mark.unit

VERSION = get_guardrails().rules.version

KNEE = Profile(condition_ids=("knee_ligament_injury",))
SHOULDER = Profile(condition_ids=("shoulder_injury",))
ASTHMA = Profile(condition_ids=("asthma",))
NUTS = Profile(allergen_tags=("tree_nut",))
MILK = Profile(allergen_tags=("milk",))
VEGAN = Profile(diet_tags=("vegan",))
VEGETARIAN = Profile(diet_tags=("vegetarian",))
EGGETARIAN = Profile(diet_tags=("eggetarian",))
JAIN = Profile(diet_tags=("jain",))
HALAL = Profile(diet_tags=("halal",))
NONE = Profile()


def exercise(cid: str, note: str = "") -> dict:
    return {"catalogue_id": cid, "sets": 3, "reps": 10, "duration_s": None,
            "intensity": "moderate", "note": note}


def workout(cid: str) -> dict:
    return {"catalogue_id": cid, "sets": 3, "reps": 10, "duration_s": None, "note": ""}


def practice(cid: str, note: str = "") -> dict:
    return {"catalogue_id": cid, "duration_min": 5, "note": note}


def food(name: str, ingredients: list[str], allergens=(), note: str = "") -> dict:
    return {"name": name, "ingredients": ingredients, "allergen_tags": list(allergens),
            "diet_tags": [], "portion": "1 bowl", "calories": None, "note": note}


def reply(items=(), summary="Here you go.", notes=(), kind=None, follow_up=None) -> dict:
    return {"kind": kind or ("plan" if items else "answer"), "summary": summary,
            "items": list(items), "notes": list(notes), "source_ids": [],
            "follow_up": follow_up, "risk_flag": False}


def physical(*cids, **kw) -> dict:
    return reply([exercise(c) for c in cids], **kw)


def meal(*foods, **kw) -> dict:
    return reply(list(foods), **kw)


def rule_ids(result) -> set[str]:
    return {d.rule_id for d in result.decisions}


# --- Items ---


@pytest.mark.parametrize(("cid", "action", "rules"), [
    ("back_squat", "block", {"EX-KNEE-01"}),
    ("split_squat", "block", {"EX-KNEE-01"}),  # Bulgarian split squat is its alias
    ("jump_squat", "block", {"EX-KNEE-01", "EX-KNEE-02"}),
    ("leg_extension", "block", {"EX-KNEE-01"}),  # prescribed for a torn ACL (Part E #16)
    ("box_jump", "block", {"EX-KNEE-01", "EX-KNEE-02"}),
    ("glute_bridge", "allow", set()),
])
def test_knee_ligament_injury(cid, action, rules):
    result = gate("physical", physical(cid), KNEE)
    assert result.items[0].action == action
    assert result.action == action
    assert rule_ids(result) == rules


def test_rules_only_apply_to_the_profile():
    assert gate("physical", physical("back_squat", "jump_squat"), NONE).action == "allow"


def test_items_are_judged_not_removed():
    result = gate("physical", physical("glute_bridge", "back_squat", "plank"), KNEE)
    assert result.blocked_items == [1]
    assert len(result.content["items"]) == 3


def test_unknown_catalogue_id_is_malformed():
    result = gate("physical", physical("glute_bridge", "moon_squat"), KNEE)
    assert result.malformed
    assert result.action == "block"
    assert result.items[1].action == "block"
    assert rule_ids(result) == {MALFORMED_RULE}


def test_a_practice_id_is_not_an_exercise():
    assert gate("physical", physical("box_breathing"), NONE).malformed


def test_breath_holding_with_asthma():
    result = gate("mental", reply([practice("box_breathing"), practice("body_scan")]), ASTHMA)
    assert [v.action for v in result.items] == ["block", "allow"]
    assert rule_ids(result) == {"MN-BREATH-01"}


@pytest.mark.parametrize(("profile", "item", "action", "rules"), [
    # Nut allergy: declared tag, untagged food named by alias, Hindi name
    (NUTS, food("Trail bars", ["oats"], allergens=["tree_nut"]), "block", {"DI-ALG-01"}),
    (NUTS, food("Pasta", ["pasta", "pesto"]), "block", {"DI-ALG-01"}),
    (NUTS, food("Kaju katli", ["sugar"]), "block", {"DI-ALG-01"}),
    (NUTS, food("Rice bowl", ["rice", "kaju"]), "block", {"DI-ALG-01"}),
    (NUTS, food("Dal rice", ["dal", "rice"]), "allow", set()),
    # Longest term wins: these don't contain the shorter allergen term
    (MILK, food("Toast", ["bread", "peanut butter"]), "allow", set()),
    (MILK, food("Smoothie", ["banana", "almond milk"]), "allow", set()),
    (MILK, food("Curry", ["coconut milk", "tofu"]), "allow", set()),
    # Diets
    (VEGAN, food("Dal tadka", ["lentils", "ghee"]), "block", {"DI-VEGAN-01"}),
    (VEGAN, food("Mystery bowl", ["house sauce"], allergens=["milk"]), "block", {"DI-VEGAN-01"}),
    (VEGAN, food("Dal tadka", ["lentils", "oil"]), "allow", set()),
    (JAIN, food("Sabzi", ["okra", "onion"]), "block", {"DI-JAIN-01"}),
    (JAIN, food("Aloo paratha", ["atta"]), "block", {"DI-JAIN-01"}),
    (VEGETARIAN, food("Egg bhurji", ["eggs", "tomato"]), "block", {"DI-VEG-01"}),
    (EGGETARIAN, food("Egg bhurji", ["eggs", "tomato"]), "allow", set()),
    (HALAL, food("Pork chop", ["pork"]), "block", {"DI-HALAL-01", "DI-HALAL-02"}),
    (HALAL, food("Chicken tikka", ["chicken", "curd"]), "warn", {"DI-HALAL-02"}),
    (HALAL, food("Chicken sausage", ["chicken sausage"]), "warn", {"DI-HALAL-02"}),
    # Spices (catalogue version 2): compounded hing has wheat; blends fail closed
    (Profile(allergen_tags=("gluten",)), food("Dal tadka", ["dal", "hing"]), "block",
     {"DI-ALG-01"}),
    (Profile(allergen_tags=("mustard",)), food("Veg curry", ["peas", "curry powder"]), "block",
     {"DI-ALG-01"}),
    (NUTS, food("Kesar kheer", ["rice", "milk", "saffron", "elaichi"]), "allow", set()),
])
def test_food_items(profile, item, action, rules):
    result = gate("nutrition", meal(item), profile)
    assert result.items[0].action == action
    assert rule_ids(result) == rules


def test_halal_meat_gets_a_caveat():
    result = gate("nutrition", meal(food("Chicken tikka", ["chicken"])), HALAL)
    assert result.items[0].caveats == ("Check that the meat or gelatin is halal",)


def test_unknown_ingredient_is_not_checked_for_an_allergic_user():
    item = food("Quorn curry", ["quorn", "tomato"])
    result = gate("nutrition", meal(item), NUTS)
    assert result.items[0].action == "warn"
    assert result.items[0].caveats == ("Not checked against your allergies: quorn",)
    assert rule_ids(result) == {UNCHECKED_RULE}
    # Without an allergy nothing needs checking
    assert gate("nutrition", meal(item), VEGAN).action == "allow"


def test_a_blocked_food_keeps_its_unchecked_caveat():
    result = gate("nutrition", meal(food("Pesto bowl", ["pesto", "quorn"])), NUTS)
    assert result.items[0].action == "block"
    assert rule_ids(result) == {"DI-ALG-01", UNCHECKED_RULE}


# --- Prose ---


@pytest.mark.parametrize(("profile", "text"), [
    (SHOULDER, "Keep an eye on your blood pressure."),  # "press"
    (KNEE, "Have a light brunch first."),  # "run"
    (KNEE, "Avoid squats for now."),
    (KNEE, "No squats today."),
    (KNEE, "Don't do lunges."),
    (KNEE, "Do not do jump squats or lunges."),
    (KNEE, "Avoid deep squats and lunges."),
    (KNEE, "Instead of squats, do glute bridges."),
    (KNEE, "Squats mat karo."),
    (KNEE, "Lunges bilkul nahi."),
    # Warnings seen in real replies (gpt-6-luna, 26 Oct 2026)
    (NUTS, "Make them without nuts and check every ingredient label for tree nuts."),
    (ASTHMA, "Box breathing may not suit you because it includes breath-holds."),
    (NUTS, "If you're allergic to cashews, use seeds."),
    (KNEE, "Jump squats are not recommended with a torn ACL."),
])
def test_prose_that_is_not_a_recommendation_stays(profile, text):
    result = gate_text(text, profile)
    assert result.content == text
    assert result.action == "allow"


@pytest.mark.parametrize(("profile", "text", "rule"), [
    (SHOULDER, "Do a few sets of overhead press.", "EX-SHLD-01"),
    (SHOULDER, "Overhead presses build strength.", "EX-SHLD-01"),  # plural of a name
    (KNEE, "Go for a run after brunch.", "EX-KNEE-01"),
    (KNEE, "Do squats.", "EX-KNEE-01"),
    (KNEE, "Bulgarian split squats build your glutes.", "EX-KNEE-01"),
    (KNEE, "Don't skip squats.", "EX-KNEE-01"),  # two negations
    (KNEE, "Don't forget your lunges.", "EX-KNEE-01"),
    (KNEE, "No exercise beats squats.", "EX-KNEE-01"),
    (KNEE, "Skip squats and do lunges instead.", "EX-KNEE-01"),
    (KNEE, "Avoid running, lunges are fine.", "EX-KNEE-01"),  # negation stops at the comma
    (KNEE, "Squats kyun nahi karte?", "EX-KNEE-01"),  # "why don't you": a suggestion
    (KNEE, "Do squats on a yoga mat.", "EX-KNEE-01"),
    (KNEE, "Lunges are not bad for your knees.", "EX-KNEE-01"),  # no bare post-"not"
    (KNEE, "Squats aren't hard, just go slow.", "EX-KNEE-01"),
    (ASTHMA, "Try box breathing tonight.", "MN-BREATH-01"),
    (NUTS, "Add a handful of cashews.", "DI-ALG-01"),
    (VEGAN, "Try paneer tikka.", "DI-VEGAN-01"),
])
def test_prose_that_recommends_a_blocked_item_is_removed(profile, text, rule):
    result = gate_text(text, profile)
    assert result.content == ""
    assert result.action == "block"
    assert rule in rule_ids(result)


def test_only_the_offending_sentence_is_removed():
    text = "Great question! Squats build strength. Glute bridges are gentle on the knee."
    result = gate("physical", physical(summary=text), KNEE)
    assert result.content["summary"] == "Great question! Glute bridges are gentle on the knee."
    assert result.action == "block"
    assert result.decisions[0].offending_items == ("Bodyweight squat",)


def test_prose_is_cleaned_in_every_field():
    data = reply([exercise("glute_bridge", note="Pair with lunges. Go slow.")],
                 summary="A gentle plan.", notes=["Add squats later.", "Rest well."])
    result = gate("physical", data, KNEE)
    assert result.content["items"][0]["note"] == "Go slow."
    assert result.content["notes"] == ["Rest well."]  # an emptied note is dropped


def test_follow_up_is_cleaned():
    data = reply(kind="clarify", summary="One question first.",
                 follow_up="Can you do jump squats?")
    result = gate("physical", data, KNEE)
    assert result.content["follow_up"] is None
    MentalReply.model_validate({**result.content, "items": []})


def test_a_warn_rule_keeps_the_sentence():
    result = gate_text("Chicken tikka is a good protein source.", HALAL)
    assert result.content == "Chicken tikka is a good protein source."
    assert result.action == "warn"
    assert rule_ids(result) == {"DI-HALAL-02"}


def test_self_harm_text_is_removed_in_any_domain():
    result = gate("nutrition", meal(summary="You could starve yourself for a day. Or not."), NONE)
    assert result.content["summary"] == "Or not."
    assert rule_ids(result) == {"MN-HARM-01"}
    assert result.action == "block"


def test_holistic_summary_checks_every_domain():
    text = "Run daily. Eat cashews. Practise box breathing. Sleep well."
    profile = Profile(condition_ids=("knee_ligament_injury", "asthma"),
                      allergen_tags=("tree_nut",))
    result = gate_text(text, profile)
    assert result.content == "Sleep well."
    assert rule_ids(result) == {"EX-KNEE-01", "EX-KNEE-02", "DI-ALG-01", "MN-BREATH-01"}


# --- Links and write claims ---


@pytest.mark.parametrize(("text", "expected"), [
    ("Read [this guide](https://evil.example/login) first.", "Read this guide first."),
    ("See https://evil.com/x?a=1 for more.", "See for more."),
    ("Details at www.phish.in.", "Details at."),
    ("Visit evil.com/promo today.", "Visit today."),
    ("Mail me at a@b.co today.", "Mail me at today."),
    ("Go to <https://x.org> now.", "Go to now."),
    ("![img](http://x.io/a.png) Nice.", "img Nice."),
])
def test_links_are_removed(text, expected):
    result = gate_text(text, NONE)
    assert result.content == expected
    assert {s.kind for s in result.scrubbed} == {"link"}
    assert result.action == "allow"  # a link isn't a profile rule: no retry


def test_helpline_domain_stays():
    text = "You can also find help at findahelpline.com."
    assert gate_text(text, NONE).content == text


@pytest.mark.parametrize("claim", [
    "I've logged it.", "I have logged your workout.", "Your meal has been saved.",
    "Saved!", "I've added it to your log.", "Maine log kar diya.",
])
def test_write_claims_are_removed(claim):
    result = gate("physical", physical(summary=f"Nice work. {claim} Keep going."), NONE)
    assert result.content["summary"] == "Nice work. Keep going."
    assert [s.kind for s in result.scrubbed] == ["write_claim"]


# --- Writes ---


@pytest.mark.parametrize(("domain", "write", "profile", "action", "rules"), [
    ("physical", workout("back_squat"), KNEE, "block", {"EX-KNEE-01"}),
    ("physical", workout("glute_bridge"), KNEE, "allow", set()),
    ("physical", workout("moon_squat"), KNEE, "block", {MALFORMED_RULE}),
    ("mental", {**practice("box_breathing"), "mood_before": 2, "mood_after": 4}, ASTHMA,
     "block", {"MN-BREATH-01"}),
    ("nutrition", {"meal": "lunch", "foods": [food("Dal", ["dal", "ghee"])]}, VEGAN,
     "block", {"DI-VEGAN-01"}),
    ("nutrition", {"meal": "lunch", "foods": [food("Dal", ["dal", "rice"])]}, VEGAN,
     "allow", set()),
])
def test_writes(domain, write, profile, action, rules):
    result = gate(domain, write, profile)
    assert result.action == action
    assert rule_ids(result) == rules


def test_write_note_is_cleaned():
    write = {"catalogue_id": "plank", "sets": None, "reps": None, "duration_s": 60,
             "note": "Logged! See www.x.com for tips."}
    result = gate("physical", write, NONE)
    assert result.content["note"] == "See for tips."
    assert {s.kind for s in result.scrubbed} == {"link", "write_claim"}


# --- Every result ---


def all_cases() -> list:
    """Fresh data for each test, so one test's mutation can't hide another's."""
    return [
        ("physical", reply([exercise("back_squat", note="Then lunges."), exercise("moon_squat")],
                           summary="Do lunges. See x.com."), KNEE),
        ("mental", reply([practice("box_breathing")], summary="Kill yourself."), ASTHMA),
        ("nutrition", meal(food("Pesto", ["pesto", "quorn"]), food("Chicken", ["chicken"])),
         Profile(allergen_tags=("tree_nut",), diet_tags=("halal",))),
    ]


@pytest.mark.parametrize(("domain", "data", "profile"), all_cases())
def test_every_decision_has_rule_id_and_version(domain, data, profile):
    result = gate(domain, data, profile)
    assert result.decisions
    for decision in result.decisions:
        assert decision.rule_id
        assert decision.rules_version == VERSION
        assert decision.action in ("allow", "warn", "block")
        assert type(decision.action) is str  # plain text, ready for the trace
        assert decision.reason
    for verdict in result.items:
        assert all(d in result.decisions for d in verdict.decisions)


@pytest.mark.parametrize(("domain", "data", "profile"), all_cases())
def test_input_is_not_changed(domain, data, profile):
    before = copy.deepcopy(data)
    gate(domain, data, profile)
    assert data == before


@pytest.mark.parametrize(("domain", "model", "data"), [
    ("physical", PhysicalReply, physical("glute_bridge", summary="Squats! Rest well.",
                                         notes=["Do lunges."])),
    ("nutrition", NutritionReply, meal(food("Dal", ["dal"], note="Try www.x.com."),
                                       summary="I've saved it.")),
    ("mental", MentalReply, reply([practice("body_scan")], summary="Hurt yourself.")),
])
def test_cleaned_reply_still_validates(domain, model, data):
    model.model_validate(data)
    profile = Profile(condition_ids=("knee_ligament_injury",))
    model.model_validate(gate(domain, data, profile).content)


def test_unknown_domain_is_an_error():
    with pytest.raises(ValueError, match="unknown domain"):
        gate("holistic", reply(), NONE)  # type: ignore[arg-type]


# --- Retry (Plan C.10 step 6) ---


@pytest.mark.parametrize(("domain", "data", "profile", "retry"), [
    ("physical", physical("back_squat"), KNEE, True),  # a blocked item
    ("physical", physical("moon_squat"), NONE, True),  # malformed
    ("physical", physical("glute_bridge", summary="Squats help. Rest."), KNEE, False),  # prose
    ("mental", reply(summary="Hurt yourself."), NONE, False),  # self-harm text, removed
    ("nutrition", meal(food("Chicken", ["chicken"])), HALAL, False),  # warn
    ("physical", physical("glute_bridge"), KNEE, False),
])
def test_retry_only_for_blocked_items_or_malformed(domain, data, profile, retry):
    result = gate(domain, data, profile)
    assert result.needs_retry is retry


# --- "Good morning": the greeting or the exercise (Part E #36) ---

BONES = Profile(condition_ids=("osteoporosis",))


@pytest.mark.parametrize("text", [
    "Good morning, Harbhajan! Welcome back.",
    "Good morning!",
    "Good morning Harbhajan, how did you sleep?",
    "Hi Arjun, good morning! Ready for today?",
    "Morning! Good morning to you.",
])
def test_good_morning_as_a_greeting_is_kept(text):
    result = gate_text(text, BONES)
    assert result.action == "allow" and result.content == text


@pytest.mark.parametrize("text", [
    "Do 3 sets of good morning.",
    "Good mornings strengthen the hamstrings.",
    "Good morning with a light bar, 3x10.",
    "Good morning: 3 sets of 8.",
    "Add a barbell good morning to leg day.",
    "Good morning for hamstrings is great.",
])
def test_good_morning_as_the_exercise_is_still_blocked(text):
    result = gate_text(text, BONES)
    assert result.action == "block" and result.content == ""
