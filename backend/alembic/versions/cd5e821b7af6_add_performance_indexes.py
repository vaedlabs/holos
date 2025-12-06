"""add_performance_indexes

Revision ID: cd5e821b7af6
Revises: e79813599dcb
Create Date: 2025-12-03 06:54:53.184581

Adds composite indexes for frequently queried columns to improve query performance.
Indexes are added on (user_id, date/created_at) columns for tables that are frequently
queried by user and ordered by date.

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cd5e821b7af6'
down_revision = 'e79813599dcb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add composite indexes for performance optimization.
    
    These indexes improve query performance for:
    - Conversation messages: Filtered by user_id, ordered by created_at
    - Workout logs: Filtered by user_id, ordered by workout_date
    - Nutrition logs: Filtered by user_id, ordered by meal_date
    - Mental fitness logs: Filtered by user_id, ordered by activity_date
    
    Note: medical_history and user_preferences already have unique indexes on user_id
    (created by unique constraints), so no additional indexes are needed.
    """
    # Composite index for conversation messages (user_id + created_at)
    # Used by: GET /conversation/messages - filters by user_id, orders by created_at
    op.create_index(
        'idx_conversation_user_created',
        'conversation_messages',
        ['user_id', 'created_at'],
        unique=False
    )
    
    # Composite index for workout logs (user_id + workout_date)
    # Used by: GET /logs/workouts - filters by user_id, orders by workout_date DESC
    op.create_index(
        'idx_workout_log_user_date',
        'workout_logs',
        ['user_id', 'workout_date'],
        unique=False
    )
    
    # Composite index for nutrition logs (user_id + meal_date)
    # Used by: GET /logs/nutrition - filters by user_id, orders by meal_date DESC
    op.create_index(
        'idx_nutrition_log_user_date',
        'nutrition_logs',
        ['user_id', 'meal_date'],
        unique=False
    )
    
    # Composite index for mental fitness logs (user_id + activity_date)
    # Used by: GET /logs/mental-fitness - filters by user_id, orders by activity_date DESC
    op.create_index(
        'idx_mental_fitness_log_user_date',
        'mental_fitness_logs',
        ['user_id', 'activity_date'],
        unique=False
    )


def downgrade() -> None:
    """
    Remove the performance indexes.
    """
    op.drop_index('idx_mental_fitness_log_user_date', table_name='mental_fitness_logs')
    op.drop_index('idx_nutrition_log_user_date', table_name='nutrition_logs')
    op.drop_index('idx_workout_log_user_date', table_name='workout_logs')
    op.drop_index('idx_conversation_user_created', table_name='conversation_messages')

