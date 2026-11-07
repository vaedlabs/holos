"""The failure library (`app/observability/failures.yaml`, Part E #55) stays complete:
every cause the tracer can record has an entry, every entry names tests that exist (or
says why it has none), and every error and notice the person can see belongs to one."""

import ast
import warnings
from collections import Counter
from functools import cache
from pathlib import Path

import pytest
import yaml

from app.observability.tracer import CAUSES
from app.orchestration.composer import ERRORS, NOTICES

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]
LIBRARY = BACKEND / "app" / "observability" / "failures.yaml"
LAYERS = {"provider", "stream", "tools", "data", "process", "storage", "external", "safety",
          "jobs"}
REQUIRED = ("id", "layer", "what", "cause", "handling", "person_sees", "code", "tests",
            "seen_live")


@cache
def entries() -> list[dict]:
    return yaml.safe_load(LIBRARY.read_text(encoding="utf-8"))["failures"]


@cache
def _tests_in(path: str) -> frozenset[str]:
    tree = ast.parse((BACKEND / path).read_text(encoding="utf-8"))
    return frozenset(n.name for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                     and n.name.startswith("test_"))


def test_every_entry_is_complete():
    problems = []
    for e in entries():
        missing = [k for k in REQUIRED if k not in e]
        empty = [k for k in ("id", "what", "handling", "person_sees") if not e.get(k)]
        if missing or empty or e.get("layer") not in LAYERS:
            problems.append((e.get("id"), missing, empty, e.get("layer")))
    assert problems == []
    assert [i for i, n in Counter(e["id"] for e in entries()).items() if n > 1] == []


def test_every_cause_has_an_entry_and_no_entry_invents_one():
    used = {e["cause"] for e in entries()}
    assert CAUSES - used == set(), "causes the tracer can record but the library lacks"
    assert used - CAUSES - {"none"} == set(), "causes the tracer doesn't know"


def test_every_named_test_exists():
    missing = []
    for e in entries():
        for node in e["tests"] or []:
            path, _, name = node.partition("::")
            if not (BACKEND / path).exists() or name not in _tests_in(path):
                missing.append((e["id"], node))
    assert missing == []


def test_an_entry_without_tests_says_why():
    untested = [e["id"] for e in entries() if not e["tests"] and not e.get("gap")]
    assert untested == []
    for e in entries():
        if e.get("gap"):  # a known gap stays visible in every run
            warnings.warn(f"failure library gap: {e['id']}: {e['gap']}", stacklevel=1)


def test_everything_the_person_can_be_told_is_in_the_library():
    codes = {e["code"] for e in entries()}
    assert (set(ERRORS) | set(NOTICES)) - codes == set()


def test_the_check_catches_a_missing_test(tmp_path, monkeypatch):
    """The checks above can fail: a test name that doesn't exist is found."""
    monkeypatch.setattr("tests.unit.test_failure_library.entries", lambda: [
        {"id": "x", "tests": ["tests/unit/test_failure_library.py::test_no_such_test"]}])
    with pytest.raises(AssertionError):
        test_every_named_test_exists()
