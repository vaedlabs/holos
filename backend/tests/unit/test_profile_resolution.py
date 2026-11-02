"""An account's saved profile text resolves to what the gate checks (Plan C.8, P4.7)."""

from types import SimpleNamespace as Row

import pytest

from app.guardrails import loader
from app.guardrails.loader import GuardrailsError, load_guardrails
from app.storage.profile import phrases, resolve_profile, unchecked_caveat

pytestmark = pytest.mark.unit


def _medical(conditions=None, limitations=None, medications=None, notes=None):
    return Row(conditions=conditions, limitations=limitations, medications=medications,
               notes=notes)


def _diet(text):
    return Row(dietary_restrictions=text)


@pytest.mark.parametrize(("text", "ids"), [
    ("torn ACL left knee", ["knee_ligament_injury"]),
    ("Type 2 diabetes and high blood pressure", ["diabetes", "hypertension"]),
    ('["slipped disc", "asthma"]', ["asthma", "lower_back_injury"]),  # the old JSON form
    ("runner's knee; frozen shoulder", ["knee_injury", "shoulder_injury"]),
    ("Pregnant (22 weeks)", ["pregnancy"]),
    ("no back pain", []),  # negated: not a condition, and kept as a note
])
def test_conditions_resolve_through_the_catalogue(text, ids):
    assert resolve_profile(_medical(conditions=text), None).condition_ids == ids


@pytest.mark.parametrize(("text", "allergens", "diets"), [
    ("no dairy, peanuts", ["milk", "peanut"], []),
    ("pure veg", [], ["vegetarian"]),
    ("non-veg", [], []),  # "non" cancels a diet word
    ("coeliac, lactose intolerant", ["gluten"], ["lactose_free"]),
    ("Jain, no root vegetables", [], ["jain"]),
    ("tree nuts and sesame", ["sesame", "tree_nut"], []),
    ("peanuts", ["peanut"], []),  # "nuts" inside "peanuts" is not tree nuts
])
def test_allergies_and_diets_resolve_through_profile_terms(text, allergens, diets):
    profile = resolve_profile(None, _diet(text))
    assert ([str(a) for a in profile.allergen_tags], [str(d) for d in profile.diet_tags]) == (
        allergens, diets)


def test_what_resolves_nothing_becomes_a_note_with_a_caveat():
    profile = resolve_profile(_medical(conditions="torn ACL, bad shoulder from cricket",
                                       medications="metformin",
                                       notes="Recovering from a slipped disc"), None)
    # The note's own words still count where they name something
    assert profile.condition_ids == ["knee_ligament_injury", "lower_back_injury"]
    assert profile.notes == ("bad shoulder from cricket; medications: metformin; "
                             "Recovering from a slipped disc")
    assert unchecked_caveat(profile) == (
        "We couldn't check this note: 'bad shoulder from cricket; medications: metformin; "
        "Recovering from a slipped disc'")
    assert unchecked_caveat(resolve_profile(_medical(conditions="asthma"), None)) is None


def test_long_notes_are_cut_for_the_caveat_and_the_profile():
    profile = resolve_profile(_medical(notes="x" * 3000), None)
    assert len(profile.notes) == 1000
    assert len(unchecked_caveat(profile)) < 260 and unchecked_caveat(profile).endswith("…'")


def test_empty_and_missing_text():
    assert phrases(None) == phrases("  ") == []
    profile = resolve_profile(None, None)
    assert (profile.condition_ids, profile.allergen_tags, profile.notes) == ([], [], "")


# --- The catalogue's profile terms are checked when it loads ---


def test_every_allergy_and_diet_needs_words_and_a_word_means_one_thing(tmp_path):
    source = loader.CATALOGUE_PATH.read_text()
    missing = source.replace("    lupin: [lupin, lupine]\n", "")
    clash = source.replace("    celery: [celery]\n", "    celery: [celery, sesame]\n")
    for text, problem in ((missing, "nothing for 'lupin'"), (clash, "'sesame' means")):
        path = tmp_path / "catalogue.yaml"
        path.write_text(text)
        with pytest.raises(GuardrailsError, match=problem):
            load_guardrails(catalogue_path=path)
