"""Account imports: one "save to an account" per import_id (Plan C.18, Part E #46)

Revision ID: e5f607182930
Revises: d4e5f6071829
Create Date: 2026-11-03
"""

import sqlalchemy as sa

from alembic import op

revision = "e5f607182930"
down_revision = "d4e5f6071829"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_imports",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("import_id", sa.Uuid(), primary_key=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )


def downgrade() -> None:
    op.drop_table("account_imports")
