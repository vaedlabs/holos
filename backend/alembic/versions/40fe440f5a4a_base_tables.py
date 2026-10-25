"""Base tables that were first made by setup_database.py

Revision ID: 40fe440f5a4a
Revises:
Create Date: 2026-10-25

The original chain started with conversation_messages, which references users,
but no migration created users or the other base tables; setup_database.py did.
So `alembic upgrade head` failed on an empty database (Plan Part E #6).

This revision creates those six tables as they stood before 5610f35e0f8a. A
database that already has them (every existing one) is already past this
revision, so it never runs there.
"""

import sqlalchemy as sa

from alembic import op

revision = "40fe440f5a4a"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    ]


def _user_fk() -> sa.Column:
    return sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean()),
        *_timestamps(),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "medical_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("conditions", sa.Text()),
        sa.Column("limitations", sa.Text()),
        sa.Column("medications", sa.Text()),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_medical_history_id", "medical_history", ["id"])

    # age, gender and lifestyle are added later by f29379640c3d
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("goals", sa.Text()),
        sa.Column("dietary_restrictions", sa.Text()),
        sa.Column("location", sa.String()),
        sa.Column("exercise_types", sa.Text()),
        sa.Column("activity_level", sa.String()),
        *_timestamps(),
    )
    op.create_index("ix_user_preferences_id", "user_preferences", ["id"])

    logs = {
        "workout_logs": ("workout_date", [
            sa.Column("exercise_type", sa.String()),
            sa.Column("exercises", sa.Text()),
            sa.Column("duration_minutes", sa.Float()),
        ]),
        "nutrition_logs": ("meal_date", [
            sa.Column("meal_type", sa.String()),
            sa.Column("foods", sa.Text()),
            sa.Column("calories", sa.Float()),
            sa.Column("macros", sa.Text()),
        ]),
        "mental_fitness_logs": ("activity_date", [
            sa.Column("activity_type", sa.String()),
            sa.Column("duration_minutes", sa.Float()),
            sa.Column("mood_before", sa.String()),
            sa.Column("mood_after", sa.String()),
        ]),
    }
    for table, (date_column, columns) in logs.items():
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True),
            _user_fk(),
            sa.Column(date_column, sa.DateTime(timezone=True), server_default=sa.text("now()"),
                      nullable=False),
            *columns,
            sa.Column("notes", sa.Text()),
            *_timestamps(),
        )
        op.create_index(f"ix_{table}_id", table, ["id"])


def downgrade() -> None:
    for table in ("mental_fitness_logs", "nutrition_logs", "workout_logs",
                  "user_preferences", "medical_history", "users"):
        op.drop_table(table)
