"""A turn's profile and history, and saving it, in either storage mode (Plan C.8).

    profile, history = await load_context(principal, payload, sessions)
    await save_turn(principal, sessions, payload, assistant_turn)   # accounts only

Guest: both come from the payload, and nothing is stored on the server. Account: the
saved profile resolved to IDs (`storage.profile`) and the last 6 messages, through
user-scoped repositories that take the user from the session, never from the request.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.schemas import AgentName, ChatPayload, HistoryTurn, UserProfile
from app.data.repositories.messages import MessageRepository
from app.data.repositories.profile import ProfileRepository
from app.orchestration.principal import Principal
from app.storage.profile import resolve_profile

HISTORY_TURNS = 6
TURN_CHARS = 2000
AGENTS: tuple[AgentName, ...] = ("physical", "nutrition", "mental")
# The old app's agent_type values
_OLD_AGENTS = {"physical-fitness": "physical", "mental-fitness": "mental",
               "nutrition": "nutrition"}

Sessions = async_sessionmaker[AsyncSession]


async def load_context(principal: Principal, payload: ChatPayload, sessions: Sessions | None
                       ) -> tuple[UserProfile | None, list[HistoryTurn]]:
    if principal.user_id is None:
        return payload.guest_profile, list(payload.guest_history or [])
    async with sessions() as session:
        profiles = ProfileRepository(session, principal.user_id)
        profile = resolve_profile(await profiles.get_medical(), await profiles.get_preferences())
        rows = await MessageRepository(session, principal.user_id).recent(HISTORY_TURNS)
    return profile, [_turn(row) for row in rows]


def _turn(row) -> HistoryTurn:
    agents = None
    if row.role == "assistant":
        names = [_OLD_AGENTS.get(a.strip(), a.strip()) for a in (row.agent_type or "").split(",")]
        agents = [a for a in AGENTS if a in names] or None
    return HistoryTurn(role=row.role, content=(row.content or "")[:TURN_CHARS], agents=agents,
                       ts=row.created_at)


async def save_turn(principal: Principal, sessions: Sessions, client_request_id: uuid.UUID,
                    message: str, turn: HistoryTurn) -> None:
    """The person's message and what they saw, in one transaction (C.2 stage 13). The
    message carries `client_request_id`: its unique key is the second lock against a
    request answered twice (C.5)."""
    async with sessions() as session, session.begin():
        messages = MessageRepository(session, principal.user_id)
        await messages.add("user", message, agent_type="user",
                           client_request_id=client_request_id)
        await messages.add("assistant", turn.content,
                           agent_type=",".join(turn.agents or []) or "holos")
