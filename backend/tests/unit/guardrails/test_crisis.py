"""The crisis check (Plan C.16) passes every shared case, offline and fast."""

import json
import socket
import time
from pathlib import Path

import pytest

from app.guardrails.crisis import CRISIS_RULE, CrisisChecker, crisis_check
from app.guardrails.loader import get_guardrails
from app.guardrails.normalise import CrisisNormaliser

pytestmark = pytest.mark.unit

CONTRACTS = Path(__file__).parents[4] / "contracts"
CASES = [json.loads(line) for line in (CONTRACTS / "crisis_cases.jsonl").read_text(
    encoding="utf-8").splitlines() if line.strip()]
NORMALISE = get_guardrails().rules.crisis.normalise.normaliser()
PHRASES = {NORMALISE(p) for ps in get_guardrails().rules.crisis.phrases.values() for p in ps}


def test_case_file_has_enough_of_each():
    assert sum(c["expect"] for c in CASES) >= 15
    assert sum(not c["expect"] for c in CASES) >= 15
    assert all(set(c) == {"text", "expect", "note"} for c in CASES)


@pytest.mark.parametrize("case", CASES, ids=[c["note"] for c in CASES])
def test_shared_case(case):
    result = crisis_check(case["text"])
    assert result.matched is case["expect"], case
    if result.matched:
        assert result.rule_id == CRISIS_RULE
        assert result.language in {"en", "hi_latn", "hi_deva"}
        assert result.phrase in PHRASES


def test_result_names_the_phrase_not_the_message():
    result = crisis_check("my day was awful and honestly I want to die tonight")
    assert result.phrase == "want to die"
    assert result.language == "en"
    assert crisis_check("main khudkushi kar lunga").language == "hi_latn"
    assert crisis_check("मैं आत्महत्या करना चाहता हूं").language == "hi_deva"


@pytest.mark.parametrize(("text", "expected"), [
    ("K.I.L.L   myself", "kill myself"),
    ("s-u-1-c-1-d-e", "suicide"),  # leetspeak first, then joined
    ("i k i l l", "i kill"),  # a lone "i" at the edge stays a word
    ("I a m tired", "i a m tired"),
    ("go to the g y m", "go to the gym"),
    ("vitamin b12", "vitamin bi2"),
    ("ki\u200bll ｍyself", "kill myself"),
    ("d!e w4nt", "die want"),  # leetspeak between letters
    ("die! 4 sets", "die! 4 sets"),  # ... but not at a word's edge
    ("I don't, I don’t", "i do not, i do not"),  # apostrophes dropped, then folded
    ("wanna kill-myself", "want to kill myself"),
    ("kill my self", "kill myself"),
    ("khud khushi", "khudkushi"),
    ("mai mar jaaungi", "mai mar jaungi"),
    ("मैं मर जाउँगा", "मैं मर जाऊंगा"),  # chandrabindu and short u
    ("ज़िंदगी ख़त्म", "जिंदगी खत्म"),  # nukta dropped
    ("skill myself", "skill myself"),  # words fold whole words only
])
def test_normalise(text, expected):
    assert NORMALISE(text) == expected


def test_word_fold_keys_pass_through_chars():
    # A key written with an apostrophe or a hyphen still matches the normalised text
    normalise = CrisisNormaliser({}, chars={"'": "", "-": " "},
                                 words={"can't": "can not", "self-harm": "selfharm"})
    assert normalise("I can't stop self-harm") == "i can not stop selfharm"


def test_every_phrase_matches_itself_and_its_written_forms():
    crisis = get_guardrails().rules.crisis
    for phrases in crisis.phrases.values():
        for phrase in phrases:
            assert crisis_check(phrase).matched, phrase
            assert crisis_check(f"honestly, {phrase.upper()}.").matched, phrase


def test_devanagari_vowel_signs_are_part_of_a_word():
    # "चाहत" (desire) must not match inside "चाहता", though Python's \w skips vowel signs
    crisis = get_guardrails().rules.crisis
    checker = CrisisChecker(crisis.model_copy(update={"phrases": {
        **crisis.phrases, "hi_deva": ["चाहत"]}}))
    assert not checker.check("मैं घर जाना चाहता हूं").matched
    assert checker.check("उसकी चाहत").matched


def test_an_exception_only_covers_its_own_match():
    assert not crisis_check("suicide sprints and suicide drills today").matched
    assert crisis_check("suicide drills make me suicidal").matched


def test_no_network_or_llm_call(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the crisis check must not use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    for case in CASES:
        assert crisis_check(case["text"]).matched is case["expect"]


def test_under_5_ms_per_message():
    crisis_check("warm up")  # build the checker once
    longest = "honestly " * 220  # a 2,000-character message, the ChatPayload limit
    messages = [c["text"] for c in CASES] + [longest[:2000], ("a b " * 500)[:2000]]
    for message in messages:
        start = time.perf_counter()
        for _ in range(20):
            crisis_check(message)
        per_call_ms = (time.perf_counter() - start) / 20 * 1000
        assert per_call_ms < 5, (message[:40], per_call_ms)
