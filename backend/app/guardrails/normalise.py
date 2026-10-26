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

