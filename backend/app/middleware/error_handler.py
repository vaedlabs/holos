"""
Standardized error handling middleware for FastAPI application.

This module provides centralized error handling for the FastAPI application,
ensuring consistent error responses across all endpoints. It registers exception
handlers for HTTP exceptions, validation errors, and general exceptions.

Key Features:
- Centralized error handling: All exceptions handled in one place
- Consistent error responses: Standardized error response format
- Environment-aware error messages: Detailed errors in development, generic in production
- Comprehensive logging: All errors logged with context (method, path, details)
- Security: Sensitive error details hidden in production

Exception Handlers:
- HTTPException: Handles HTTP exceptions (4xx, 5xx status codes)
- RequestValidationError: Handles request validation errors (422)
- Exception: Handles all other unhandled exceptions (500)

Error Response Format:
- error: str (error message)
- status_code: int (HTTP status code)
- path: str (request path)
- details: List[Dict] (validation error details, if applicable)
- error_type: str (exception type, development only)

Security Considerations:
- Detailed error messages only in development environment
- Generic error messages in production to prevent information leakage
- Error paths logged but not exposed in production responses

Usage:
    from app.middleware.error_handler import register_error_handlers
    
    app = FastAPI()
    register_error_handlers(app)
"""

import logging
import os
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Logger for error handling
# Logs all errors with context (method, path, details)
logger = logging.getLogger(__name__)


def register_error_handlers(app):
    """
    Register exception handlers with the FastAPI app.
    
    This function registers three exception handlers with the FastAPI application:
    1. HTTPException handler: Handles HTTP exceptions (4xx, 5xx)
    2. RequestValidationError handler: Handles request validation errors (422)
    3. Exception handler: Handles all other unhandled exceptions (500)
    
    Exception handlers are registered in order of specificity:
    - Most specific handlers first (HTTPException, RequestValidationError)
    - General handler last (Exception) to catch all remaining exceptions
    
    Args:
        app: FastAPI application instance
              Exception handlers are registered on this app instance
    
    Usage:
        Call this function in main.py after creating the FastAPI app:
        
        from app.middleware.error_handler import register_error_handlers
        
        app = FastAPI()
        register_error_handlers(app)
        
    Note:
        - Handlers are registered as decorators on the app instance
        - Order matters: more specific handlers should be registered first
        - All handlers return JSONResponse for consistent API responses
    """
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """
        Handle HTTP exceptions (4xx, 5xx status codes).
        
        This handler catches all HTTP exceptions raised by FastAPI endpoints
        or Starlette middleware. These include client errors (4xx) and server
        errors (5xx) that are explicitly raised as HTTPException.
        
        Args:
            request: FastAPI Request object (contains method, path, etc.)
            exc: StarletteHTTPException instance (contains status_code, detail)
        
        Returns:
            JSONResponse: Consistent error response with:
                - error: str (error detail message)
                - status_code: int (HTTP status code)
                - path: str (request path)
                
        Logging:
            - Errors logged at ERROR level with context
            - Includes HTTP method, path, and error detail
            
        Example:
            Raises HTTPException(404, detail="Not found")
            -> Returns 404 with {"error": "Not found", "status_code": 404, "path": "/api/..."}
        """
        # Log the error with context
        # Includes HTTP method, path, and error detail for debugging
        logger.error(
            f"HTTP {exc.status_code} error on {request.method} {request.url.path}: {exc.detail}"
        )
        
        # Return consistent error response
        # Standardized format for all HTTP exceptions
        return JSONResponse(
            status_code=exc.status_code,  # Preserve original status code
            content={
                "error": exc.detail,  # Error detail message
                "status_code": exc.status_code,  # HTTP status code
                "path": str(request.url.path)  # Request path for debugging
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
        Handle request validation errors (422 Unprocessable Entity).
        
        This handler catches Pydantic validation errors when request data
        doesn't match the expected schema. These occur when:
        - Required fields are missing
        - Field types don't match (e.g., string instead of int)
        - Field values fail validation (e.g., negative age)
        
        Args:
            request: FastAPI Request object (contains method, path, etc.)
            exc: RequestValidationError instance (contains validation errors)
        
        Returns:
            JSONResponse: Validation error response with:
                - error: str ("Validation error")
                - status_code: int (422)
                - details: List[Dict] (detailed validation errors)
                - path: str (request path)
                
        Validation Error Details:
            - Each error includes field location, error type, and message
            - Format: [{"loc": ["field"], "msg": "error message", "type": "error_type"}]
            
        Logging:
            - Validation errors logged at WARNING level
            - Includes HTTP method, path, and validation error details
            
        Example:
            POST /api/users with invalid email
            -> Returns 422 with validation error details
        """
        # Log validation errors
        # Validation errors are logged at WARNING level (not ERROR - expected behavior)
        logger.warning(
            f"Validation error on {request.method} {request.url.path}: {exc.errors()}"
        )
        
        # Return validation error response
        # Includes detailed validation errors for client debugging
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,  # 422 Unprocessable Entity
            content={
                "error": "Validation error",  # Generic error message
                "status_code": 422,  # HTTP status code
                "details": exc.errors(),  # Detailed validation errors (field, message, type)
                "path": str(request.url.path)  # Request path for debugging
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """
        Handle all other unhandled exceptions (500 Internal Server Error).
        
        This handler catches all exceptions that aren't handled by more specific
        handlers. This includes:
        - Database errors
        - Unexpected exceptions in endpoint handlers
        - Third-party library exceptions
        - Any other unhandled exceptions
        
        Security:
            - In development: Shows detailed error messages and exception types
            - In production: Shows generic "Internal server error" message
            - Prevents information leakage in production
        
        Args:
            request: FastAPI Request object (contains method, path, etc.)
            exc: Exception instance (any unhandled exception)
        
        Returns:
            JSONResponse: Error response with:
                - error: str (error message - detailed in dev, generic in prod)
                - status_code: int (500)
                - path: str (request path)
                - error_type: str (exception type, development only)
                
        Logging:
            - Full exception logged with traceback (logger.exception)
            - Includes HTTP method, path, and exception message
            
        Environment Detection:
            - Checks ENVIRONMENT environment variable
            - Defaults to "development" if not set
            - Development: Detailed errors
            - Production: Generic errors
            
        Example:
            Database connection error in endpoint
            -> Development: Returns 500 with detailed error
            -> Production: Returns 500 with "Internal server error"
        """
        # Log full exception with traceback
        # logger.exception() includes full traceback for debugging
        logger.exception(
            f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}"
        )
        
        # Determine error message based on environment
        # Security: Detailed errors only in development, generic in production
        is_development = os.getenv("ENVIRONMENT", "development") == "development"
        
        if is_development:
            # In development, show detailed error
            # Helps developers debug issues quickly
            error_message = str(exc)  # Full exception message
            error_type = type(exc).__name__  # Exception class name
        else:
            # In production, show generic error
            # Prevents information leakage (sensitive details, stack traces, etc.)
            error_message = "Internal server error"
            error_type = "InternalServerError"
        
        # Return error response
        # Base response content (always included)
        response_content = {
            "error": error_message,  # Error message (detailed or generic)
            "status_code": 500,  # HTTP status code
            "path": str(request.url.path)  # Request path for debugging
        }
        
        # Only include error type in development
        # Error type helps debugging but shouldn't be exposed in production
        if is_development:
            response_content["error_type"] = error_type
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  # 500 Internal Server Error
            content=response_content
        )

