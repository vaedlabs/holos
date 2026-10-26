"""Admin commands (Plan C.18).

    python -m app.cli create-invite [--by NAME]

Prints a single-use invite link, valid for 7 days. Only the token's hash is stored,
so a lost link can't be recovered: make a new one.
"""

import argparse
import asyncio
import secrets
import sys
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import limits
from app.config.settings import get_settings
from app.data.engine import get_async_sessionmaker
from app.models.state import Invite
from app.routers.auth import invite_token_hash


async def create_invite(
    created_by: str, sessions: async_sessionmaker[AsyncSession] | None = None
) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + limits.INVITE_TTL
    async with (sessions or get_async_sessionmaker())() as db, db.begin():
        db.add(Invite(token_hash=invite_token_hash(token), created_by=created_by,
                      expires_at=expires_at))
    return token, expires_at


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    invite = commands.add_parser("create-invite", help="print a single-use invite link")
    invite.add_argument("--by", default="cli", help="who the invite is from (a label)")
    args = parser.parse_args(argv)

    if args.command == "create-invite":
        token, expires_at = asyncio.run(create_invite(args.by[:64]))
        print(f"{get_settings().app_origin}/invite/{token}")
        print(f"Single use; expires {expires_at:%Y-%m-%d %H:%M} UTC.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
