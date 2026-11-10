"""Every file ruff leaves out must still exist: a deleted or moved file comes off the list
(Plan Part E #3), or the list hides what it no longer names."""

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]


def test_every_file_ruff_leaves_out_exists():
    excluded = tomllib.loads((BACKEND / "ruff.toml").read_text())["extend-exclude"]
    assert excluded  # the list is read, not silently empty
    assert [path for path in excluded if not (BACKEND / path).exists()] == []
