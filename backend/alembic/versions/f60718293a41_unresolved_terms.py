"""Unresolved health phrases for the catalogue review (Plan P4.10, Part E #42, #47)

Revision ID: f60718293a41
Revises: e5f607182930
Create Date: 2026-11-03
"""

import sqlalchemy as sa

from alembic import op

revision = "f60718293a41"
down_revision = "e5f607182930"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unresolved_terms",
        sa.Column("term", sa.String(40), primary_key=True),
        sa.Column("field", sa.String(24), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("unresolved_terms")
