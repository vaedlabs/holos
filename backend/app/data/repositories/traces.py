from typing import Any

from sqlalchemy import select

from app.models import GateDecision, Trace

from .base import UserScopedRepository


class TraceRepository(UserScopedRepository):
    """The user's request traces and the gate decisions inside them."""

    async def add(
        self,
        trace_id: str,
        route: str,
        steps: list[dict[str, Any]],
        usage: dict[str, Any],
        success: bool,
        session_id_hash: str | None = None,
    ) -> Trace:
        row = Trace(
            trace_id=trace_id, user_id=self._user_id, route=route, steps=steps, usage=usage,
            success=success, session_id_hash=session_id_hash,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, trace_id: str) -> Trace | None:
        return await self._session.scalar(
            select(Trace).where(Trace.trace_id == trace_id, Trace.user_id == self._user_id)
        )

    async def recent(self, n: int = 20) -> list[Trace]:
        rows = await self._session.scalars(
            select(Trace)
            .where(Trace.user_id == self._user_id)
            .order_by(Trace.created_at.desc(), Trace.trace_id)
            .limit(n)
        )
        return list(rows)

    async def add_decisions(self, trace_id: str, decisions: list[dict[str, Any]]) -> None:
        """Store gate decisions (rule_id, rules_version, action, item, reason)."""
        self._session.add_all(
            GateDecision(trace_id=trace_id, user_id=self._user_id, **d) for d in decisions
        )
        await self._session.flush()

    async def decisions(self, trace_id: str) -> list[GateDecision]:
        rows = await self._session.scalars(
            select(GateDecision)
            .where(GateDecision.trace_id == trace_id, GateDecision.user_id == self._user_id)
            .order_by(GateDecision.id)
        )
        return list(rows)
