"""Accounts are active unless deactivated: users.is_active is never NULL (Plan C.6)

A NULL was read as inactive by some checks and as active by none, so a row inserted
without the column locked its account out. Existing NULLs become true.

Revision ID: 0718293a4b52
Revises: f60718293a41
Create Date: 2026-11-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0718293a4b52"
down_revision = "f60718293a41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET is_active = true WHERE is_active IS NULL")
    op.alter_column("users", "is_active", existing_type=sa.Boolean(), nullable=False,
                    server_default=sa.true())


def downgrade() -> None:
    op.alter_column("users", "is_active", existing_type=sa.Boolean(), nullable=True,
                    server_default=None)
