"""
API routers package.

This module contains FastAPI route handlers (routers) that define API endpoints.
Routers are organized by domain and handle HTTP requests/responses.

Router Modules:
    - auth.py: User authentication (register, login, delete account)
    - agents.py: AI agent interactions (chat endpoints for all agents)
    - preferences.py: User preferences management (GET, POST/PUT)
    - medical.py: Medical history management (GET, POST/PUT)
    - logs.py: Log management (workouts, nutrition, mental fitness)
    - conversation.py: Conversation history and image handling
    - cache.py: Cache management and monitoring endpoints

Routers are registered in app.main:app using app.include_router().

Usage:
    Routers are imported and included in main.py:
        from app.routers import auth, agents, preferences
        app.include_router(auth.router, prefix="/auth", tags=["auth"])
"""
