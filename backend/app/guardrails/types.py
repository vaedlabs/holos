"""Fixed vocabularies shared by the catalogue, the rules and the schemas, and the
gate's input and output types."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Protocol


class Allergen(StrEnum):
    """Allergen tags (Plan C.3)."""

    PEANUT = "peanut"
    TREE_NUT = "tree_nut"
    MILK = "milk"
    EGG = "egg"
    FISH = "fish"
    CRUSTACEAN = "crustacean"
    MOLLUSC = "mollusc"
    SOY = "soy"
    GLUTEN = "gluten"
    SESAME = "sesame"
    MUSTARD = "mustard"
    CELERY = "celery"
    LUPIN = "lupin"
    SULPHITES = "sulphites"


class Diet(StrEnum):
    """Diet tags a profile can carry (Plan C.3)."""

    VEGAN = "vegan"
    VEGETARIAN = "vegetarian"
    EGGETARIAN = "eggetarian"
    JAIN = "jain"
    HALAL = "halal"
    KOSHER = "kosher"
    PESCATARIAN = "pescatarian"
    LACTOSE_FREE = "lactose_free"


class DietConflict(StrEnum):
    """Diet-conflict tags on ingredients (Plan C.14)."""

    ANIMAL_PRODUCT = "animal_product"
    MEAT = "meat"
    FISH = "fish"
    SHELLFISH = "shellfish"
    EGG = "egg"
    PORK = "pork"
    ALCOHOL = "alcohol"
    GELATIN = "gelatin"
    HONEY = "honey"
    ROOT_VEGETABLE = "root_vegetable"
    LACTOSE = "lactose"


class Severity(StrEnum):
    """What the gate does when a rule matches."""

    BLOCK = "block"
    WARN = "warn"


LEVELS = ("low", "moderate", "high")

# Tag keys and allowed values for catalogue items. A missing tag means
# "low" for levels and false for flags.
EXERCISE_TAGS: dict[str, tuple] = {
    "knee_load": LEVELS,
    "spinal_load": LEVELS,
    "shoulder_load": LEVELS,
    "wrist_load": LEVELS,
    "ankle_load": LEVELS,
    "neck_load": LEVELS,
    "impact": LEVELS,
    "exertion": LEVELS,
    "abdominal_strain": LEVELS,
    "heavy_load": (True, False),
    "supine": (True, False),
    "inversion": (True, False),
}

PRACTICE_TAGS: dict[str, tuple] = {
    "breath_hold": (True, False),
    "forceful_breathing": (True, False),
}

# Tags that imply animal_product: an ingredient with one of these must
# also carry animal_product, so a vegan rule can't miss it.
IMPLIES_ANIMAL_PRODUCT_CONFLICTS = frozenset(
    {
        DietConflict.MEAT,
        DietConflict.FISH,
        DietConflict.SHELLFISH,
        DietConflict.EGG,
        DietConflict.PORK,
        DietConflict.GELATIN,
        DietConflict.HONEY,
        DietConflict.LACTOSE,
    }
)
IMPLIES_ANIMAL_PRODUCT_ALLERGENS = frozenset(
    {Allergen.MILK, Allergen.EGG, Allergen.FISH, Allergen.CRUSTACEAN, Allergen.MOLLUSC}
)


# --- Gate input and output (Plan C.14) ---
# Plain dataclasses: guardrails/ can't import app.agents.schemas. The fields of
# Decision match schemas.Decision, so the caller converts with Decision(**asdict(d)).

Action = Literal["allow", "warn", "block"]
Domain = Literal["physical", "nutrition", "mental"]
ACTION_ORDER: dict[str, int] = {"allow": 0, "warn": 1, "block": 2}


class ProfileLike(Protocol):
    """What the gate reads from a profile; schemas.UserProfile fits."""

    condition_ids: Sequence[str]
    allergen_tags: Sequence[str]
    diet_tags: Sequence[str]


@dataclass(frozen=True)
class Profile:
    condition_ids: tuple[str, ...] = ()
    allergen_tags: tuple[str, ...] = ()
    diet_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    action: Action
    rule_id: str
    rules_version: int
    reason: str
    offending_items: tuple[str, ...] = ()


@dataclass(frozen=True)
class ItemVerdict:
    """The gate's view of one plan item or one food in a meal write."""

    index: int
    action: Action
    caveats: tuple[str, ...] = ()
    decisions: tuple[Decision, ...] = ()


@dataclass(frozen=True)
class Scrub:
    """Text the gate removed that no profile rule asked for: a link or a write claim."""

    kind: Literal["link", "write_claim"]
    field: str
    text: str


@dataclass(frozen=True)
class GateResult:
    action: Action  # the worst decision; malformed counts as block
    decisions: tuple[Decision, ...]
    content: Any  # the reply or write with prose cleaned; items are left for the caller
    items: tuple[ItemVerdict, ...] = ()
    scrubbed: tuple[Scrub, ...] = ()
    malformed: bool = False

    @property
    def blocked_items(self) -> list[int]:
        return [v.index for v in self.items if v.action == "block"]

    @property
    def needs_retry(self) -> bool:
        """BaseAgent retries only for a blocked item or a malformed reply. A block in
        prose is already handled: the sentence is gone (owner, Part E #18, 26 Oct 2026)."""
        return self.malformed or bool(self.blocked_items)
