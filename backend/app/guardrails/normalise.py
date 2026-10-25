"""Text normalisation shared by the loader, the matcher and the crisis check."""

import re
import unicodedata

ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
WHITESPACE = re.compile(r"\s+")


def normalise_text(text: str) -> str:
    """NFKC, lowercase, remove zero-width characters, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = ZERO_WIDTH.sub("", text)
    return WHITESPACE.sub(" ", text).strip()
