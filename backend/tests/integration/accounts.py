"""An app with the account routes on the test database, and requests as a principal."""

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config.settings import get_settings
from app.dependencies import get_db_sessions, get_engine, get_image_store, get_state_store
from app.orchestration.principal import csrf_token
from app.routers import account, auth, conversation
from app.routers.errors import ApiError, api_error_handler

from .test_admission import APP, settings


def account_app(store, async_engine, images) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    for r in (account.router, auth.router, auth.invites_router, conversation.router):
        app.include_router(r)
    db = async_sessionmaker(async_engine, expire_on_commit=False)
    cfg = settings()
    app.dependency_overrides.update({
        get_settings: lambda: cfg, get_state_store: lambda: store, get_db_sessions: lambda: db,
        get_engine: lambda: async_engine, get_image_store: lambda: images})
    return app


async def call(app, principal, method, path, **kw) -> httpx.Response:
    cfg = settings()
    headers = {"origin": APP, **kw.pop("headers", {})}
    cookies = {}
    if principal is not None:
        headers["x-csrf-token"] = csrf_token(principal.raw_session_id, cfg)
        cookies[cfg.session_cookie] = principal.raw_session_id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://testserver", cookies=cookies) as client:
        return await client.request(method, path, headers=headers, **kw)
