"""An account's saved profile text resolves to what the gate checks (Plan C.8, P4.7)."""

from types import SimpleNamespace as Row

import pytest

from app.agents.schemas import UserProfile
from app.guardrails import loader
from app.guardrails.loader import GuardrailsError, load_guardrails
from app.storage.profile import phrases, resolve_profile, unchecked_caveat, with_note_terms

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
    assert resolve_profile(_medical(conditions=text), None).profile.condition_ids == ids


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
    profile = resolve_profile(None, _diet(text)).profile
    assert ([str(a) for a in profile.allergen_tags], [str(d) for d in profile.diet_tags]) == (
        allergens, diets)


def test_unchecked_health_text_gets_the_caveat_and_free_notes_do_not():
    resolved = resolve_profile(_medical(conditions="torn ACL, bad shoulder from cricket",
                                        medications="metformin",
                                        notes="Recovering from a slipped disc"),
                               _diet("low salt, peanuts"))
    profile = resolved.profile
    # The note's own words still count where they name something
    assert profile.condition_ids == ["knee_ligament_injury", "lower_back_injury"]
    # The coaches read all of it
    assert profile.notes == ("bad shoulder from cricket; low salt; medications: metformin; "
                             "Recovering from a slipped disc")
    # The caveat names only health text the gate can't check (Part E #42)
    assert unchecked_caveat(resolved.unchecked) == (
        "We couldn't check this note: 'bad shoulder from cricket; low salt; medications: "
        "metformin'")


@pytest.mark.parametrize("notes", [
    "very little free time", "walks in the morning", "hostel mess food, no kitchen",
    "coeliac",  # understood: gluten, so nothing is unchecked
])
def test_free_notes_never_bring_the_caveat(notes):
    resolved = resolve_profile(_medical(conditions="asthma", notes=notes), None)
    assert resolved.unchecked == () and unchecked_caveat(resolved.unchecked) is None
    assert notes in resolved.profile.notes


def test_a_free_note_that_names_something_still_counts():
    assert [str(a) for a in resolve_profile(_medical(notes="coeliac"), None)
            .profile.allergen_tags] == ["gluten"]


def test_a_guests_notes_add_to_their_tags_without_a_caveat():
    guest = UserProfile(condition_ids=["asthma"], allergen_tags=[], diet_tags=[],
                        notes="torn ACL last year, pure veg, busy mornings")
    profile = with_note_terms(guest)
    assert profile.condition_ids == ["asthma", "knee_ligament_injury"]
    assert [str(d) for d in profile.diet_tags] == ["vegetarian"]
    assert profile.notes == guest.notes
    assert with_note_terms(None) is None


def test_long_unchecked_text_is_cut_for_the_caveat_and_the_profile():
    resolved = resolve_profile(_medical(conditions="x" * 3000), None)
    assert len(resolved.profile.notes) == 1000
    caveat = unchecked_caveat(resolved.unchecked)
    assert len(caveat) < 260 and caveat.endswith("…'")


def test_empty_and_missing_text():
    assert phrases(None) == phrases("  ") == []
    resolved = resolve_profile(None, None)
    profile = resolved.profile
    assert (profile.condition_ids, profile.allergen_tags, profile.notes) == ([], [], "")
    assert resolved.unchecked == ()


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
