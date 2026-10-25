"""Integration tests run against TEST_DATABASE_URL, never the dev database (Plan A.3)."""

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

load_dotenv()

BACKEND = Path(__file__).resolve().parents[2]
TEST_URL = os.getenv("TEST_DATABASE_URL")
OLD_HEAD = "cd5e821b7af6"  # head before Plan P1.3


def pytest_collection_modifyitems(items):
    here = Path(__file__).parent
    for item in items:
        if here in Path(item.fspath).parents:
            item.add_marker(pytest.mark.integration)
            if not TEST_URL:
                item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL is not set"))


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
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def async_engine(clean):
    eng = make_async_engine(TEST_URL)
    yield eng
    await eng.dispose()
