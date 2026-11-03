"""Log warnings: what in a logged entry conflicted with the profile (Plan C.17, Part E #45)

Revision ID: d4e5f6071829
Revises: c3d4e5f60718
Create Date: 2026-11-03
"""

import sqlalchemy as sa

from alembic import op

revision = "d4e5f6071829"
down_revision = "c3d4e5f60718"
branch_labels = None
depends_on = None

TABLES = ("workout_logs", "nutrition_logs", "mental_fitness_logs")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("warnings", sa.JSON(), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "warnings")
