"""
Standardized error handling middleware for FastAPI application
Provides consistent error responses across all endpoints
"""

import logging
import os
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def register_error_handlers(app):
    """
    Register exception handlers with the FastAPI app.
    Call this function in main.py after creating the app.
    
    Args:
        app: FastAPI application instance
    """
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """
        Handle HTTP exceptions (4xx, 5xx status codes)
        """
        # Log the error with context
        logger.error(
            f"HTTP {exc.status_code} error on {request.method} {request.url.path}: {exc.detail}"
        )
        
        # Return consistent error response
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "status_code": exc.status_code,
                "path": str(request.url.path)
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
        Handle request validation errors (422 Unprocessable Entity)
        """
        # Log validation errors
        logger.warning(
            f"Validation error on {request.method} {request.url.path}: {exc.errors()}"
        )
        
        # Return validation error response
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation error",
                "status_code": 422,
                "details": exc.errors(),
                "path": str(request.url.path)
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """
        Handle all other unhandled exceptions (500 Internal Server Error)
        """
        # Log full exception with traceback
        logger.exception(
            f"Unhandled exception on {request.method} {request.url.path}: {str(exc)}"
        )
        
        # Determine error message based on environment
        is_development = os.getenv("ENVIRONMENT", "development") == "development"
        
        if is_development:
            # In development, show detailed error
            error_message = str(exc)
            error_type = type(exc).__name__
        else:
            # In production, show generic error
            error_message = "Internal server error"
            error_type = "InternalServerError"
        
        # Return error response
        response_content = {
            "error": error_message,
            "status_code": 500,
            "path": str(request.url.path)
        }
        
        # Only include error type in development
        if is_development:
            response_content["error_type"] = error_type
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_content
        )

