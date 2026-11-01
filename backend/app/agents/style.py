"""How a person writes, told to the coach each turn (Part D: 5 of 374 replies came back in
English to someone writing Hinglish or Hindi). Deterministic."""

import re
import unicodedata
from typing import Literal

Style = Literal["hindi", "hinglish", "english"]

# Common Hindi words in Latin letters that aren't also English or Spanish words ("me",
# "do", "de" are left out: live, they made 46 English messages look Hinglish)
HINGLISH_WORDS = frozenset({
    "hai", "hain", "hoon", "hu", "ho", "tha", "thi", "kya", "kyun", "kyu", "kaise", "kaisa",
    "nahi", "nahin", "mein", "mujhe", "mera", "meri", "mere", "tum", "aap", "ka", "ki",
    "ke", "ko", "se", "aur", "bhi", "bahut", "thoda", "thodi", "kuch", "karo", "kar", "karna",
    "karu", "karun", "chahiye", "abhi", "aaj", "kal", "raat", "din", "yaar", "bhai", "toh",
    "lekin", "wala", "wali", "bata", "batao", "dena", "sakta", "sakti",
    "rha", "rhi", "raha", "rahi", "gaya", "gayi", "hota", "hoti", "lagta", "lagti", "khana",
    "khaya", "kiya", "piya", "liya", "diya", "hua", "hui", "haan", "accha", "acha", "theek",
    "thik", "kitna", "kitni", "kab", "kahan", "kyunki", "matlab", "sab", "koi", "wapas",
    "yeh", "woh", "isse", "usse", "tak", "jaata", "jaati", "karte", "karti", "chal",
})
_WORD = re.compile(r"[^\W\d_]+")
STYLE_NOTE = {
    "hindi": "They write in Hindi (Devanagari): reply in Hindi, in Devanagari.",
    "hinglish": "They write in Hinglish: reply in Hinglish, in Latin letters.",
    "english": "They write in English: reply in English.",
}


def letters(text: str) -> list[str]:
    """Letters and combining marks: Devanagari vowel signs aren't isalpha() (Part D)."""
    return [c for c in text if c.isalpha() or unicodedata.category(c).startswith("M")]


def writing_style(text: str) -> Style:
    letters_ = letters(text)
    devanagari = sum(unicodedata.name(c, "").startswith("DEVANAGARI") for c in letters_)
    if letters_ and devanagari * 2 > len(letters_):
        return "hindi"
    words = [w.lower() for w in _WORD.findall(text)]
    hinglish = sum(w in HINGLISH_WORDS for w in words)
    # Two Hindi words, or one in a short message ("neend?")
    return "hinglish" if hinglish >= 2 or (hinglish and len(words) <= 3) else "english"
