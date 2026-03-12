"""
Database configuration and session management.

This module provides the database connection setup and session management for the
Holos application. It uses SQLAlchemy ORM to interact with a PostgreSQL database.

Key Components:
- Database engine with connection pooling
- Session factory for creating database sessions
- Base class for SQLAlchemy models
- Dependency function for FastAPI to inject database sessions

The module uses environment variables for configuration, allowing different
database settings for development, testing, and production environments.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

# Load environment variables from .env file
# Must be called before accessing DATABASE_URL
load_dotenv()

# Database connection URL from environment variable
# Format: postgresql://username:password@host:port/database_name
# Default value is provided for local development but should be set via environment
# variable in production
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/holos_db")

# SQLAlchemy engine instance
# The engine manages the connection pool and provides the interface to the database
# pool_pre_ping=True: Verifies connections are alive before using them, preventing
#   errors from stale database connections (important for long-running applications)
# echo=False: Set to True to log all SQL queries (useful for debugging)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using (prevents stale connection errors)
    echo=False  # Set to True for SQL query logging (useful for debugging)
)

# Session factory class
# Creates database sessions that are used for all database operations
# autocommit=False: Transactions must be explicitly committed (recommended for data integrity)
# autoflush=False: Changes are not automatically flushed to the database (gives more control)
# bind=engine: Associates this sessionmaker with the database engine
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all SQLAlchemy models
# All model classes should inherit from this Base class
# Provides the declarative base functionality for defining database models
Base = declarative_base()

def get_db():
    """
    Dependency function for FastAPI to get database session.
    
    This function is used as a FastAPI dependency to inject database sessions
    into route handlers. It follows the dependency injection pattern, ensuring
    that database sessions are properly created and closed for each request.
    
    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            # Use db session here
            return db.query(User).all()
    
    Yields:
        Session: SQLAlchemy database session instance
        
    Note:
        The session is automatically closed after the request handler completes,
        even if an exception occurs. This ensures proper resource cleanup and
        prevents connection leaks.
        
        The function uses a generator pattern (yield) which allows FastAPI to
        execute cleanup code in the 'finally' block after the route handler finishes.
    """
    # Create a new database session for this request
    db = SessionLocal()
    try:
        # Yield the session to the route handler
        # FastAPI will inject this session into the route handler function
        yield db
    finally:
        # Always close the session, even if an exception occurred
        # This ensures database connections are properly released back to the pool
        db.close()

