"""Find catalogue items and ingredients in text (Plan C.14).

Every exercise, practice and ingredient name and alias becomes a term. A term
matches only as whole words, with an optional plural ("squats", "lunges"), and
the longest term wins where terms overlap ("peanut butter" is not "butter").

A mention can be negated: "avoid squats", "no lunges today", "don't do burpees",
"squats mat karo", "check the label for peanuts", "your peanut allergy". A list
shares a negation: "avoid onion, garlic and root vegetables". Negation decides
only whether prose recommends an item; plan items and food ingredients are never
negated. Every cue below comes from real replies (Part D, P3.1 and P4.3); where a
phrase could also recommend, it is left out, so the gate errs towards removing.
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
    # Exclusions explained (live Luna replies, 27 Oct 2026): "it avoids onion",
    # "I've avoided wheat", "I left out peanut chutney", "avoid cross-contact with milk"
    "avoids", "avoided", "skips", "skipped", "excludes", "excluded", "omit", "omits",
    "omitted", "omitting", "leave out", "leaves out", "left out", "leaving out",
    # One cue, not two: "avoid" + "cross contact with" would cancel out
    "avoid cross contact with", "prevent cross contact with", "no cross contact with",
    "cross contact with",
)
# A warning cue after another warning cue adds to it: "watch for cross-contact with
# peanuts", "check the label for traces of egg". A true negator before a warning cue
# still flips it: "no need to watch for peanuts" says peanuts are fine.
WARNING_CUES = (
    "allergic to", "allergy to", "label for", "labels for", "traces of", "may contain",
    "check for", "watch for", "watch out for", "look out for", "avoid cross contact with",
    "prevent cross contact with", "no cross contact with", "cross contact with",
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
    # Hinglish: "peanut se bachein" (avoid), "unhe chhod dein" (leave out),
    # "soy sauce na daalein" (don't add), "mustard ke bina" (without)
    "se bachein", "se bacho", "se bachna", "se bachen", "chhod dein", "chhod do",
    "na daalein", "na daalo", "na dalein", "na use karein", "na use karo", "ke bina",
    "left out", "are left out", "is left out",
)
# Hindi puts the verb after its whole object, so these also cover the list before
# them: "peanut ya groundnut oil se bachein". English post-cues never reach back:
# "peanut chutney and nut-free cookies" still recommends the chutney.
HINDI_POST_CUES = (
    "mat karo", "mat kijiye", "mat karna", "mat kar", "mat karein", "mat khao", "mat khaiye",
    "mat khana", "mat lo", "mat lena", "mat piyo", "nahi", "nahin", "na karo", "na karein",
    "se bachein", "se bacho", "se bachna", "se bachen", "chhod dein", "chhod do",
    "na daalein", "na daalo", "na dalein", "na use karein", "na use karo", "ke bina",
)
# Nouns after a food that name the allergy, not the food: "your peanut allergy",
# "peanut cross-contact", "egg traces". A list before them shares the negation:
# "your milk and tree nut allergies".
POST_NOUN_CUES = ("allergy", "allergies", "intolerance", "cross contact", "traces")
POST_NOUN_REACH = 0  # right after the food: "peanut allergy", not "peanut toast suits your allergy"

# "check ... for X" warns about X when what is checked is a label or an ingredient:
# "check spice blends and packaged ingredients for sesame". Not any "for": "check
# out this recipe for peanut chutney" recommends it.
CHECK_VERBS = frozenset({"check", "checks", "checking", "verify", "inspect", "read", "scan"})
CHECKED_THINGS = frozenset({
    "label", "labels", "package", "packages", "packaging", "packet", "packets", "packaged",
    "ingredient", "ingredients", "spice", "spices", "blend", "blends", "mix", "mixes",
    "masala", "masale", "seasoning", "seasonings", "sauce", "sauces", "oil", "oils",
    "preparation", "statement", "statements", "product", "products",
})
CHECK_REACH = 6  # words from the verb to "for"

# "Good morning" is also an exercise. It's the greeting at the start of a sentence
# ("Good morning, Harbhajan!", "Good morning to you") or before "!", unless exercise
# words follow ("Good morning with a light bar", "Good morning 3x10"). "Do 3 sets of
# good morning." and "good mornings" stay the exercise (Part E #36).
GREETING_TERM = "good morning"
EXERCISE_FOLLOWERS = frozenset({
    "exercise", "exercises", "set", "sets", "rep", "reps", "with", "using", "barbell",
    "dumbbell", "for", "x",
})
_SENTENCE_START = re.compile(r"(?:^|[.!?\n]|[^\w\s,;:'\"()-])\s*$")
# "don't check labels for peanuts" says peanuts are fine
CHECK_NEGATORS = frozenset({"don't", "dont", "not", "no", "never", "needn't", "skip"})
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
_POST_NOUNS = _phrases(POST_NOUN_CUES)
_HINDI_POST = _phrases(HINDI_POST_CUES)
_WARNING = frozenset(tuple(c.split()) for c in WARNING_CUES)

# Between two mentions of one list: a comma, and/or, or both ("onion, garlic and ..."),
# after an optional modifier and one noun ("peanut based chutneys and groundnut oil")
_LIST_JOIN = re.compile(
    r"(?:\s+(?:based|containing|coated|flavoured|flavored|style|rich)(?:\s+[\w']+)?)?"
    r"\s*,?\s*(?:(?:and|or|nor|aur|ya|&)\s+)?")
_AND_OR = re.compile(r"\b(?:and|or|nor|aur|ya)\b|&")
# The list goes on past its last catalogue mention: "onion, garlic and root vegetables"
_LIST_GOES_ON = re.compile(r"\s*,?\s*(?:and|or|nor|aur|ya)\s")
# From a negated mention to its examples: "wheat based staples such as roti",
# "avoid sesame, including sesame oil". Carries the negation forward only.
# A food made of a negated one: "instead of wheat-based roti". Forward only.
_COMPOUND = re.compile(r"\s+(?:based|containing|coated)\s+")
_EXAMPLES = re.compile(r"\s*,?((?:\s+[\w']+){0,3})\s+(?:such as|including|like|e g)\s+")


def _cue_length(words: list[str], i: int, cues: list[tuple[str, ...]]) -> int:
    for cue in cues:
        if tuple(words[i:i + len(cue)]) == cue:
            return len(cue)
    return 0


def _negated_before(words: list[str]) -> bool:
    negated, gap, i, last_warning = False, 0, 0, False
    while i < len(words):
        length = _cue_length(words, i, _CUES)
        if length:
            warning = tuple(words[i:i + length]) in _WARNING
            flips = negated and gap <= NEGATION_WINDOW and not (warning and last_warning)
            negated, last_warning = not flips, warning
            gap = 0
            i += length
            continue
        if words[i] in NEGATION_RESETS:
            negated = False
        gap += 1
        i += 1
    return negated and gap <= NEGATION_WINDOW


def _checked_for(words: list[str]) -> bool:
    """"check <label or ingredient words> for <mention>", the mention within reach."""
    if "for" not in words:
        return False
    at = len(words) - 1 - words[::-1].index("for")
    after = words[at + 1:]
    if len(after) > NEGATION_WINDOW or any(w in NEGATION_RESETS for w in after):
        return False
    before = words[max(0, at - CHECK_REACH):at]
    verbs = [i for i, w in enumerate(before) if w in CHECK_VERBS]
    if not verbs:
        return False
    start = max(0, at - CHECK_REACH)
    if any(w in CHECK_NEGATORS for w in words[max(0, start + verbs[-1] - 3):start + verbs[-1]]):
        return False
    between = before[verbs[-1] + 1:]
    return (any(w in CHECKED_THINGS for w in between)
            and not any(w in NEGATION_RESETS for w in between))


def _negated_after(words: list[str], cues: list[tuple[str, ...]] = _POST_CUES,
                   reach: int = POST_NEGATION_WINDOW) -> bool:
    for i, word in enumerate(words[:reach + 1]):
        if word in POST_NEGATION_RESETS:
            return False
        if _cue_length(words, i, cues):
            return True
    return False


def _share_in_lists(folded: str, found: list[tuple[int, int, bool, bool]]) -> list[bool]:
    """Spread a negation along a list. found: (start, end, negated, noun_after) per
    mention. A list is mentions joined by commas and/or; one joined only by commas
    counts only if an and/or closes it ("without onion, garlic adds flavour" is not a
    list). Forward from a negated mention; backward only from an allergy noun."""
    negated = [n for _, _, n, _ in found]
    for _ in range(len(found)):  # until nothing changes: examples can start a list
        before = list(negated)
        _share_once(folded, found, negated)
        if negated == before:
            break
    return negated


def _share_once(folded: str, found: list[tuple[int, int, bool, bool]],
                negated: list[bool]) -> None:
    i = 0
    while i < len(found):
        j, joins = i, []
        while j + 1 < len(found):
            gap = folded[found[j][1]:found[j + 1][0]]
            if not _LIST_JOIN.fullmatch(gap):
                break
            joins.append(gap)
            j += 1
        goes_on = _LIST_GOES_ON.match(folded, found[j][1]) is not None
        if j > i and (any(_AND_OR.search(g) for g in joins) or goes_on):
            for k in range(i + 1, j + 1):  # forward
                negated[k] = negated[k] or negated[k - 1]
            if found[j][3]:  # backward from "... allergies" or a Hindi verb
                for k in range(i, j):
                    negated[k] = True
        i = j + 1
    for k in range(1, len(found)):  # examples of, or foods made of, a negated mention
        gap = folded[found[k - 1][1]:found[k][0]]
        example = _EXAMPLES.fullmatch(gap)
        if negated[k - 1] and (_COMPOUND.fullmatch(gap) or (example and not any(
            w in NEGATION_RESETS for w in WORD.findall(example.group(1))
        ))):
            negated[k] = True


def _is_greeting(folded: str, match: re.Match) -> bool:
    if match.group(0) != GREETING_TERM:  # "good mornings", "barbell good morning"
        return False
    after = folded[match.end():]
    if after.startswith("!"):
        return True
    if not _SENTENCE_START.search(folded[:match.start()]) or after.lstrip().startswith(":"):
        return False
    following = WORD.findall(after)
    return not following or (following[0] not in EXERCISE_FOLLOWERS
                             and not following[0][0].isdigit())


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
        matches, found = [], []
        previous_end = 0
        for match in self._pattern.finditer(folded):
            # A negation doesn't jump over another food ("no onion needed and garlic
            # works"); only a list carries it on (_share_in_lists)
            before = WORD.findall(CLAUSE_BREAK.split(folded[previous_end:match.start()])[-1])
            previous_end = match.end()
            after = WORD.findall(CLAUSE_BREAK.split(folded[match.end():])[0])
            noun_after = (_negated_after(after, _POST_NOUNS, POST_NOUN_REACH)
                          or _negated_after(after, _HINDI_POST))
            negated = (_negated_before(before) or _checked_for(before)
                       or _negated_after(after) or noun_after)
            matches.append(match)
            found.append((match.start(), match.end(), negated, noun_after))
        negated = _share_in_lists(folded, found)
        return [Mention(m.group(1), self.terms[m.group(1)], m.start(), m.end(), n)
                for m, n in zip(matches, negated, strict=True)
                if not _is_greeting(folded, m)]

    def ingredients(self, text: str) -> list[Entry]:
        """The known ingredients named in a food name or ingredient. Negation is
        ignored, so "peanut-free sauce" still counts as peanut (fails closed)."""
        return [m.entry for m in self.find(text) if m.entry.kind == "ingredient"]


@lru_cache(maxsize=1)
def get_matcher() -> Matcher:
    """The matcher for the packaged catalogue, built once per process."""
    return Matcher(get_guardrails().catalogue)
