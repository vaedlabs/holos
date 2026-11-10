"""
API routers package.

This module contains FastAPI route handlers (routers) that define API endpoints.
Routers are organized by domain and handle HTTP requests/responses.

Router Modules:
    - auth.py: Login, logout, invites, delete account
    - session.py: Guest sessions and the CSRF token
    - chat.py: The chat stream, reconnect and write confirmation
    - account.py: Import a guest's data, profile check
    - crud/: the account's medical history, preferences, logs and chat history
      (plain functions on the sync pool, run in FastAPI's threadpool; Plan C.1)

Routers are registered in app.main:app using app.include_router().

Usage:
    Routers are imported and included in main.py:
        from app.routers import auth, chat
        app.include_router(auth.router, prefix="/auth", tags=["auth"])
"""
