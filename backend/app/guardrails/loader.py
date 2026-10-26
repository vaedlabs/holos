"""Load and validate guardrails/catalogue.yaml and guardrails/rules.yaml.

Validation has two layers: Pydantic checks the shape of each file, then
cross-checks make sure every rule refers to catalogue entries that exist.
Every problem is reported at once, each prefixed with the file and the
path inside it, so a broken file fails with a clear message.
"""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .normalise import CrisisNormaliser, normalise_text
from .types import (
    EXERCISE_TAGS,
    IMPLIES_ANIMAL_PRODUCT_ALLERGENS,
    IMPLIES_ANIMAL_PRODUCT_CONFLICTS,
    PRACTICE_TAGS,
    Allergen,
    Diet,
    DietConflict,
    Severity,
)

GUARDRAILS_DIR = Path(__file__).parent
CATALOGUE_PATH = GUARDRAILS_DIR / "catalogue.yaml"
RULES_PATH = GUARDRAILS_DIR / "rules.yaml"

ID_PATTERN = r"^[a-z][a-z0-9_]*$"
RULE_ID_PATTERN = r"^(EX|DI|MN)-[A-Z]+-\d{2}$"
CRISIS_LANGUAGES = {"en", "hi_latn", "hi_deva"}


class GuardrailsError(ValueError):
    """A catalogue or rules file is missing, malformed or inconsistent."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Invalid guardrails data:\n  " + "\n  ".join(problems))


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _as_list(value: Any) -> Any:
    """Let YAML say `condition: x` as well as `condition: [x, y]`."""
    return value if value is None or isinstance(value, list) else [value]


# --- Catalogue ---


class CatalogueItem(_Model):
    id: str = Field(pattern=ID_PATTERN, max_length=40)
    name: str = Field(min_length=1, max_length=60)
    aliases: list[str] = []
    tags: dict[str, Any] = {}


class Condition(_Model):
    id: str = Field(pattern=ID_PATTERN, max_length=40)
    name: str = Field(min_length=1, max_length=60)
    aliases: list[str] = []


class Ingredient(_Model):
    name: str = Field(min_length=1, max_length=30)
    aliases: list[str] = []
    allergens: list[Allergen] = []
    diet_conflicts: list[DietConflict] = []


class Catalogue(_Model):
    version: int = Field(ge=1)
    exercises: list[CatalogueItem] = Field(min_length=1)
    practices: list[CatalogueItem] = Field(min_length=1)
    conditions: list[Condition] = Field(min_length=1)
    ingredients: list[Ingredient] = Field(min_length=1)

    @property
    def exercise_ids(self) -> list[str]:
        return [item.id for item in self.exercises]

    @property
    def practice_ids(self) -> list[str]:
        return [item.id for item in self.practices]

    @property
    def condition_ids(self) -> list[str]:
        return [item.id for item in self.conditions]


# --- Rules ---


class When(_Model):
    condition: list[str] | None = None
    diet: list[Diet] | None = None
    allergen: Literal["any"] | None = None
    always: Literal[True] | None = None

    _lists = field_validator("condition", "diet", mode="before")(_as_list)


class Rule(_Model):
    id: str = Field(pattern=RULE_ID_PATTERN)
    when: When
    block: dict[str, Any] = Field(min_length=1)
    severity: Severity
    reason: str = Field(min_length=1, max_length=120)


class Helpline(_Model):
    name: str = Field(min_length=1)
    region: str = Field(min_length=1)
    contact: str = Field(min_length=1)


class CrisisNormalise(_Model):
    leet: dict[str, str]  # anywhere: "k1ll"
    leet_inner: dict[str, str] = {}  # only between two letters: "d!e", not "die!"
    chars: dict[str, str] = {}  # apostrophes dropped, Devanagari spellings folded
    words: dict[str, str] = {}  # spelling variants and contractions, whole words

    def normaliser(self) -> CrisisNormaliser:
        return CrisisNormaliser(self.leet, self.leet_inner, self.chars, self.words)


class Crisis(_Model):
    message: str = Field(min_length=1)
    reminder: str = Field(min_length=1)
    helplines: list[Helpline] = Field(min_length=1)
    phrases: dict[str, list[str]]
    exceptions: list[str] = []
    normalise: CrisisNormalise


class Rules(_Model):
    version: int = Field(ge=1)
    exercise: list[Rule] = Field(min_length=1)
    dietary: list[Rule] = Field(min_length=1)
    mental: list[Rule] = Field(min_length=1)
    crisis: Crisis


@dataclass(frozen=True)
class Guardrails:
    catalogue: Catalogue
    rules: Rules


# --- Loading ---


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GuardrailsError([f"{path.name}: file not found ({path})"]) from None
    except yaml.YAMLError as exc:
        raise GuardrailsError([f"{path.name}: invalid YAML: {exc}"]) from None


def _parse(model: type[_Model], path: Path) -> Any:
    data = _read_yaml(path)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = [
            f"{path.name}: {'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()
        ]
        raise GuardrailsError(problems) from None


def load_guardrails(
    catalogue_path: Path = CATALOGUE_PATH, rules_path: Path = RULES_PATH
) -> Guardrails:
    """Load both files and cross-check them. Raises GuardrailsError."""
    catalogue = _parse(Catalogue, catalogue_path)
    rules = _parse(Rules, rules_path)
    problems = _check_catalogue(catalogue, catalogue_path.name)
    problems += _check_rules(rules, catalogue, rules_path.name)
    if problems:
        raise GuardrailsError(problems)
    return Guardrails(catalogue=catalogue, rules=rules)


@lru_cache(maxsize=1)
def get_guardrails() -> Guardrails:
    """The packaged catalogue and rules, loaded once per process."""
    return load_guardrails()


# --- Cross-checks ---


def _check_tags(
    tags: dict[str, Any], vocab: dict[str, tuple], where: str
) -> list[str]:
    problems = []
    for key, value in tags.items():
        if key not in vocab:
            problems.append(f"{where}.tags: unknown tag '{key}'")
        elif value not in vocab[key]:
            problems.append(f"{where}.tags.{key}: '{value}' is not one of {list(vocab[key])}")
    return problems


def _check_catalogue(catalogue: Catalogue, file: str) -> list[str]:
    problems = []

    ids = Counter(
        item.id for item in [*catalogue.exercises, *catalogue.practices, *catalogue.conditions]
    )
    problems += [f"{file}: id '{i}' is used {n} times" for i, n in ids.items() if n > 1]

    # Every name and alias maps to exactly one item
    owners: dict[str, list[str]] = {}
    sections = {
        "exercises": catalogue.exercises,
        "practices": catalogue.practices,
        "conditions": catalogue.conditions,
        "ingredients": catalogue.ingredients,
    }
    for section, items in sections.items():
        for item in items:
            label = f"{section}[{getattr(item, 'id', item.name)}]"
            for term in [item.name, *item.aliases]:
                owners.setdefault(normalise_text(term), []).append(label)
    problems += [
        f"{file}: name or alias '{term}' is used by {', '.join(labels)}"
        for term, labels in owners.items()
        if len(labels) > 1
    ]

    for item in catalogue.exercises:
        problems += _check_tags(item.tags, EXERCISE_TAGS, f"{file}: exercises[{item.id}]")
    for item in catalogue.practices:
        problems += _check_tags(item.tags, PRACTICE_TAGS, f"{file}: practices[{item.id}]")

    for food in catalogue.ingredients:
        implies = set(food.diet_conflicts) & IMPLIES_ANIMAL_PRODUCT_CONFLICTS
        implies |= set(food.allergens) & IMPLIES_ANIMAL_PRODUCT_ALLERGENS
        if implies and DietConflict.ANIMAL_PRODUCT not in food.diet_conflicts:
            problems.append(
                f"{file}: ingredients[{food.name}]: {sorted(str(t) for t in implies)} "
                "needs diet_conflict 'animal_product'"
            )
        conflicts = set(food.diet_conflicts)
        if DietConflict.PORK in conflicts and DietConflict.MEAT not in conflicts:
            problems.append(f"{file}: ingredients[{food.name}]: 'pork' needs 'meat'")

    return problems


def _check_rules(rules: Rules, catalogue: Catalogue, file: str) -> list[str]:
    problems = []

    ids = Counter(r.id for r in [*rules.exercise, *rules.dietary, *rules.mental])
    problems += [f"{file}: rule id '{i}' is used {n} times" for i, n in ids.items() if n > 1]

    condition_ids = set(catalogue.condition_ids)
    sections = {
        "exercise": (rules.exercise, "EX", {"condition"}, EXERCISE_TAGS, catalogue.exercises),
        "mental": (rules.mental, "MN", {"condition", "always"}, PRACTICE_TAGS, catalogue.practices),
    }
    for section, (section_rules, prefix, allowed_when, vocab, items) in sections.items():
        for rule in section_rules:
            where = f"{file}: {section}[{rule.id}]"
            if not rule.id.startswith(prefix + "-"):
                problems.append(f"{where}: id must start with '{prefix}-'")
            problems += _check_when(rule.when, allowed_when, condition_ids, where)
            for key, value in rule.block.items():
                if section == "mental" and key == "text":
                    if not isinstance(value, list) or not value or not all(
                        isinstance(v, str) and v.strip() for v in value
                    ):
                        problems.append(f"{where}.block.text: must be a list of phrases")
                    continue
                if key not in vocab:
                    problems.append(f"{where}.block: unknown tag '{key}'")
                    continue
                values = _as_list(value)
                bad = [v for v in values if v not in vocab[key]]
                if bad:
                    problems.append(
                        f"{where}.block.{key}: {bad} not in {list(vocab[key])}"
                    )
                elif not any(item.tags.get(key) in values for item in items):
                    problems.append(
                        f"{where}.block.{key}: no catalogue item has {key}={values}"
                    )

    used_conflicts = {c for food in catalogue.ingredients for c in food.diet_conflicts}
    for rule in rules.dietary:
        where = f"{file}: dietary[{rule.id}]"
        if not rule.id.startswith("DI-"):
            problems.append(f"{where}: id must start with 'DI-'")
        problems += _check_when(rule.when, {"diet", "allergen"}, condition_ids, where)
        for key, value in rule.block.items():
            if key == "allergen":
                if value != "same":
                    problems.append(f"{where}.block.allergen: must be 'same'")
                if rule.when.allergen != "any":
                    problems.append(f"{where}: block.allergen needs when.allergen: any")
            elif key == "diet_conflict":
                for tag in _as_list(value):
                    if tag not in DietConflict.__members__.values():
                        problems.append(f"{where}.block.diet_conflict: unknown tag '{tag}'")
                    elif tag not in used_conflicts:
                        problems.append(
                            f"{where}.block.diet_conflict: no ingredient has '{tag}'"
                        )
            else:
                problems.append(f"{where}.block: unknown key '{key}'")

    problems += _check_crisis(rules.crisis, file)
    return problems


def _check_when(
    when: When, allowed: set[str], condition_ids: set[str], where: str
) -> list[str]:
    problems = []
    given = {k for k, v in when.model_dump().items() if v is not None}
    if len(given) != 1:
        problems.append(f"{where}.when: needs exactly one of {sorted(allowed)}")
    problems += [f"{where}.when: '{k}' is not allowed here" for k in given - allowed]
    for cid in when.condition or []:
        if cid not in condition_ids:
            problems.append(f"{where}.when.condition: unknown condition '{cid}'")
    return problems


def _check_crisis(crisis: Crisis, file: str) -> list[str]:
    where = f"{file}: crisis"
    problems = []
    if set(crisis.phrases) != CRISIS_LANGUAGES:
        problems.append(f"{where}.phrases: languages must be {sorted(CRISIS_LANGUAGES)}")
    for section in ("leet", "leet_inner", "chars"):
        for key in getattr(crisis.normalise, section):
            if len(key) != 1:
                problems.append(f"{where}.normalise.{section}: key '{key}' must be one character")
    if problems:
        return problems
    # Phrases and exceptions are compared as the check sees them, after normalisation
    normalise = crisis.normalise.normaliser()
    for key, value in crisis.normalise.words.items():
        if normalise(value) != value:
            problems.append(f"{where}.normalise.words: '{key}' -> '{value}' is not normalised")
    phrases = []
    for lang, items in crisis.phrases.items():
        if not items:
            problems.append(f"{where}.phrases.{lang}: is empty")
        phrases += [normalise(p) for p in items]
    dupes = [p for p, n in Counter(phrases).items() if n > 1]
    problems += [f"{where}.phrases: '{p}' is listed twice (after normalisation)" for p in dupes]
    for exception in crisis.exceptions:
        if not any(p in normalise(exception) for p in phrases):
            problems.append(f"{where}.exceptions: '{exception}' contains no crisis phrase")
    return problems
