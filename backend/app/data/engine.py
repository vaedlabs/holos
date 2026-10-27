"""Async engine for the chat path and sync engine for CRUD, with separate pools (Plan C.1).

Both use psycopg 3. Plain `postgresql://` URLs (and old `postgresql+psycopg2://`
ones) are rewritten to `postgresql+psycopg://`, so an existing .env keeps working.
"""

import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Pool sizes are not fixed in the plan; these suit one small server (Plan Part E #11)
ASYNC_POOL = {"pool_size": 10, "max_overflow": 5, "pool_timeout": 5}
SYNC_POOL = {"pool_size": 5, "max_overflow": 5, "pool_timeout": 10}
# Without it, a connection to an unreachable database waits for the OS's TCP
# timeout (75 s measured); a refused one fails at once either way
CONNECT_TIMEOUT_S = 5

_DRIVER_PREFIXES = ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://", "postgres://")


def psycopg_url(url: str) -> str:
    """Rewrite a Postgres URL to use the psycopg 3 driver."""
    for prefix in _DRIVER_PREFIXES:
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    raise ValueError("DATABASE_URL must be a PostgreSQL URL")


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg_url(url)


def make_async_engine(url: str) -> AsyncEngine:
    return create_async_engine(psycopg_url(url), pool_pre_ping=True,
                               connect_args={"connect_timeout": CONNECT_TIMEOUT_S}, **ASYNC_POOL)


def make_sync_engine(url: str) -> Engine:
    return create_engine(psycopg_url(url), pool_pre_ping=True,
                         connect_args={"connect_timeout": CONNECT_TIMEOUT_S}, **SYNC_POOL)


@lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    return make_async_engine(database_url())


@lru_cache(maxsize=1)
def get_sync_engine() -> Engine:
    return make_sync_engine(database_url())


@lru_cache(maxsize=1)
def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False)
