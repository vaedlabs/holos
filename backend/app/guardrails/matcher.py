"""Find catalogue items and ingredients in text (Plan C.14).

Every exercise, practice and ingredient name and alias becomes a term. A term
matches only as whole words, with an optional plural ("squats", "lunges"), and
the longest term wins where terms overlap ("peanut butter" is not "butter").

A mention can be negated: "avoid squats", "no lunges today", "don't do burpees",
"squats mat karo". Negation decides only whether prose recommends an item; plan
items and food ingredients are never negated.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from .loader import Catalogue, get_guardrails
from .normalise import fold_for_matching
from .types import EXERCISE_TAGS, PRACTICE_TAGS

EntryKind = Literal["exercise", "practice", "ingredient", "food"]  # food: a reply item

WORD = re.compile(r"[\w']+")
# Punctuation that ends the reach of a negation ("avoid running, lunges are fine")
CLAUSE_BREAK = re.compile(r"[.,;:!?()\[\]{}\n—–\"]")

# Words between a negation and the mention it covers, at most
NEGATION_WINDOW = 3
# Words between a mention and a negation that follows it (Hinglish word order)
POST_NEGATION_WINDOW = 2

# A cue negates what follows. A second cue inside the window flips it back:
# "don't skip squats" recommends squats.
NEGATION_CUES = (
    "avoid", "avoiding", "no", "not", "never", "without", "skip", "skipping",
    "stop", "stopping", "quit", "forget", "miss", "neglect", "eliminate",
    "exclude", "excluding", "isn't", "aren't", "don't", "dont", "do not",
    "don't do", "dont do", "do not do", "instead of", "rather than",
    "steer clear of", "stay away from", "refrain from", "cut out", "free of",
    "free from", "mat karo", "mat karna", "mat kijiye", "na karo", "na karein",
    # Allergy warnings: "check the label for nuts", "if you're allergic to cashews"
    "allergic to", "allergy to", "label for", "labels for", "traces of", "may contain",
    "check for", "watch for", "watch out for", "look out for",
)
# A reset ends the negation: "skip squats and do lunges", "no exercise beats squats"
NEGATION_RESETS = frozenset({
    "but", "instead", "try", "then", "do", "does", "doing", "use", "add", "include",
    "including", "choose", "eat", "have", "swap", "with", "replace", "prefer",
    "recommend", "than", "beats", "better", "best", "like", "except", "only",
    "unless", "until", "also", "plus", "can", "should", "must", "start", "begin",
    "keep", "continue", "focus",
})
# Negations that follow the mention: "squats mat karo", "squats nahi", "egg free",
# "box breathing may not suit you". Never a bare "not": "lunges are not bad for you"
# recommends lunges.
POST_NEGATION_CUES = (
    "mat karo", "mat kijiye", "mat karna", "mat kar", "mat karein", "mat khao",
    "mat khaiye", "mat khana", "mat lo", "mat lena", "mat piyo", "nahi", "nahin",
    "na karo", "na karein", "free",
    "may not suit", "might not suit", "doesn't suit", "does not suit", "not suitable",
    "isn't suitable", "not recommended", "isn't recommended", "not safe", "isn't safe",
    "aren't safe", "should be avoided", "is best avoided", "are best avoided",
    "is off limits", "are off limits",
)
# "squats kyun nahi karte?" asks why you don't: a suggestion, not a negation
POST_NEGATION_RESETS = frozenset({"kyun", "kyon", "kyu", "why"})


@dataclass(frozen=True)
class Entry:
    kind: EntryKind
    key: str  # catalogue ID, or the ingredient's name
    name: str  # display name
    tags: dict[str, Any] = field(default_factory=dict, hash=False)  # exercises, practices
    allergens: frozenset[str] = frozenset()  # ingredients
    diet_conflicts: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Mention:
    term: str
    entry: Entry
    start: int
    end: int
    negated: bool


def _with_defaults(tags: dict[str, Any], vocab: dict[str, tuple]) -> dict[str, Any]:
    """A missing tag means "low" for levels and false for flags."""
    return {key: tags.get(key, "low" if "low" in values else False)
            for key, values in vocab.items()}


def _phrases(phrases: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Cue phrases as word tuples, longest first."""
    return sorted((tuple(p.split()) for p in phrases), key=len, reverse=True)


