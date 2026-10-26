"""Record consent on users at invite acceptance (Plan C.18, Part E #23)

Revision ID: b7c1d2e3f405
Revises: 74b3be8d6801
Create Date: 2026-10-26
"""

import sqlalchemy as sa

from alembic import op

revision = "b7c1d2e3f405"
down_revision = "74b3be8d6801"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("consent_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "consent_version")
    op.drop_column("users", "consent_at")
