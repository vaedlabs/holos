from sqlalchemy.ext.asyncio import AsyncSession


class UserScopedRepository:
    """Holds the session and the one user this repository may read and write."""

    def __init__(self, session: AsyncSession, user_id: int):
        self._session = session
        self._user_id = user_id

    def _fields(self, fields: dict, allowed: set[str]) -> dict:
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown fields: {sorted(unknown)}")
        return fields
