"""
Custom exception classes for agent tool execution errors.

This module provides a hierarchy of custom exceptions for handling agent tool
execution errors. These exceptions enable proper error classification, retry
logic, and error handling in agent tool execution.

Exception Hierarchy:
    - ToolExecutionError: Base exception for all tool execution errors
    - ToolInputValidationError: Invalid tool input (non-retryable)
    - ToolNotFoundError: Tool doesn't exist (non-retryable)
    - ToolRetryableError: Retryable errors (database deadlocks, transient failures)

Error Classification:
    - Retryable errors: Should be retried with exponential backoff
    - Non-retryable errors: Should not be retried (validation, not found, etc.)

Retryable Error Detection:
    - ToolRetryableError instances
    - Database deadlocks and lock timeouts
    - Transient database errors (connection, timeout, temporary)
    - Exception type names containing "Deadlock", "Timeout", "Connection"

Usage:
    from app.exceptions.agent_exceptions import (
        ToolExecutionError,
        ToolInputValidationError,
        ToolRetryableError,
        is_retryable_tool_error
    )
    
    try:
        tool._run(...)
    except ToolRetryableError:
        # Retry with exponential backoff
    except ToolInputValidationError:
        # Don't retry - invalid input
"""


class ToolExecutionError(Exception):
    """
    Base exception for tool execution errors.
    
    This is the base class for all tool execution errors. It provides common
    functionality for tracking tool name and original error information.
    
    Attributes:
        tool_name: str - Name of the tool that failed
        original_error: Exception or None - Original exception that caused this error
        message: str - Error message (from Exception base class)
    
    Usage:
        Raised when a tool fails to execute due to an unexpected error.
        Subclasses provide more specific error types (validation, not found, retryable).
    """
    
    def __init__(self, tool_name: str, message: str, original_error: Exception = None):
        """
        Initialize tool execution error.
        
        Args:
            tool_name: str - Name of the tool that failed
                      Used for error messages and logging
            message: str - Error message describing what went wrong
            original_error: Optional[Exception] - Original exception that caused this error
                          Preserved for error chaining and debugging
                          Can be None if no original error
        """
        self.tool_name = tool_name  # Tool name for error tracking
        self.original_error = original_error  # Original exception (for error chaining)
        super().__init__(f"Tool '{tool_name}' execution failed: {message}")  # Error message


class ToolInputValidationError(ToolExecutionError):
    """
    Exception raised when tool input validation fails.
    
    This exception is raised when tool inputs are invalid, missing required fields,
    or have wrong types. These errors are non-retryable - retrying with the same
    invalid input will always fail.
    
    Attributes:
        tool_name: str - Name of the tool (inherited from ToolExecutionError)
        invalid_fields: List[str] - List of invalid field names
                       Helps identify which fields failed validation
    
    Usage:
        Raised when tool input validation fails before tool execution.
        Should not be retried - requires fixing input data.
    """
    
    def __init__(self, tool_name: str, message: str, invalid_fields: list = None):
        """
        Initialize tool input validation error.
        
        Args:
            tool_name: str - Name of the tool with invalid input
            message: str - Validation error message describing the problem
            invalid_fields: Optional[List[str]] - List of invalid field names
                          Helps identify which fields failed validation
                          Defaults to empty list if not provided
        """
        self.invalid_fields = invalid_fields or []  # Invalid field names (for debugging)
        super().__init__(tool_name, f"Input validation failed: {message}")  # Error message


class ToolNotFoundError(ToolExecutionError):
    """
    Exception raised when a requested tool is not found.
    
    This exception is raised when trying to execute a tool that doesn't exist
    in the agent's tool list. These errors are non-retryable - the tool won't
    exist on retry either.
    
    Attributes:
        tool_name: str - Name of the tool that was not found
    
    Usage:
        Raised when agent tries to call a tool that doesn't exist.
        Should not be retried - indicates configuration or code error.
    """
    
    def __init__(self, tool_name: str):
        """
        Initialize tool not found error.
        
        Args:
            tool_name: str - Name of the tool that was not found
                      Used in error message
        """
        super().__init__(tool_name, f"Tool '{tool_name}' not found")  # Error message


class ToolRetryableError(ToolExecutionError):
    """
    Exception raised for retryable tool errors.
    
    This exception is raised for errors that should be retried with exponential
    backoff. These include database deadlocks, transient failures, connection
    timeouts, and other temporary errors that may succeed on retry.
    
    Retryable Error Types:
        - Database deadlocks
        - Lock wait timeouts
        - Connection errors
        - Transient database failures
        - Temporary service unavailability
    
    Attributes:
        tool_name: str - Name of the tool that failed (inherited)
        original_error: Exception or None - Original exception (inherited)
        retry_after: Optional[float] - Suggested retry delay in seconds
                    Helps implement retry logic with appropriate delays
    
    Usage:
        Raised when tool execution fails due to retryable errors.
        Should be retried with exponential backoff.
    """
    
    def __init__(self, tool_name: str, message: str, original_error: Exception = None, retry_after: float = None):
        """
        Initialize retryable tool error.
        
        Args:
            tool_name: str - Name of the tool that failed
            message: str - Error message describing the retryable error
            original_error: Optional[Exception] - Original exception that caused this error
                          Preserved for error chaining and debugging
            retry_after: Optional[float] - Suggested retry delay in seconds
                        Helps implement retry logic with appropriate delays
                        None if no specific delay suggested
        """
        self.retry_after = retry_after  # Suggested retry delay (seconds)
        super().__init__(tool_name, message, original_error)  # Initialize base exception


def is_retryable_tool_error(error: Exception) -> bool:
    """
    Check if a tool error is retryable.
    
    This function determines if an error should be retried based on error type
    and error message content. Used by retry logic to decide whether to retry
    tool execution with exponential backoff.
    
    Retryable Error Detection:
        1. ToolRetryableError instances (explicitly marked as retryable)
        2. Database deadlocks ("deadlock" in error message)
        3. Lock wait timeouts ("lock wait timeout" in error message)
        4. Transient database errors (connection, timeout, temporary, transient)
        5. Exception type names containing "Deadlock", "Timeout", "Connection"
    
    Non-Retryable Errors:
        - ToolInputValidationError (invalid input won't become valid)
        - ToolNotFoundError (tool won't appear on retry)
        - Other validation errors
    
    Args:
        error: Exception - Exception to check for retryability
        
    Returns:
        bool: True if error is retryable (should retry with exponential backoff)
              False if error is non-retryable (don't retry)
              
    Usage:
        Used by retry logic in llm_retry and agent execution:
        
        if is_retryable_tool_error(error):
            # Retry with exponential backoff
        else:
            # Don't retry - error won't succeed on retry
            
    Note:
        - Checks both error type and error message content
        - Case-insensitive string matching for error messages
        - Exception type name matching for common error types
    """
    # Check if it's a ToolRetryableError
    # Explicitly marked as retryable
    if isinstance(error, ToolRetryableError):
        return True
    
    # Check for database deadlocks (SQLAlchemy)
    # Deadlocks are transient and may succeed on retry
    error_str = str(error).lower()  # Case-insensitive matching
    if "deadlock" in error_str or "lock wait timeout" in error_str:
        return True
    
    # Check for transient database errors
    # Connection errors, timeouts, temporary failures are retryable
    if any(term in error_str for term in ["connection", "timeout", "temporary", "transient"]):
        return True
    
    # Check exception type names
    # Some exception types indicate retryable errors
    error_type = type(error).__name__  # Exception class name
    if "Deadlock" in error_type or "Timeout" in error_type or "Connection" in error_type:
        return True
    
    # Not retryable
    return False

