"""Guest sessions and the CSRF token (Plan C.6).

    POST /session/start {turnstile_token}  → cookie + {mode, csrf_token, expires_at}
    GET  /session/csrf                     → the token for the current session (a new tab)
"""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import Settings, get_settings
from app.data.state_store import StateStore
from app.dependencies import get_principal, get_state_store, get_turnstile
from app.orchestration.principal import Principal, check_origin, csrf_token
from app.orchestration.sessions import (
    TURNSTILE_TOKEN_MAX,
    Turnstile,
    set_session_cookie,
    start_guest,
    utc_iso,
)

router = APIRouter(prefix="/session", tags=["session"])


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turnstile_token: str = Field(min_length=1, max_length=TURNSTILE_TOKEN_MAX)


@router.post("/start")
async def start(
    body: StartRequest,
    request: Request,
    response: Response,
    store: StateStore = Depends(get_state_store),
    turnstile: Turnstile = Depends(get_turnstile),
    settings: Settings = Depends(get_settings),
) -> dict:
    check_origin(request, settings)  # no session yet, so no CSRF token to check
    started = await start_guest(request, body.turnstile_token, store, turnstile, settings)
    set_session_cookie(response, started, settings)
    return started.body(settings)


@router.get("/csrf")
async def csrf(
    principal: Principal = Depends(get_principal), settings: Settings = Depends(get_settings)
) -> dict:
    return {"mode": principal.mode, "csrf_token": csrf_token(principal.raw_session_id, settings),
            "expires_at": utc_iso(principal.session.expires_at)}
