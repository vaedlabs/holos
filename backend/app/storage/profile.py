"""An account's saved profile text as the IDs and tags the gate checks (Plan C.8).

    profile = resolve_profile(medical, preferences)   # UserProfile
    caveat = unchecked_caveat(profile)                 # for every plan, or None

Conditions resolve through the catalogue's condition names and aliases ("torn ACL left
knee" → knee_ligament_injury); allergies and diets through its profile terms ("no
dairy" → milk, "pure veg" → vegetarian). A phrase that names nothing the catalogue
knows goes into `notes`, which the coaches read but the gate can't check, so every plan
then carries a caveat saying so. Medications are always such a note.

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


def resolve_profile(medical, preferences) -> UserProfile:
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
    notes = [*unchecked]
    if medications:
        notes.append(f"medications: {medications}")
    if free:
        notes.append(free)
    return UserProfile(condition_ids=sorted(found["condition"]),
                       allergen_tags=sorted(found["allergen"]),
                       diet_tags=sorted(found["diet"]),
                       notes="; ".join(notes)[:NOTES_MAX])


def unchecked_caveat(profile: UserProfile | None) -> str | None:
    """Every plan's caveat while the profile has text the gate couldn't check (C.8)."""
    if profile is None or not profile.notes.strip():
        return None
    note = profile.notes.strip()
    if len(note) > CAVEAT_NOTE_CHARS:
        note = note[:CAVEAT_NOTE_CHARS - 1] + "…"
    return f"We couldn't check this note: '{note}'"
