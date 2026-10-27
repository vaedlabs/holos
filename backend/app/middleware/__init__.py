"""Middleware registered in app.main.

    - error_handler.py: exception handlers with consistent JSON error bodies
    - flood.py: C.2 stage 1, 100 requests per minute per IP key (Postgres counter)
    - headers.py: security headers on every response (`nosniff`)
"""
