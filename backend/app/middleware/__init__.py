"""
Middleware package for FastAPI application.

This module contains FastAPI middleware components that process requests/responses
before they reach route handlers. Middleware handles cross-cutting concerns.

Middleware Modules:
    - error_handler.py: Standardized error handling and exception responses
    - rate_limit.py: Rate limiting to prevent API abuse (sliding window)

Middleware Registration:
    Middleware is registered in app.main:app using app.add_middleware().
    Order matters - middleware executes in registration order.

Error Handler:
    - Registers exception handlers for HTTP errors, validation errors, and general exceptions
    - Provides consistent JSON error responses
    - Environment-aware error messages (detailed in dev, generic in prod)

Rate Limiter:
    - Sliding window rate limiting per client IP
    - Endpoint-specific limits (default, agent endpoints, auth endpoints)
    - X-RateLimit-* headers for client feedback

Usage:
    Middleware is automatically applied when registered in main.py:
        from app.middleware.error_handler import register_error_handlers
        register_error_handlers(app)
"""
