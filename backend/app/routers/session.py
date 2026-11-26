"""Guest sessions and the CSRF token (Plan C.6).

    POST /session/start {turnstile_token}  → cookie + {mode, csrf_token, expires_at}
    GET  /session/csrf                     → the token for the current session (a new tab)
"""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import Settings, get_settings
from app.data.state_store import StateStore
from app.dependencies import get_principal, get_state_store, get_turnstile
from app.orchestration.principal import Principal, check_origin
from app.orchestration.sessions import (
    TURNSTILE_TOKEN_MAX,
    SessionView,
    Turnstile,
    session_view,
    set_session_cookie,
    start_guest,
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
) -> SessionView:
    check_origin(request, settings)  # no session yet, so no CSRF token to check
    started = await start_guest(request, body.turnstile_token, store, turnstile, settings)
    set_session_cookie(response, started, settings)
    return started.body(settings)


@router.get("/csrf")
async def csrf(
    principal: Principal = Depends(get_principal), settings: Settings = Depends(get_settings)
) -> SessionView:
    return session_view(principal.raw_session_id, principal.session, settings)
