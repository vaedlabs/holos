"""The database tests never pass by being skipped (R3): without TEST_DATABASE_URL the run
stops and says how to fix it, here and in CI alike; leaving them out is asked for by name.

Each test runs pytest in its own process on a copy of the real integration conftest and
pytest.ini, with one database test and one plain test, collecting only."""

import shutil
from pathlib import Path

import pytest

from tests.integration.conftest import MISSING

pytest_plugins = ["pytester"]
pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]
OPT_OUT = "not integration and not paid and not load"


@pytest.fixture
def suite(pytester, monkeypatch):
    shutil.copy(BACKEND / "pytest.ini", pytester.path / "pytest.ini")
    (pytester.path / "tests" / "integration").mkdir(parents=True)
    shutil.copy(BACKEND / "tests" / "integration" / "conftest.py",
                pytester.path / "tests" / "integration" / "conftest.py")
    (pytester.path / "tests" / "integration" / "test_db.py").write_text("def test_db(): pass\n")
    (pytester.path / "tests" / "test_plain.py").write_text("def test_plain(): pass\n")
    monkeypatch.setenv("PYTHONPATH", str(BACKEND))  # the conftest imports the app
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return pytester


def _run(pytester, *args):
    return pytester.runpytest_subprocess("--collect-only", "-p", "no:cacheprovider", *args)


def test_without_the_database_the_run_stops_and_says_how_to_fix_it(suite):
    result = _run(suite)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["ERROR: 1 integration tests need TEST_DATABASE_URL*",
                                 "*backend/.env*.github/workflows/ci.yml*",
                                 f'*pytest -m "{OPT_OUT}"'])


def test_on_github_the_fix_is_on_the_runs_summary_page(suite, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    result = _run(suite)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stdout.fnmatch_lines(["::error title=Database tests can't run::1 integration*%0A*"])


def test_leaving_them_out_by_name_runs_the_rest(suite):
    result = _run(suite, "-m", OPT_OUT)
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(["*test_plain*", "*1/2 tests collected (1 deselected)*"])


def test_with_the_database_they_are_collected(suite, monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://x:y@localhost:5432/holos_test")
    result = _run(suite)
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(["*test_db*", "*test_plain*"])


def test_the_message_keeps_paid_and_load_tests_out():
    """A later -m replaces pytest.ini's: "not integration" alone would run paid calls."""
    assert f'-m "{OPT_OUT}"' in MISSING