_CUES = _phrases(NEGATION_CUES)
_POST_CUES = _phrases(POST_NEGATION_CUES)


def _cue_length(words: list[str], i: int, cues: list[tuple[str, ...]]) -> int:
    for cue in cues:
        if tuple(words[i:i + len(cue)]) == cue:
            return len(cue)
    return 0


def _negated_before(words: list[str]) -> bool:
    negated, gap, i = False, 0, 0
    while i < len(words):
        length = _cue_length(words, i, _CUES)
        if length:
            negated = not negated if negated and gap <= NEGATION_WINDOW else True
            gap = 0
            i += length
            continue
        if words[i] in NEGATION_RESETS:
            negated = False
        gap += 1
        i += 1
    return negated and gap <= NEGATION_WINDOW


def _negated_after(words: list[str]) -> bool:
    for i, word in enumerate(words[:POST_NEGATION_WINDOW + 1]):
        if word in POST_NEGATION_RESETS:
            return False
        if _cue_length(words, i, _POST_CUES):
            return True
    return False


class Matcher:
    def __init__(self, catalogue: Catalogue):
        self.exercises = {
            item.id: Entry("exercise", item.id, item.name, _with_defaults(item.tags, EXERCISE_TAGS))
            for item in catalogue.exercises
        }
        self.practices = {
            item.id: Entry("practice", item.id, item.name, _with_defaults(item.tags, PRACTICE_TAGS))
            for item in catalogue.practices
        }
        ingredients = [
            Entry("ingredient", food.name, food.name,
                  allergens=frozenset(food.allergens),
                  diet_conflicts=frozenset(food.diet_conflicts))
            for food in catalogue.ingredients
        ]
        terms: dict[str, Entry] = {}
        named = [
            *((item, self.exercises[item.id]) for item in catalogue.exercises),
            *((item, self.practices[item.id]) for item in catalogue.practices),
            *zip(catalogue.ingredients, ingredients, strict=True),
        ]
        for item, entry in named:
            for term in {fold_for_matching(t) for t in [item.name, *item.aliases]}:
                if terms.setdefault(term, entry) is not entry:
                    raise ValueError(f"term '{term}' maps to {terms[term].key} and {entry.key}")
        self.terms = terms
        alternatives = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
        self._pattern = re.compile(rf"(?<![\w'])({alternatives})(?:e?s)?(?![\w'])")

    def find(self, text: str) -> list[Mention]:
        """Every catalogue term in the text, leftmost-longest, with its negation."""
        folded = fold_for_matching(text)
        mentions = []
        for match in self._pattern.finditer(folded):
            before = CLAUSE_BREAK.split(folded[:match.start()])[-1]
            after = CLAUSE_BREAK.split(folded[match.end():])[0]
            negated = (_negated_before(WORD.findall(before))
                       or _negated_after(WORD.findall(after)))
            term = match.group(1)
            mentions.append(Mention(term, self.terms[term], match.start(), match.end(), negated))
        return mentions

    def ingredients(self, text: str) -> list[Entry]:
        """The known ingredients named in a food name or ingredient. Negation is
        ignored, so "peanut-free sauce" still counts as peanut (fails closed)."""
        return [m.entry for m in self.find(text) if m.entry.kind == "ingredient"]


@lru_cache(maxsize=1)
def get_matcher() -> Matcher:
    """The matcher for the packaged catalogue, built once per process."""
    return Matcher(get_guardrails().catalogue)
