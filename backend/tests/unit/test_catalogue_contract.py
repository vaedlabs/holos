"""The profile pickers' contract (P5.3, Part E #42): what an account saves for each
condition, allergy and diet resolves back to exactly that one."""

from types import SimpleNamespace

import pytest

from app.contracts.generate import catalogue_contract
from app.storage.profile import resolve_profile

pytestmark = pytest.mark.unit
CONTRACT = catalogue_contract()


def _resolved(conditions="", dietary=""):
    medical = SimpleNamespace(conditions=conditions, limitations=None, medications=None,
                              notes=None)
    return resolve_profile(medical, SimpleNamespace(dietary_restrictions=dietary)).profile


@pytest.mark.parametrize("c", CONTRACT["conditions"], ids=lambda c: c["id"])
def test_a_saved_condition_reads_back_as_itself(c):
    assert _resolved(conditions=c["save"]).condition_ids == [c["id"]]


@pytest.mark.parametrize("a", CONTRACT["allergens"], ids=lambda a: a["id"])
def test_a_saved_allergy_reads_back_as_itself(a):
    assert [str(x) for x in _resolved(dietary=a["save"]).allergen_tags] == [a["id"]]


@pytest.mark.parametrize("d", CONTRACT["diets"], ids=lambda d: d["id"])
def test_a_saved_diet_reads_back_as_itself(d):
    assert [str(x) for x in _resolved(dietary=d["save"]).diet_tags] == [d["id"]]


def test_everything_saved_together_reads_back():
    profile = _resolved(", ".join(c["save"] for c in CONTRACT["conditions"]),
                        ", ".join(x["save"] for x in CONTRACT["allergens"] + CONTRACT["diets"]))
    assert sorted(profile.condition_ids) == sorted(c["id"] for c in CONTRACT["conditions"])
    assert len(profile.allergen_tags) == len(CONTRACT["allergens"])
    assert len(profile.diet_tags) == len(CONTRACT["diets"])
