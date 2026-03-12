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
    
    Creates composite indexes on (user_id, date/created_at) columns for tables
    that are frequently queried by user and ordered by date. These indexes
    significantly improve query performance for paginated, user-scoped queries.
    
    Index Strategy:
        - Composite indexes cover both WHERE (user_id) and ORDER BY (date) clauses
        - Single index handles both filter and sort operations efficiently
        - Reduces full table scans and improves query execution time
    
    Tables Indexed:
        - conversation_messages: (user_id, created_at) - GET /conversation/messages
        - workout_logs: (user_id, workout_date) - GET /logs/workouts
        - nutrition_logs: (user_id, meal_date) - GET /logs/nutrition
        - mental_fitness_logs: (user_id, activity_date) - GET /logs/mental-fitness
    
    Note: medical_history and user_preferences already have unique indexes on
    user_id (created by unique constraints), so no additional indexes needed.
    
    Performance Impact:
        - Before: Full table scan + sort (O(n log n))
        - After: Index scan + sort (O(log n) + k) where k is result set size
    """
    # Composite index for conversation messages (user_id + created_at)
    # Query pattern: WHERE user_id = ? ORDER BY created_at DESC
    # Used by: GET /conversation/messages - filters by user_id, orders by created_at
    op.create_index(
        'idx_conversation_user_created',
        'conversation_messages',
        ['user_id', 'created_at'],  # Composite: filter + sort
        unique=False  # Non-unique (multiple messages per user)
    )
    
    # Composite index for workout logs (user_id + workout_date)
    # Query pattern: WHERE user_id = ? ORDER BY workout_date DESC
    # Used by: GET /logs/workouts - filters by user_id, orders by workout_date DESC
    op.create_index(
        'idx_workout_log_user_date',
        'workout_logs',
        ['user_id', 'workout_date'],  # Composite: filter + sort
        unique=False
    )
    
    # Composite index for nutrition logs (user_id + meal_date)
    # Query pattern: WHERE user_id = ? ORDER BY meal_date DESC
    # Used by: GET /logs/nutrition - filters by user_id, orders by meal_date DESC
    op.create_index(
        'idx_nutrition_log_user_date',
        'nutrition_logs',
        ['user_id', 'meal_date'],  # Composite: filter + sort
        unique=False
    )
    
    # Composite index for mental fitness logs (user_id + activity_date)
    # Query pattern: WHERE user_id = ? ORDER BY activity_date DESC
    # Used by: GET /logs/mental-fitness - filters by user_id, orders by activity_date DESC
    op.create_index(
        'idx_mental_fitness_log_user_date',
        'mental_fitness_logs',
        ['user_id', 'activity_date'],  # Composite: filter + sort
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

