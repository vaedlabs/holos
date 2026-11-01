"""Resumable requests: chat_requests replaces request_claims; stream_events (Plan C.5,
C.11, Part E #34)

Revision ID: c3d4e5f60718
Revises: b7c1d2e3f405
Create Date: 2026-11-02
"""

import sqlalchemy as sa

from alembic import op

revision = "c3d4e5f60718"
down_revision = "b7c1d2e3f405"
branch_labels = None
depends_on = None


def _now() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                     nullable=False)


def upgrade() -> None:
    op.create_table(
        "chat_requests",
        sa.Column("principal_key", sa.String(128), primary_key=True),
        sa.Column("client_request_id", sa.Uuid(), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("worker", sa.String(128), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _now(),
    )
    op.create_table(
        "stream_events",
        sa.Column("trace_id", sa.String(64),
                  sa.ForeignKey("chat_requests.trace_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("event", sa.String(20), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        _now(),
    )
    # Claims live a day: nothing in flight is lost by dropping the old ones
    op.drop_table("request_claims")


def downgrade() -> None:
    op.create_table(
        "request_claims",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("client_request_id", sa.Uuid(), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        _now(),
    )
    op.drop_table("stream_events")
    op.drop_table("chat_requests")
