"""Account sessions and invites (Plan C.6, C.18).

    POST   /auth/login {email, password}                   → cookie + {mode, csrf_token, ...}
    POST   /auth/logout                                    → this session ends
    POST   /auth/logout-all                                → every session of the user ends
    POST   /invites/accept {token, email, password, consent: true}  → a new account, signed in
    DELETE /auth/delete-account                            → the user and their data

There is no registration: accounts come only from invites (`python -m app.cli
create-invite`). The username is the email address, lowercased (Part E #23).
"""

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.data.state_store import StateStore
from app.dependencies import (
    get_current_user,
    get_database,
    get_db_sessions,
    get_principal,
    get_state_store,
)
from app.models.agent_execution_log import AgentExecutionLog
from app.models.conversation_message import ConversationMessage
from app.models.medical_history import MedicalHistory
from app.models.mental_fitness_log import MentalFitnessLog
from app.models.nutrition_log import NutritionLog
from app.models.state import Invite
from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.models.workout_log import WorkoutLog
from app.orchestration.passwords import (
    get_password_hash,
    password_problem,
    verify_password,
    verify_unknown_user,
)
from app.orchestration.principal import Principal, check_origin
from app.orchestration.sessions import clear_session_cookie, set_session_cookie, start_account

from .errors import ApiError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
invites_router = APIRouter(prefix="/invites", tags=["auth"])

# The privacy note the user agrees to at invite acceptance; bump when its text changes (P7.5)
CONSENT_VERSION = "2026-10-draft"
PASSWORD_MAX_CHARS = 200  # long enough for any passphrase; bytes are checked separately


def _normalise_email(email: str) -> str:
    return email.strip().lower()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_CHARS)


class AcceptInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=16, max_length=128)
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_CHARS)
    consent: bool


def invite_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _signed_in(response: Response, started, user: User, settings: Settings) -> dict:
    set_session_cookie(response, started, settings)
    return {**started.body(settings), "user": {"id": user.id, "email": user.email}}


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    store: StateStore = Depends(get_state_store),
    settings: Settings = Depends(get_settings),
    sessions: async_sessionmaker[AsyncSession] = Depends(get_db_sessions),
) -> dict:
    check_origin(request, settings)
    email = _normalise_email(body.email)
    async with sessions() as db:
        # Older accounts may differ only by case; the oldest one wins
        user = (await db.execute(
            select(User).where(func.lower(User.email) == email).order_by(User.id).limit(1)
        )).scalar_one_or_none()
    # bcrypt takes ~0.25 s of CPU: off the event loop, or every request would wait
    ok = await anyio.to_thread.run_sync(
        (lambda: verify_password(body.password, user.password_hash)) if user
        else (lambda: verify_unknown_user(body.password)))
    if not ok:
        raise ApiError(401, "bad_credentials", "Incorrect email or password.")
    if not user.is_active:
        raise ApiError(403, "inactive", "This account is not active.")
    started = await start_account(request, user.id, store, settings)
    return _signed_in(response, started, user, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    principal: Principal = Depends(get_principal),
    store: StateStore = Depends(get_state_store),
    settings: Settings = Depends(get_settings),
) -> None:
    """Ends this session, guest or account ("Clear my data" ends a guest session)."""
    await store.end_session(principal.raw_session_id)
    clear_session_cookie(response, settings)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    principal: Principal = Depends(get_principal),
    store: StateStore = Depends(get_state_store),
    settings: Settings = Depends(get_settings),
) -> None:
    if principal.user_id is None:
        raise ApiError(401, "account_required", "Please sign in to your account.")
    await store.end_user_sessions(principal.user_id)
    clear_session_cookie(response, settings)


@invites_router.post("/accept")
async def accept_invite(
    body: AcceptInviteRequest,
    request: Request,
    response: Response,
    store: StateStore = Depends(get_state_store),
    settings: Settings = Depends(get_settings),
    sessions: async_sessionmaker[AsyncSession] = Depends(get_db_sessions),
) -> dict:
    check_origin(request, settings)
    if body.consent is not True:
        raise ApiError(400, "consent_required", "Please agree to the privacy note to continue.")
    if problem := password_problem(body.password):
        raise ApiError(400, "weak_password", problem)
    email = _normalise_email(body.email)
    password_hash = await anyio.to_thread.run_sync(get_password_hash, body.password)
    async with sessions() as db:
        async with db.begin():
            invite = (await db.execute(
                select(Invite).where(Invite.token_hash == invite_token_hash(body.token))
                .with_for_update()
            )).scalar_one_or_none()
            if invite is None:
                raise ApiError(404, "invite_not_found", "This invite link isn't valid.")
            if invite.used_at is not None:
                raise ApiError(410, "invite_used", "This invite has already been used.")
            if invite.expires_at <= datetime.now(UTC):
                raise ApiError(410, "invite_expired", "This invite has expired.")
            taken = (await db.execute(
                select(User.id).where(func.lower(User.email) == email)
            )).first()
            if taken:
                raise ApiError(409, "email_taken", "An account with this email already "
                               "exists. Please sign in instead.")
            now = datetime.now(UTC)
            user = User(email=email, username=email, password_hash=password_hash,
                        is_active=True, consent_at=now, consent_version=CONSENT_VERSION)
            db.add(user)
            try:
                await db.flush()
            except IntegrityError:  # the same email accepted at the same moment
                raise ApiError(409, "email_taken", "An account with this email already "
                               "exists. Please sign in instead.") from None
            invite.used_at, invite.used_by = now, user.id
    started = await start_account(request, user.id, store, settings)
    return _signed_in(response, started, user, settings)


@router.delete("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    settings: Settings = Depends(get_settings),
):
    """Deletes the user and every row that references them; sessions cascade.
    P4.9 replaces this with C.18's version (deletion queue, object storage)."""
    try:
        user_id = current_user.id
        for image_file in Path("uploads/images").glob(f"{user_id}_*.jpg"):
            try:
                image_file.unlink()
            except OSError as e:
                logger.warning("Failed to delete image file %s: %s", image_file, e)
        for model in (ConversationMessage, WorkoutLog, NutritionLog, MentalFitnessLog,
                      MedicalHistory, UserPreferences, AgentExecutionLog):
            db.query(model).filter(model.user_id == user_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("account deletion failed")
        raise ApiError(500, "delete_failed", "We couldn't delete your account. "
                       "Please try again.") from None
    clear_session_cookie(response, settings)
