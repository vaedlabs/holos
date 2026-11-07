"""A held log entry waits until the person decides (Plan C.17, Part E #50)

pending_writes.expires_at is NULL while an entry waits: it has no time limit, and a
newer held entry of its kind replaces it. A decided entry keeps its row a day, so a
repeat tap gets the same answer. Entries already past the old 15-minute limit could no
longer be confirmed, so they go; the rest wait.

Revision ID: 18293a4b5c63
Revises: 0718293a4b52
Create Date: 2026-11-07
"""

import sqlalchemy as sa

from alembic import op

revision = "18293a4b5c63"
down_revision = "0718293a4b52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("pending_writes", "expires_at", existing_type=sa.DateTime(timezone=True),
                    nullable=True)
    op.execute("DELETE FROM pending_writes WHERE status = 'pending' AND expires_at <= now()")
    op.execute("UPDATE pending_writes SET expires_at = NULL WHERE status = 'pending'")


def downgrade() -> None:
    op.execute("UPDATE pending_writes SET expires_at = now() + interval '15 minutes' "
                "WHERE expires_at IS NULL")
    op.alter_column("pending_writes", "expires_at", existing_type=sa.DateTime(timezone=True),
                    nullable=False)
