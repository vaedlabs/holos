"""
Custom exceptions for agent system.

This module exports custom exception classes for agent tool execution errors.
Provides a convenient import point for exception classes used throughout
the agent system.

Exported Exceptions:
    - ToolExecutionError: Base exception for tool execution errors
    - ToolInputValidationError: Invalid tool input (non-retryable)
    - ToolNotFoundError: Tool doesn't exist (non-retryable)
    - ToolRetryableError: Retryable errors (database deadlocks, transient failures)

Usage:
    from app.exceptions import (
        ToolExecutionError,
        ToolInputValidationError,
        ToolRetryableError
    )
    
    try:
        tool._run(...)
    except ToolRetryableError:
        # Retry with exponential backoff
    except ToolInputValidationError:
        # Don't retry - invalid input
"""

from app.exceptions.agent_exceptions import (
    ToolExecutionError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolRetryableError
)

# Export all exception classes
# Makes exceptions available via: from app.exceptions import ToolExecutionError
__all__ = [
    "ToolExecutionError",  # Base exception for tool execution errors
    "ToolInputValidationError",  # Invalid tool input (non-retryable)
    "ToolNotFoundError",  # Tool doesn't exist (non-retryable)
    "ToolRetryableError"  # Retryable errors (database deadlocks, transient failures)
]

