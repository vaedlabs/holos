"""The crisis check (Plan C.16): deterministic, no LLM, no network.

    crisis_check(message) -> CrisisMatch

Only the current message is checked. Message and phrases go through the same
normalisation (CrisisNormaliser: leetspeak, split letters, spelling variants such
as "wanna", "chahata" or "मर जाऊँगा"), then phrases are matched with word
boundaries. A match inside an exception ("suicide sprints") doesn't count.
There is no negation handling: "I'm not suicidal" matches, by design.

The browser runs the same check from contracts/crisis.json (lib/crisis.js);
both must pass contracts/crisis_cases.jsonl.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from .loader import Crisis, get_guardrails
from .normalise import WORD_CHAR, CrisisNormaliser

CRISIS_RULE = "CR-PHRASE-01"


@dataclass(frozen=True)
class CrisisMatch:
    matched: bool
    rule_id: str | None = None
    language: str | None = None  # en, hi_latn, hi_deva
    phrase: str | None = None  # the normalised phrase from rules.yaml, never the message


def _phrase_pattern(phrase: str) -> str:
    # A space in a phrase may be missing, so fully split letters ("k i l l m y s e l f"
    # joins to "killmyself") still match
    return r"\s?".join(re.escape(word) for word in phrase.split())


def _compile(phrases) -> re.Pattern:
    alternatives = "|".join(_phrase_pattern(p) for p in sorted(phrases, key=len, reverse=True))
    return re.compile(rf"(?<!{WORD_CHAR})(?:{alternatives or '(?!x)x'})(?!{WORD_CHAR})")


class CrisisChecker:
    def __init__(self, crisis: Crisis):
        self.normalise: CrisisNormaliser = crisis.normalise.normaliser()
        self.language = {
            self.normalise(phrase): language
            for language, phrases in crisis.phrases.items()
            for phrase in phrases
        }
        self._phrases = _compile(self.language)
        self._exceptions = _compile(self.normalise(e) for e in crisis.exceptions)
        self._compact = {p.replace(" ", ""): p for p in self.language}

    def check(self, message: str) -> CrisisMatch:
        text = self.normalise(message)
        covered = [m.span() for m in self._exceptions.finditer(text)]
        for match in self._phrases.finditer(text):
            start, end = match.span()
            if any(s <= start and end <= e for s, e in covered):
                continue
            phrase = self._compact[re.sub(r"\s", "", match.group(0))]
            return CrisisMatch(True, CRISIS_RULE, self.language[phrase], phrase)
        return CrisisMatch(False)


@lru_cache(maxsize=1)
def _default_checker() -> CrisisChecker:
    return CrisisChecker(get_guardrails().rules.crisis)


def crisis_check(message: str) -> CrisisMatch:
    """Check one message against the packaged crisis phrases."""
    return _default_checker().check(message)
