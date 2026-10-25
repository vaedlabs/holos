"""Catalogue and rules load, and broken files fail with a clear message."""

import ast
import copy
from collections import Counter
from pathlib import Path

import pytest
import yaml

from app.guardrails.loader import (
    CATALOGUE_PATH,
    RULES_PATH,
    GuardrailsError,
    load_guardrails,
)
from app.guardrails.normalise import normalise_text
from app.guardrails.types import Severity

pytestmark = pytest.mark.unit

CATALOGUE = yaml.safe_load(CATALOGUE_PATH.read_text(encoding="utf-8"))
RULES = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def guardrails():
    return load_guardrails()


def _load_broken(tmp_path: Path, catalogue=None, rules=None) -> GuardrailsError:
    """Write (possibly edited) copies of both files and expect the load to fail."""
    cat_path, rules_path = tmp_path / "catalogue.yaml", tmp_path / "rules.yaml"
    for path, data, default in ((cat_path, catalogue, CATALOGUE), (rules_path, rules, RULES)):
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_text(yaml.safe_dump(data or default, allow_unicode=True), encoding="utf-8")
    with pytest.raises(GuardrailsError) as exc:
        load_guardrails(cat_path, rules_path)
    return exc.value


# --- The packaged files ---


def test_both_files_load(guardrails):
    assert guardrails.catalogue.version >= 1
    assert guardrails.rules.version >= 1
    assert guardrails.catalogue.exercises and guardrails.catalogue.practices


def test_catalogue_ids_are_unique(guardrails):
    c = guardrails.catalogue
    ids = Counter(c.exercise_ids + c.practice_ids + c.condition_ids)
    assert [i for i, n in ids.items() if n > 1] == []


def test_every_alias_maps_to_one_item(guardrails):
    c = guardrails.catalogue
    terms = Counter(
        normalise_text(term)
        for item in [*c.exercises, *c.practices, *c.conditions, *c.ingredients]
        for term in [item.name, *item.aliases]
    )
    assert [t for t, n in terms.items() if n > 1] == []


def test_every_rule_has_id_reason_and_severity(guardrails):
    r = guardrails.rules
    for rule in [*r.exercise, *r.dietary, *r.mental]:
        assert rule.id and rule.reason.strip()
        assert rule.severity in set(Severity)


def test_rules_refer_to_existing_conditions(guardrails):
    known = set(guardrails.catalogue.condition_ids)
    r = guardrails.rules
    for rule in [*r.exercise, *r.mental]:
        assert set(rule.when.condition or []) <= known, rule.id


def test_plan_required_rules_exist(guardrails):
    """Plan P1.1: knee and ACL block knee_load high; allergies block; breath-holding."""
    by_id = {r.id: r for r in [*guardrails.rules.exercise, *guardrails.rules.dietary,
                               *guardrails.rules.mental]}
    for rule_id in ("EX-KNEE-01", "EX-KNEE-03"):
        assert by_id[rule_id].block == {"knee_load": "high"}
        assert by_id[rule_id].severity == Severity.BLOCK
    assert by_id["DI-ALG-01"].severity == Severity.BLOCK
    assert set(by_id["MN-BREATH-01"].when.condition) == {"heart_condition", "asthma"}


def test_pescatarian_and_lactose_free(guardrails):
    """Owner decision (Part E #8): both diets exist; lactose-free warns, not blocks."""
    by_id = {r.id: r for r in guardrails.rules.dietary}
    assert by_id["DI-PESC-01"].severity == Severity.BLOCK
    assert by_id["DI-LACT-01"].severity == Severity.WARN
    foods = {f.name: set(f.diet_conflicts) for f in guardrails.catalogue.ingredients}
    assert "lactose" in foods["milk"] and "lactose" in foods["curd"]
    # Most lactose-intolerant people eat these, so they must not be flagged
    for name in ("ghee", "butter", "cheese"):
        assert "lactose" not in foods[name]


def test_hindi_ingredient_names_resolve(guardrails):
    """Plan C.14 names ghee, paneer, kaju, badam, moongphali, til, atta, maida, besan."""
    terms = {
        normalise_text(term)
        for food in guardrails.catalogue.ingredients
        for term in [food.name, *food.aliases]
    }
    for name in ("ghee", "paneer", "kaju", "badam", "moongphali", "til", "atta", "maida", "besan"):
        assert name in terms


def test_guardrails_package_has_no_app_imports():
    """Plan C.1: guardrails/ imports nothing from app.* and no LangChain."""
    package = CATALOGUE_PATH.parent
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                assert not name.startswith(("app", "langchain", "langgraph")), (path.name, name)


