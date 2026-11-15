"""A turn's profile and history, and saving it, in either storage mode (Plan C.8).

    turn = await load_context(principal, payload, sessions)   # profile, history, unchecked
    await save_turn(principal, sessions, payload, assistant_turn)   # accounts only
    await save_display(sessions, user_id, trace_id, composer.shown)  # before `done`
    resolved = await load_profile(sessions, user_id)         # an account's, alone

Guest: both come from the payload, and nothing is stored on the server; only the
history's signed, unchanged exchanges are used (Part E #63). Account: the
saved profile resolved to IDs (`storage.profile`) and the last 6 messages, through
user-scoped repositories that take the user from the session, never from the request.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.schemas import AgentName, ChatPayload, HistoryTurn, UserProfile
from app.data.repositories.messages import MessageRepository
from app.data.repositories.profile import ProfileRepository
from app.data.state_store import card_states
from app.models import ConversationMessage
from app.orchestration.principal import Principal
from app.storage.guest_history import verified
from app.storage.profile import Resolved, resolve_profile, with_note_terms

HISTORY_TURNS = 6
TURN_CHARS = 2000
AGENTS: tuple[AgentName, ...] = ("physical", "nutrition", "mental")

Sessions = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class TurnContext:
    profile: UserProfile | None
    history: list[HistoryTurn]
    unchecked: tuple[str, ...] = ()  # health text the gate can't check (C.8)
    chain: str | None = None  # a guest's newest signed exchange (Part E #63)


async def load_context(principal: Principal, payload: ChatPayload, sessions: Sessions | None
                       ) -> TurnContext:
    if principal.user_id is None:
        # Only the signed exchanges the browser left unchanged (Part E #63)
        history, chain = verified(list(payload.guest_history or []))
        return TurnContext(with_note_terms(payload.guest_profile), history, chain=chain)
    async with sessions() as session:
        resolved = await _resolved(session, principal.user_id)
        rows = await MessageRepository(session, principal.user_id).recent(HISTORY_TURNS)
    return TurnContext(resolved.profile, [_turn(row) for row in rows], resolved.unchecked)


async def load_profile(sessions: Sessions, user_id: int) -> Resolved:
    async with sessions() as session:
        return await _resolved(session, user_id)


async def _resolved(session: AsyncSession, user_id: int) -> Resolved:
    profiles = ProfileRepository(session, user_id)
    return resolve_profile(await profiles.get_medical(), await profiles.get_preferences())


def _turn(row) -> HistoryTurn:
    agents = None
    if row.role == "assistant":
        agents = [a for a in AGENTS if a in (row.agents or ())] or None
    return HistoryTurn(role=row.role, content=(row.content or "")[:TURN_CHARS], agents=agents,
                       ts=row.created_at)


async def save_turn[T](principal: Principal, sessions: Sessions,
                       client_request_id: uuid.UUID, message: str, turn: HistoryTurn,
                       also: Callable[[AsyncSession], Awaitable[T]] | None = None,
                       image_key: str | None = None, trace_id: str | None = None
                       ) -> T | None:
    """The person's message and the answer's history text, in one transaction (C.2
    stage 13), with `also` (the turn's writes) in the same one. The message carries
    `client_request_id`: its unique key is the second lock against a request answered
    twice (C.5). What the person saw follows with `save_display`."""
    async with sessions() as session, session.begin():
        messages = MessageRepository(session, principal.user_id)
        await messages.add("user", message, image_path=image_key,
                           client_request_id=client_request_id)
        await messages.add("assistant", turn.content, agents=turn.agents, trace_id=trace_id)
        return await also(session) if also is not None else None


async def save_display(sessions: Sessions, user_id: int, trace_id: str,
                       shown: list[dict]) -> None:
    """What the person saw (C.5 History), after the turn's last card and before `done`.
    Each held entry's card takes its entry's state under the entry's row lock, the lock
    a decision takes first, so a Confirm tapped meanwhile is never lost (C.17)."""
    ids = [e["data"]["write_id"] for e in shown if e["event"] == "pending_write"]
    async with sessions() as session, session.begin():
        states = await card_states(await session.connection(), user_id, ids)
        display = [{**e, "data": {**e["data"], "state": states[e["data"]["write_id"]]}}
                   if e["event"] == "pending_write" else e for e in shown]
        await session.execute(
            update(ConversationMessage)
            .where(ConversationMessage.user_id == user_id,
                   ConversationMessage.trace_id == trace_id,
                   ConversationMessage.role == "assistant")
            .values(display=display))
