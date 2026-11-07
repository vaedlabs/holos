"""
API routers package.

This module contains FastAPI route handlers (routers) that define API endpoints.
Routers are organized by domain and handle HTTP requests/responses.

Router Modules:
    - auth.py: Login, logout, invites, delete account
    - session.py: Guest sessions and the CSRF token
    - chat.py: The chat stream, reconnect and write confirmation
    - account.py: Import a guest's data, profile check
    - preferences.py: User preferences management (GET, POST/PUT)
    - medical.py: Medical history management (GET, POST/PUT)
    - logs.py: Log management (workouts, nutrition, mental fitness)
    - conversation.py: Conversation history and image handling

Routers are registered in app.main:app using app.include_router().

Usage:
    Routers are imported and included in main.py:
        from app.routers import auth, chat, preferences
        app.include_router(auth.router, prefix="/auth", tags=["auth"])
"""