# --- Broken files fail with a clear message ---


def test_invalid_yaml(tmp_path):
    err = _load_broken(tmp_path, rules="version: 1\nexercise: [unclosed\n")
    assert "rules.yaml: invalid YAML" in str(err)


def test_missing_file(tmp_path):
    with pytest.raises(GuardrailsError, match="catalogue.yaml: file not found"):
        load_guardrails(tmp_path / "catalogue.yaml", RULES_PATH)


def test_unknown_condition(tmp_path):
    rules = copy.deepcopy(RULES)
    rules["exercise"][0]["when"]["condition"] = "kne_injury"
    err = _load_broken(tmp_path, rules=rules)
    assert "exercise[EX-KNEE-01].when.condition: unknown condition 'kne_injury'" in str(err)


def test_unknown_tag_and_value(tmp_path):
    rules = copy.deepcopy(RULES)
    rules["exercise"][0]["block"] = {"knee_lode": "high"}
    rules["exercise"][1]["block"] = {"impact": "extreme"}
    err = str(_load_broken(tmp_path, rules=rules))
    assert "exercise[EX-KNEE-01].block: unknown tag 'knee_lode'" in err
    assert "exercise[EX-KNEE-02].block.impact: ['extreme']" in err


def test_rule_that_matches_nothing(tmp_path):
    rules = copy.deepcopy(RULES)
    rules["mental"][0]["block"] = {"breath_hold": False}
    err = _load_broken(tmp_path, rules=rules)
    assert "no catalogue item has breath_hold=[False]" in str(err)


def test_bad_severity_and_missing_reason(tmp_path):
    rules = copy.deepcopy(RULES)
    rules["dietary"][0]["severity"] = "maybe"
    del rules["dietary"][1]["reason"]
    err = str(_load_broken(tmp_path, rules=rules))
    assert "rules.yaml: dietary.0.severity: Input should be 'block' or 'warn'" in err
    assert "rules.yaml: dietary.1.reason: Field required" in err


def test_duplicate_rule_id(tmp_path):
    rules = copy.deepcopy(RULES)
    rules["exercise"][1]["id"] = rules["exercise"][0]["id"]
    err = _load_broken(tmp_path, rules=rules)
    assert "rule id 'EX-KNEE-01' is used 2 times" in str(err)


def test_duplicate_alias(tmp_path):
    catalogue = copy.deepcopy(CATALOGUE)
    catalogue["practices"][0]["aliases"].append("Back Squat")
    err = _load_broken(tmp_path, catalogue=catalogue)
    assert "alias 'back squat' is used by exercises[back_squat], practices[box_breathing]" in str(
        err
    )


def test_duplicate_id(tmp_path):
    catalogue = copy.deepcopy(CATALOGUE)
    catalogue["practices"][0]["id"] = "back_squat"
    err = _load_broken(tmp_path, catalogue=catalogue)
    assert "id 'back_squat' is used 2 times" in str(err)


def test_meat_without_animal_product(tmp_path):
    catalogue = copy.deepcopy(CATALOGUE)
    chicken = next(i for i in catalogue["ingredients"] if i["name"] == "chicken")
    chicken["diet_conflicts"] = ["meat"]
    err = _load_broken(tmp_path, catalogue=catalogue)
    assert "ingredients[chicken]: ['meat'] needs diet_conflict 'animal_product'" in str(err)


def test_unknown_allergen(tmp_path):
    catalogue = copy.deepcopy(CATALOGUE)
    catalogue["ingredients"][0]["allergens"] = ["nuts"]
    err = _load_broken(tmp_path, catalogue=catalogue)
    assert "catalogue.yaml: ingredients.0.allergens.0: Input should be" in str(err)


def test_crisis_exception_without_phrase(tmp_path):
    rules = copy.deepcopy(RULES)
    rules["crisis"]["exceptions"].append("killer abs")
    err = _load_broken(tmp_path, rules=rules)
    assert "crisis.exceptions: 'killer abs' contains no crisis phrase" in str(err)


def test_crisis_missing_language(tmp_path):
    rules = copy.deepcopy(RULES)
    del rules["crisis"]["phrases"]["hi_deva"]
    err = _load_broken(tmp_path, rules=rules)
    assert "crisis.phrases: languages must be" in str(err)


def test_all_problems_reported_together(tmp_path):
    rules = copy.deepcopy(RULES)
    rules["exercise"][0]["when"]["condition"] = "nope"
    rules["mental"][0]["when"]["condition"] = "nope_either"
    err = _load_broken(tmp_path, rules=rules)
    assert len(err.problems) == 2
