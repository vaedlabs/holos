"""An account's saved profile text as the IDs and tags the gate checks (Plan C.8).

    resolved = resolve_profile(medical, preferences)  # .profile, .unchecked
    caveat = unchecked_caveat(resolved.unchecked)      # for every plan, or None
    profile = with_note_terms(guest_profile)           # a guest's notes add tags too

Conditions resolve through the catalogue's condition names and aliases ("torn ACL left
knee" → knee_ligament_injury); allergies and diets through its profile terms ("no
dairy" → milk, "pure veg" → vegetarian). Everything goes into `notes` for
the coaches to read. Only health text the gate couldn't check gets the caveat on every
plan (owner, 2 Nov 2026, Part E #42): a phrase in conditions, limitations or dietary
restrictions that names nothing the catalogue knows, and the medications. Free notes
("very little free time") don't: they are context, not a health claim, and a warning on
every plan for them taught people to ignore warnings (75 of 215 live plans). What a free
note names still counts ("coeliac" in a note means gluten).

Over-matching is the safe direction: an extra condition only blocks more. A condition
after "no", "not", "never" or "without" ("no back pain") doesn't count; an allergy or
diet word after "no" does ("no dairy" means avoid dairy), only "not"/"non"/"never"
cancel it ("non-veg").
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.agents.schemas import UserProfile
from app.guardrails.loader import get_guardrails
from app.guardrails.normalise import fold_for_matching

NOTES_MAX = 1000
CAVEAT_NOTE_CHARS = 200
_SPLIT = re.compile(r"[,;\n]+|\band\b")
_CONDITION_NEGATIONS = {"no", "not", "never", "without", "non"}
_TAG_NEGATIONS = {"not", "non", "never"}


@dataclass(frozen=True)
class _Term:
    pattern: re.Pattern
    kind: str  # condition, allergen or diet
    tag: str


def _pattern(words: Iterable[str]) -> re.Pattern:
    alternatives = sorted({fold_for_matching(w) for w in words}, key=len, reverse=True)
    return re.compile(r"(?<![\w'])(" + "|".join(map(re.escape, alternatives)) + r")(?![\w'])")


def _terms() -> list[_Term]:
    catalogue = get_guardrails().catalogue
    terms = [_Term(_pattern([c.id.replace("_", " "), c.name, *c.aliases]), "condition", c.id)
             for c in catalogue.conditions]
    terms += [_Term(_pattern(words), "allergen", str(tag))
              for tag, words in catalogue.profile_terms.allergens.items()]
    terms += [_Term(_pattern(words), "diet", str(tag))
              for tag, words in catalogue.profile_terms.diets.items()]
    return terms


_TERMS: list[_Term] | None = None


def phrases(text: str | None) -> list[str]:
    """Saved text is a JSON list or comma-separated (the old app wrote both)."""
    if not text or not text.strip():
        return []
    try:
        loaded = json.loads(text)
    except (ValueError, TypeError):
        loaded = None
    parts = ([str(p) for p in loaded] if isinstance(loaded, list) else _SPLIT.split(text))
    return [p.strip() for p in parts if p and p.strip()]


def _found(phrase: str) -> list[tuple[str, str]]:
    global _TERMS
    if _TERMS is None:
        _TERMS = _terms()
    folded = fold_for_matching(phrase)
    found = []
    for term in _TERMS:
        for match in term.pattern.finditer(folded):
            before = folded[:match.start()].split()
            negations = _CONDITION_NEGATIONS if term.kind == "condition" else _TAG_NEGATIONS
            if before and before[-1] in negations:
                continue
            found.append((term.kind, term.tag))
            break
    return found


@dataclass(frozen=True)
class Resolved:
    profile: UserProfile
    unchecked: tuple[str, ...] = ()  # health text the gate can't check: the caveat


def resolve_profile(medical, preferences) -> Resolved:
    """`medical`: a MedicalHistory row or None; `preferences`: a UserPreferences row or
    None. Reads conditions, limitations and notes (conditions), dietary restrictions
    (allergies and diets) and medications (a note)."""
    found: dict[str, set[str]] = {"condition": set(), "allergen": set(), "diet": set()}
    unchecked: list[str] = []
    sources = [getattr(medical, "conditions", None), getattr(medical, "limitations", None),
               getattr(preferences, "dietary_restrictions", None)]
    for text in sources:
        for phrase in phrases(text):
            hits = _found(phrase)
            for kind, tag in hits:
                found[kind].add(tag)
            if not hits:
                unchecked.append(phrase)
    # Free notes: whatever they name counts, and the note stays for the coaches to read
    free = (getattr(medical, "notes", None) or "").strip()
    for kind, tag in _found(free) if free else []:
        found[kind].add(tag)
    medications = (getattr(medical, "medications", None) or "").strip()
    if medications:
        unchecked.append(f"medications: {medications}")
    notes = [*unchecked, free] if free else unchecked
    profile = UserProfile(condition_ids=sorted(found["condition"]),
                          allergen_tags=sorted(found["allergen"]),
                          diet_tags=sorted(found["diet"]),
                          notes="; ".join(notes)[:NOTES_MAX])
    return Resolved(profile, tuple(unchecked))


def with_note_terms(profile: UserProfile | None) -> UserProfile | None:
    """A guest's own notes: what they name joins the tags the gate checks (the safe
    direction); they get no caveat, like an account's free notes."""
    if profile is None or not profile.notes.strip():
        return profile
    found = _found(profile.notes)
    if not found:
        return profile
    tags = {"condition": set(profile.condition_ids),
            "allergen": set(map(str, profile.allergen_tags)),
            "diet": set(map(str, profile.diet_tags))}
    for kind, tag in found:
        tags[kind].add(tag)
    return profile.model_copy(update={"condition_ids": sorted(tags["condition"]),
                                      "allergen_tags": sorted(tags["allergen"]),
                                      "diet_tags": sorted(tags["diet"])})


def unresolved_phrases(text: str | None) -> list[str]:
    """The phrases of a conditions, limitations or diet text that name nothing the
    catalogue knows, folded as the matcher folds them (for the review counts, P4.10)."""
    return [fold_for_matching(p) for p in phrases(text) if not _found(p)]


def unchecked_caveat(unchecked) -> str | None:
    """Every plan's caveat while health text couldn't be checked (C.8, Part E #42)."""
    if not unchecked:
        return None
    note = "; ".join(unchecked).strip()
    if len(note) > CAVEAT_NOTE_CHARS:
        note = note[:CAVEAT_NOTE_CHARS - 1] + "…"
    return f"We couldn't check this note: '{note}'"
