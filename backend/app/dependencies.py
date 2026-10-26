"""FastAPI dependencies: the database, the state store, settings and the signed-in user.

`get_current_user` keeps the name the CRUD routers already use, but reads the
cookie session (Plan C.6) instead of a JWT: no live session → 401, a guest
session → 401 (these pages are for accounts), and every state-changing request
must pass the Origin and CSRF check.
"""

from collections.abc import Generator
from functools import lru_cache

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.data.engine import get_async_engine, get_async_sessionmaker
from app.data.state_store import StateStore
from app.database import get_db
from app.models.user import User
from app.orchestration.principal import SAFE_METHODS, Principal, check_csrf, resolve_principal
from app.orchestration.sessions import Turnstile
from app.routers.errors import ApiError


def get_database() -> Generator[Session, None, None]:
    yield from get_db()


@lru_cache(maxsize=1)
def get_state_store() -> StateStore:
    return StateStore(get_async_engine())


@lru_cache(maxsize=1)
def get_turnstile() -> Turnstile:
    return Turnstile(httpx.AsyncClient())


def _no_session() -> ApiError:
    return ApiError(401, "no_session", "Your session has ended. Please sign in again.")


async def get_principal(
    request: Request,
    store: StateStore = Depends(get_state_store),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """A live session of either mode; state-changing requests also pass CSRF."""
    principal = await resolve_principal(request, store, settings)
    if principal is None:
        raise _no_session()
    if request.method not in SAFE_METHODS:
        check_csrf(request, principal, settings)
    return principal


def get_db_sessions() -> async_sessionmaker[AsyncSession]:
    """Async sessions for the session and login routes; tests point it at the test DB."""
    return get_async_sessionmaker()


async def get_current_user(
    principal: Principal = Depends(get_principal),
    sessions: async_sessionmaker[AsyncSession] = Depends(get_db_sessions),
) -> User:
    if principal.user_id is None:
        raise ApiError(401, "account_required", "Please sign in to your account.")
    async with sessions() as session:
        user = await session.get(User, principal.user_id)
    if user is None:
        raise _no_session()
    if not user.is_active:
        raise ApiError(403, "inactive", "This account is not active.")
    return user
