"""Text normalisation shared by the loader, the matcher and the crisis check."""

import re
import unicodedata

ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
WHITESPACE = re.compile(r"\s+")


CURLY_APOSTROPHE = re.compile("[‘’ʼ]")
JOINERS = re.compile(r"[-_/]")


def normalise_text(text: str) -> str:
    """NFKC, lowercase, remove zero-width characters, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = ZERO_WIDTH.sub("", text)
    return WHITESPACE.sub(" ", text).strip()


def fold_for_matching(text: str) -> str:
    """normalise_text, plus straight apostrophes and hyphens as spaces, so "push-up",
    "push up" and "don’t" match "push up" and "don't"."""
    text = CURLY_APOSTROPHE.sub("'", normalise_text(text))
    return WHITESPACE.sub(" ", JOINERS.sub(" ", text)).strip()


# --- Crisis normalisation (Plan C.16) ---
# Every step is driven by the `normalise` section of rules.yaml and published in
# contracts/crisis.json, so lib/crisis.js can run the same steps in the same order.

# Letters, digits, underscore and combining marks. Devanagari vowel signs are
# marks, not \w, so "चाहत" must not match inside "चाहता" (Plan Part D).
WORD_CHAR = r"[\w\u0300-\u036f\u0900-\u097f]"
_SEPARATOR = r"[.\-\s]+"
_LETTER = r"[^\W\d_]"
# Three or more single letters split by dots, dashes or spaces: "k.i.l.l", "s u i c i d e"
_SPLIT_LETTERS = re.compile(
    rf"(?<!{WORD_CHAR}){_LETTER}(?!{WORD_CHAR})(?:{_SEPARATOR}{_LETTER}(?!{WORD_CHAR})){{2,}}"
)
_SEPARATOR_RE = re.compile(_SEPARATOR)
# "a" and "I" are words on their own: never joined to a neighbour across a space
_SOLO_WORDS = frozenset({"a", "i"})


def join_split_letters(text: str) -> str:
    def join(match: re.Match) -> str:
        run = match.group(0)
        letters = _SEPARATOR_RE.split(run)
        seps = _SEPARATOR_RE.findall(run)
        head = tail = ""
        if letters[0] in _SOLO_WORDS and seps[0].isspace():
            head, letters, seps = letters[0] + " ", letters[1:], seps[1:]
        if len(letters) > 1 and letters[-1] in _SOLO_WORDS and seps[-1].isspace():
            tail, letters = " " + letters[-1], letters[:-1]
        if len(letters) < 3:
            return run
        return head + "".join(letters) + tail

    return _SPLIT_LETTERS.sub(join, text)


def _alternation(keys) -> str:
    return "|".join(re.escape(k) for k in sorted(keys, key=len, reverse=True))


class CrisisNormaliser:
    """In order: NFKC, lowercase, zero-width characters removed, `chars` (apostrophes
    dropped, Devanagari spellings folded), `leet` anywhere, `leet_inner` only between
    two letters ("d!e" but not "die!"), split letters joined, `words` (spelling
    variants and contractions, whole words only), whitespace collapsed."""

    def __init__(self, leet: dict[str, str], leet_inner: dict[str, str] | None = None,
                 chars: dict[str, str] | None = None, words: dict[str, str] | None = None):
        self.chars = str.maketrans(chars or {})
        self.leet = str.maketrans(leet)
        self.leet_inner = leet_inner or {}
        self._inner = (
            re.compile(rf"(?<=[^\W\d_])({_alternation(self.leet_inner)})(?=[^\W\d_])")
            if self.leet_inner else None
        )
        # Keys are compared after `chars`, so "don't" or a nukta spelling works as a key
        self.words = {
            normalise_text(k).translate(self.chars): v for k, v in (words or {}).items()
        }
        self._words = (
            re.compile(rf"(?<!{WORD_CHAR})({_alternation(self.words)})(?!{WORD_CHAR})")
            if self.words else None
        )

    def __call__(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text).lower()
        text = ZERO_WIDTH.sub("", text).translate(self.chars).translate(self.leet)
        if self._inner:
            text = self._inner.sub(lambda m: self.leet_inner[m.group(1)], text)
        text = join_split_letters(WHITESPACE.sub(" ", text))
        if self._words:
            text = self._words.sub(lambda m: self.words[m.group(1)], text)
        return WHITESPACE.sub(" ", text).strip()
