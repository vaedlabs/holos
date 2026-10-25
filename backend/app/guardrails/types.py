"""Fixed vocabularies shared by the catalogue, the rules and the schemas."""

from enum import StrEnum


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
