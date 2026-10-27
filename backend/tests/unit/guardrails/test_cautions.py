"""Cautions that name an excluded food stay; lookalike recommendations are still removed
(Part E #30). The kept sentences are real gpt-6-luna replies (Part D, 27 Oct 2026)."""

import pytest

from app.guardrails.gate import gate_text
from app.guardrails.types import Profile

pytestmark = pytest.mark.unit

PEANUT = Profile(allergen_tags=("peanut",))
NUTS = Profile(allergen_tags=("tree_nut",))
MILK = Profile(allergen_tags=("milk",))
NUTS_MILK = Profile(allergen_tags=("tree_nut", "milk"))
GLUTEN = Profile(allergen_tags=("gluten",))
SESAME = Profile(allergen_tags=("sesame",))
EGG = Profile(allergen_tags=("egg",))
JAIN = Profile(diet_tags=("jain",))


@pytest.mark.parametrize(("profile", "text"), [
    # Verb forms
    (JAIN, "It avoids onion, garlic and root vegetables."),
    (GLUTEN, "I’ve avoided wheat-based staples such as roti and naan because of your gluten "
             "allergy."),
    (PEANUT, "I left out peanut-based chutneys and groundnut oil because of your peanut "
             "allergy."),
    (EGG, "I’ve left out egg-based foods because of your egg allergy."),
    # Lists
    (JAIN, "Avoid onion, garlic, and root vegetables."),
    (JAIN, "Use no onion, garlic, or root vegetables to follow Jain preferences."),
    (NUTS_MILK, "Skip the usual ghee and cashew garnish because of your milk and tree-nut "
                "allergies."),
    (NUTS_MILK, "Avoided milk and tree nuts to respect your allergies; check ingredient labels "
                "and prevent cross-contact."),
    # Cross-contact and labels
    (NUTS_MILK, "Check ingredient labels and avoid cross-contact with milk and tree nuts."),
    (GLUTEN, "Check ingredient labels and avoid cross-contact with wheat, barley, or rye."),
    (PEANUT, "Check labels and preparation for peanut cross-contact."),
    (PEANUT, "Use no peanuts or groundnut oil, and check spice mixes for peanut cross-contact."),
    (PEANUT, "For packaged foods, check allergen statements and watch for cross-contact with "
             "peanuts."),
    (SESAME, "Check spices and oil for sesame or cross-contact."),
    (NUTS, "Check packaged spices and ingredients for tree-nut cross-contact if your allergy is "
           "severe."),
    # Hinglish
    (PEANUT, "Vegetable oil use karein; peanut ya groundnut oil se bachein."),
    (PEANUT, "Peanut allergy ke chalte peanut ya groundnut oil na use karein; doosra tel lein."),
])
def test_a_caution_that_names_the_food_stays(profile, text):
    result = gate_text(text, profile)
    assert result.content == text
    assert result.action == "allow"


@pytest.mark.parametrize(("profile", "text"), [
    # "check ... for" only when what is checked is a label or an ingredient
    (PEANUT, "Check out this recipe for peanut chutney."),
    (PEANUT, "Check the recipe for peanut chutney."),
    (PEANUT, "Check labels for peanuts, then add peanut butter."),
    # A comma alone is not a list
    (JAIN, "Without onion, garlic adds the flavour."),
    (JAIN, "No onion needed and garlic works well."),
    # A reset ends the negation, inside a list too
    (PEANUT, "Avoid sugar and add peanuts for crunch."),
    (JAIN, "Skip the onion but add garlic."),
    (PEANUT, "Skip the rice and have peanut chutney."),
    # A plain list recommends every food in it
    (NUTS, "Add a handful of almonds and cashews."),
    (JAIN, "Cook with onion, garlic and ginger."),
    # English post-cues never reach back along a list
    (PEANUT, "Have peanut chutney and nut-free cookies."),
    # The allergy word must follow the food directly
    (PEANUT, "Peanut butter toast suits your allergy plan."),
    # A negator before a warning cue flips it
    (PEANUT, "There's no need to watch for peanuts in this one."),
    (PEANUT, "Don't check labels for peanuts, they're fine."),
    # Hindi verbs reach back only along a real list
    (PEANUT, "Peanut ladoo banao aur sugar nahi."),
    # Examples carry a negation forward, never into a recommendation
    (PEANUT, "Avoid fried snacks; try peanut chikki instead."),
    # Real recommendations (profile-blind replies, 27 Oct 2026)
    (EGG, "Easy snacks: boiled eggs, roasted chickpeas, or curd with seeds."),
    (GLUTEN, "Try a banana with a small bowl of oats about 1–2 hours before your workout."),
    (NUTS, "Ghar par date-and-nut laddoo bana sakte hain: khajoor ko mash karke chopped nuts "
           "aur thode oats ke saath milaayein."),
])
def test_a_lookalike_recommendation_is_still_removed(profile, text):
    result = gate_text(text, profile)
    assert result.content == ""
    assert result.action == "block"
