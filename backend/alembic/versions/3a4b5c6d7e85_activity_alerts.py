"""unresolved_terms.alerted: how much of a count has been flagged (Part E #53)

An activity logged as "other activity" is counted here like an unresolved health phrase
(field "activity"), and the 2-minute job flags what is new since its last run to the
developer, once: it raises `alerted` to `count` as it writes the alert line.

Revision ID: 3a4b5c6d7e85
Revises: 293a4b5c6d74
Create Date: 2026-11-09
"""

import sqlalchemy as sa

from alembic import op

revision = "3a4b5c6d7e85"
down_revision = "293a4b5c6d74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unresolved_terms", sa.Column("alerted", sa.Integer(), nullable=False,
                                                server_default="0"))


def downgrade() -> None:
    op.drop_column("unresolved_terms", "alerted")
