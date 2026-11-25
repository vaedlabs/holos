"""mental_fitness_logs: the mood rating goes (Part E #73)

The coach guessed `mood_before` and `mood_after` from the person's words; the owner
scrapped the rating (25 Nov 2026), so the columns and what older rows held in them go.

Revision ID: 5c6d7e8f9a07
Revises: 4b5c6d7e8f96
Create Date: 2026-11-25
"""

import sqlalchemy as sa

from alembic import op

revision = "5c6d7e8f9a07"
down_revision = "4b5c6d7e8f96"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("mental_fitness_logs", "mood_before")
    op.drop_column("mental_fitness_logs", "mood_after")


def downgrade() -> None:
    # The columns come back empty: what they held is gone
    op.add_column("mental_fitness_logs", sa.Column("mood_before", sa.String(), nullable=True))
    op.add_column("mental_fitness_logs", sa.Column("mood_after", sa.String(), nullable=True))
