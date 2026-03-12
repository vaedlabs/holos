"""
Alembic environment configuration.

This module configures Alembic's migration environment. Alembic uses this file
to understand how to connect to the database and which SQLAlchemy models to
track for schema changes.

Key Responsibilities:
    - Database connection configuration (from DATABASE_URL env var)
    - Model metadata registration (for autogenerate migrations)
    - Migration execution modes (offline vs online)
    - Logging configuration

Migration Execution:
    - Online mode: Connects to live database, executes migrations directly
    - Offline mode: Generates SQL scripts without database connection
      (useful for review or manual execution)

Autogenerate Support:
    - target_metadata = Base.metadata enables Alembic to detect model changes
    - When models change, run: alembic revision --autogenerate -m "description"
    - Alembic compares current models to database schema and generates migration

Usage:
    alembic upgrade head          # Apply all pending migrations
    alembic downgrade -1          # Rollback last migration
    alembic revision --autogenerate -m "add column"  # Generate migration from models
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path to import app modules
# Alembic runs from alembic/ directory, so we need to add backend/ to path
# This allows importing app.database and app.models
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load environment variables from .env file
# Required for DATABASE_URL and other config values
load_dotenv()

# Import Base and models
# These imports ensure all models are registered with SQLAlchemy Base.metadata
# Alembic needs this to detect schema changes via autogenerate
from app.database import Base
from app.models import User, MedicalHistory, UserPreferences, WorkoutLog, NutritionLog, MentalFitnessLog, ConversationMessage

# Alembic Config object - provides access to alembic.ini configuration
# Contains settings like database URL, logging config, migration paths
config = context.config

# Override sqlalchemy.url with environment variable
# DATABASE_URL takes precedence over alembic.ini settings
# Fallback to default PostgreSQL URL if env var not set (dev only)
database_url = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/holos_db")
config.set_main_option("sqlalchemy.url", database_url)

# Configure Python logging from alembic.ini
# Sets up loggers for migration execution output
# Only configures if alembic.ini exists (standard Alembic setup)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Register SQLAlchemy metadata for autogenerate support
# Base.metadata contains all model definitions (tables, columns, relationships)
# Alembic compares this to current database schema to generate migrations
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Offline mode generates SQL migration scripts without connecting to the database.
    Useful for:
        - Reviewing migration SQL before execution
        - Manual execution in restricted environments
        - CI/CD pipelines that generate migrations separately

    How it works:
        - No database connection required (no DBAPI needed)
        - Generates raw SQL strings instead of executing directly
        - literal_binds=True: Embeds parameter values directly in SQL
        - dialect_opts: Configures SQL parameter style for PostgreSQL

    Output:
        SQL scripts printed to stdout (can be redirected to file)
    """
    url = config.get_main_option("sqlalchemy.url")  # Database URL from config
    context.configure(
        url=url,  # Database URL (not connected yet)
        target_metadata=target_metadata,  # Model metadata for schema comparison
        literal_binds=True,  # Embed parameter values in SQL (required for offline)
        dialect_opts={"paramstyle": "named"},  # PostgreSQL parameter style (:param)
    )

    # Generate migration SQL (doesn't execute, just outputs SQL)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Online mode connects to the database and executes migrations directly.
    This is the standard mode for development and production.

    How it works:
        - Creates SQLAlchemy Engine with connection pool
        - Establishes database connection
        - Executes migration SQL statements directly
        - Uses NullPool to avoid connection pool overhead for migrations

    Connection Pool:
        - NullPool: No connection pooling (migrations are short-lived)
        - Each migration gets a fresh connection
        - Prevents connection pool exhaustion during migrations
    """
    # Create SQLAlchemy Engine from config
    # Reads sqlalchemy.* options from alembic.ini
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),  # Config section
        prefix="sqlalchemy.",  # Prefix for SQLAlchemy options
        poolclass=pool.NullPool,  # No connection pooling (migrations are short)
    )

    # Execute migrations with live database connection
    with connectable.connect() as connection:
        context.configure(
            connection=connection,  # Live database connection
            target_metadata=target_metadata  # Model metadata for schema comparison
        )

        # Execute migration SQL statements in a transaction
        # Transaction ensures atomicity (all-or-nothing migration)
        with context.begin_transaction():
            context.run_migrations()


# Determine execution mode based on Alembic context
# Offline: alembic upgrade head --sql (generates SQL without executing)
# Online: alembic upgrade head (executes migrations directly)
if context.is_offline_mode():
    run_migrations_offline()  # Generate SQL scripts
else:
    run_migrations_online()  # Execute migrations directly

