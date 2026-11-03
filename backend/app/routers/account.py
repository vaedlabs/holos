"""Save to an account and the profile check (Plan C.18, Part E #42).

    POST /account/import {import_id, profile, history, logs}  → what was imported
    GET  /profile/check                → account: what the saved text resolved to
    POST /profile/check {notes}        → guest: what the notes name; nothing stored

The profile check reads through `storage.profile`, like a chat turn, so the profile
screen shows exactly what the coaches and the gate will see.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.agents.schemas import ImportPayload, ProfileNotes, UserProfile
from app.config import limits
from app.dependencies import get_db_sessions, get_principal
from app.guardrails.loader import get_guardrails
from app.orchestration.principal import Principal
from app.routers.errors import ApiError
from app.storage.context import Sessions, load_profile
from app.storage.import_guest import import_guest
from app.storage.profile import with_note_terms

router = APIRouter(tags=["account"])


@router.post("/account/import")
async def import_account(
    request: Request,
    principal: Principal = Depends(get_principal),
    sessions: Sessions = Depends(get_db_sessions),
) -> dict:
    user_id = _account(principal)
    if int(request.headers.get("content-length") or 0) > limits.IMPORT_BYTES:
        raise _too_large()
    body = await request.body()
    if len(body) > limits.IMPORT_BYTES:
        raise _too_large()
    try:
        payload = ImportPayload.model_validate_json(body)
    except ValidationError:
        raise ApiError(400, "bad_request", "The saved data couldn't be read, or it holds "
                       f"more than {limits.IMPORT_TURNS} turns or "
                       f"{limits.IMPORT_LOG_ENTRIES} log entries.") from None
    return await import_guest(sessions, user_id, payload)


@router.get("/profile/check")
async def check_saved_profile(
    principal: Principal = Depends(get_principal),
    sessions: Sessions = Depends(get_db_sessions),
) -> dict:
    resolved = await load_profile(sessions, _account(principal))
    return _view(resolved.profile, list(resolved.unchecked))


@router.post("/profile/check")
async def check_notes(body: ProfileNotes, principal: Principal = Depends(get_principal)
                      ) -> dict:
    empty = UserProfile(condition_ids=[], allergen_tags=[], diet_tags=[], notes=body.notes)
    return _view(with_note_terms(empty), [])  # free notes never carry the caveat (#42)


def _view(profile: UserProfile, unchecked: list[str]) -> dict:
    names = {c.id: c.name for c in get_guardrails().catalogue.conditions}
    return {"conditions": [{"id": c, "name": names.get(c, c)} for c in profile.condition_ids],
            "allergens": [str(a) for a in profile.allergen_tags],
            "diets": [str(d) for d in profile.diet_tags],
            "unchecked": unchecked}


def _account(principal: Principal) -> int:
    if principal.user_id is None:
        raise ApiError(401, "account_required", "Please sign in to your account.")
    return principal.user_id


def _too_large() -> ApiError:
    return ApiError(413, "too_large", "The saved data is over 1 MB.")
