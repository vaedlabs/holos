"""Plan C.11 tables, request ids on messages, and cascade deletes for user data

Revision ID: 74b3be8d6801
Revises: cd5e821b7af6
Create Date: 2026-10-25
"""

import sqlalchemy as sa

from alembic import op

revision = "74b3be8d6801"
down_revision = "cd5e821b7af6"
branch_labels = None
depends_on = None

# Every existing table with a user_id foreign key (Plan C.11: add ON DELETE CASCADE)
USER_TABLES = (
    "medical_history",
    "user_preferences",
    "workout_logs",
    "nutrition_logs",
    "mental_fitness_logs",
    "conversation_messages",
    "agent_execution_logs",
)

NEW_TABLES = (
    "sessions", "inflight_leases", "principal_flags", "rate_counters", "spend",
    "pending_writes", "request_claims", "invites", "traces", "gate_decisions",
    "rule_hit_counts", "deletion_queue",
)


def _user_fk(nullable: bool = True, **kw) -> sa.Column:
    return sa.Column(
        "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=nullable, **kw,
    )


def _now(name: str = "created_at") -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"),
                     nullable=False)


def _set_user_fk_cascade(cascade: bool) -> None:
    for table in USER_TABLES:
        name = f"{table}_user_id_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "users", ["user_id"], ["id"],
                              ondelete="CASCADE" if cascade else None)


def upgrade() -> None:
    _set_user_fk_cascade(True)

    op.add_column("conversation_messages", sa.Column("client_request_id", sa.Uuid()))
    op.create_unique_constraint("uq_conversation_user_request", "conversation_messages",
                                ["user_id", "client_request_id"])

    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.String(64), primary_key=True),
        sa.Column("mode", sa.String(8), nullable=False),
        _user_fk(index=True),
        sa.Column("ip_key", sa.String(64), nullable=False, index=True),
        _now(),
        _now("last_seen_at"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.CheckConstraint("mode IN ('guest', 'account')", name="ck_sessions_mode"),
    )
    op.create_table(
        "inflight_leases",
        sa.Column("principal_key", sa.String(128), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "principal_flags",
        sa.Column("principal_key", sa.String(128), primary_key=True),
        sa.Column("crisis_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "rate_counters",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "spend",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("period", sa.String(8), primary_key=True),
        sa.Column("period_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("tokens_in", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("search_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("reserved_credits", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("period IN ('day', 'month')", name="ck_spend_period"),
    )
    op.create_table(
        "pending_writes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _user_fk(nullable=False, index=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        _now(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('workout', 'meal', 'practice')",
                           name="ck_pending_writes_kind"),
        sa.CheckConstraint("status IN ('pending', 'committed', 'discarded')",
                           name="ck_pending_writes_status"),
    )
    op.create_table(
        "request_claims",
        _user_fk(nullable=False, primary_key=True),
        sa.Column("client_request_id", sa.Uuid(), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        _now(),
    )
    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        _now(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("used_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  index=True),
    )
    op.create_table(
        "traces",
        sa.Column("trace_id", sa.String(64), primary_key=True),
        sa.Column("session_id_hash", sa.String(64)),
        _user_fk(index=True),
        sa.Column("route", sa.String(16), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False, index=True),
    )
    op.create_table(
        "gate_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(64), nullable=False, index=True),
        _user_fk(index=True),
        sa.Column("rule_id", sa.String(40), nullable=False),
        sa.Column("rules_version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("item", sa.String(200)),
        sa.Column("reason", sa.Text(), nullable=False),
        _now(),
    )
    op.create_table(
        "rule_hit_counts",
        sa.Column("rule_id", sa.String(40), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "deletion_queue",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("prefix", sa.String(256), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text()),
        _now(),
    )


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
    op.drop_constraint("uq_conversation_user_request", "conversation_messages", type_="unique")
    op.drop_column("conversation_messages", "client_request_id")
    _set_user_fk_cascade(False)
