"""Integration tests run against TEST_DATABASE_URL, never the dev database (Plan A.3)."""

import asyncio
import os
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command
from app.data.engine import make_async_engine, psycopg_url
from app.observability import background
from app.orchestration import worker

load_dotenv()

BACKEND = Path(__file__).resolve().parents[2]
TEST_URL = os.getenv("TEST_DATABASE_URL")
OLD_HEAD = "cd5e821b7af6"  # head before Plan P1.3


HERE = Path(__file__).parent
# Without the test database the run stops, here and in CI alike: skipped, these tests
# would let a renamed or deleted setting pass with a green tick (R3). Leaving them out is
# asked for by name; a later -m replaces pytest.ini's, so it keeps paid and load out too
MISSING = (
    "{n} integration tests need TEST_DATABASE_URL, and it is not set.\n"
    "To run them: on your machine, set it in backend/.env (the line is in "
    "backend/.env.example); in CI, the backend job in .github/workflows/ci.yml sets it "
    "under env:, next to the postgres service: put the line back, or match its name to "
    "backend/.env.example.\n"
    'To leave them out on purpose: pytest -m "not integration and not paid and not load"'
)


def _integration(item) -> bool:
    return HERE in Path(item.fspath).parents


@pytest.hookimpl(tryfirst=True)  # before -m deselects by this marker
def pytest_collection_modifyitems(items):
    for item in items:
        if _integration(item):
            item.add_marker(pytest.mark.integration)


def pytest_collection_finish(session):
    """After -m: stop only when integration tests are still in the run."""
    n = sum(1 for item in session.items if _integration(item))
    if TEST_URL or not n:
        return
    if os.getenv("GITHUB_ACTIONS") == "true":  # the fix, on the run's summary page
        out = session.config.get_terminal_writer()
        out.line()  # GitHub reads the notice only at the start of a line, not after "collecting"
        out.line("::error title=Database tests can't run::"
                 + MISSING.format(n=n).replace("\n", "%0A"))
    raise pytest.UsageError(MISSING.format(n=n))


def _guard(url: str) -> None:
    """Refuse to run against the database the app uses."""
    dev = os.getenv("DATABASE_URL")
    if dev and make_url(psycopg_url(dev)).database == make_url(psycopg_url(url)).database:
        raise RuntimeError("TEST_DATABASE_URL must not point at the DATABASE_URL database")


def alembic(action: str, revision: str) -> None:
    """Run an Alembic command against the test database."""
    cfg = Config()  # no ini file, so env.py leaves logging alone
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["url"] = TEST_URL
    getattr(command, action)(cfg, revision)


@pytest.fixture(scope="session")
def engine():
    _guard(TEST_URL)
    eng = create_engine(psycopg_url(TEST_URL))
    yield eng
    eng.dispose()


def reset_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="session")
def migrated(engine):
    """A test database at head, built once per run."""
    reset_schema(engine)
    alembic("upgrade", "head")
    return engine


@pytest.fixture
def clean(migrated):
    """Empty every table after the test."""
    yield migrated
    with migrated.begin() as conn:
        tables = conn.execute(text(
            "SELECT string_agg(quote_ident(tablename), ', ') FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        )).scalar()
        # Another run on this database, or a leaked transaction, fails here instead of
        # hanging the run
        conn.execute(text("SET LOCAL lock_timeout = '60s'"))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def async_engine(clean):
    eng = make_async_engine(TEST_URL)
    yield eng
    await _finish_background_work()
    await eng.dispose()


async def _finish_background_work() -> None:
    """A chat request or trace write still running when the test's loop closes would hold
    its transaction open, and `clean`'s TRUNCATE (which blocks the loop) would wait for it
    forever. Requests first: they record their traces as they end."""
    loop = asyncio.get_running_loop()
    for tasks in (worker._running, background._pending):
        if mine := {t for t in tasks if t.get_loop() is loop}:
            _, late = await asyncio.wait(mine, timeout=30)
            for task in late:  # cancelled: its connection rolls back and is returned
                task.cancel()
            await asyncio.gather(*late, return_exceptions=True)
