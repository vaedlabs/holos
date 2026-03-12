"""
Holos Backend Application Package.

This is the main application package for the Holos fitness and wellness platform.
It contains all backend components including models, schemas, routers, services,
agents, and middleware.

Package Structure:
    - models/: SQLAlchemy database models (User, WorkoutLog, etc.)
    - schemas/: Pydantic validation schemas (request/response models)
    - routers/: FastAPI route handlers (API endpoints)
    - services/: Business logic services (caching, tracing, medical checks)
    - agents/: AI agent implementations (LangChain-based agents)
    - middleware/: FastAPI middleware (error handling, rate limiting)
    - exceptions/: Custom exception classes

The application is built on FastAPI and provides REST API endpoints for:
    - User authentication and account management
    - AI agent interactions (physical fitness, nutrition, mental fitness, coordinator)
    - User preferences and medical history management
    - Logging (workouts, nutrition, mental fitness activities)
    - Conversation history and image handling
    - Agent execution observability

Main entry point: app.main:app (FastAPI application instance)
"""
