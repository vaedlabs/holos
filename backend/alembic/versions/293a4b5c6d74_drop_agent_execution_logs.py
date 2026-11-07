"""Drop agent_execution_logs: the old agents' log, replaced by traces (Plan C.11, P4.12)

Its rows held people's messages and the old agents' replies; `traces` and
`gate_decisions` hold no text a person wrote (P4.10). The downgrade recreates the
table as it was, empty: the rows are not kept.

Revision ID: 293a4b5c6d74
Revises: 18293a4b5c63
Create Date: 2026-11-07
"""

import sqlalchemy as sa

from alembic import op

revision = "293a4b5c6d74"
down_revision = "18293a4b5c63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("agent_execution_logs")


def downgrade() -> None:
    op.create_table(
        "agent_execution_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("agent_type", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query", sa.Text()),
        sa.Column("response", sa.Text()),
        sa.Column("warnings", sa.JSON()),
        sa.Column("tools_called", sa.JSON()),
        sa.Column("tokens_used", sa.Integer()),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("success", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for column in ("agent_type", "created_at", "id", "user_id"):
        op.create_index(f"ix_agent_execution_logs_{column}", "agent_execution_logs", [column])
    op.create_index("ix_agent_execution_logs_trace_id", "agent_execution_logs", ["trace_id"],
                    unique=True)
