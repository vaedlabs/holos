"""
Holos - AI Fitness Application Backend

This module serves as the main entry point for the Holos FastAPI application.
It initializes the FastAPI app, configures middleware, registers routers, and sets up
static file serving.

Key Components:
- FastAPI application instance with CORS middleware
- Environment variable validation at startup
- Router registration for all API endpoints
- Static file serving for uploaded images
- Health check and root endpoints

The application uses a modular architecture with separate routers for:
- Authentication (auth)
- Medical history (medical)
- AI Agents (agents)
- User preferences (preferences)
- Conversations (conversation)
- Logs (logs)
- Cache management (cache)
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os
from pathlib import Path

# Load environment variables from .env file
# This must be called before accessing any environment variables
load_dotenv()

# Configure application-wide logging
# Log level can be set via LOG_LEVEL environment variable (defaults to INFO)
# Format includes timestamp, logger name, log level, and message
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Logger instance for this module
# Used throughout the application for logging events and errors
logger = logging.getLogger(__name__)

# FastAPI application instance
# This is the main application object that handles all HTTP requests
# Configured with title, description, and version for API documentation
app = FastAPI(
    title="Holos API",
    description="AI-powered fitness application with specialized agents",
    version="0.1.0"
)

# Validate environment variables at startup
@app.on_event("startup")
async def validate_environment():
    """
    Validate required environment variables at application startup.
    
    This function runs once when the FastAPI application starts and ensures that
    all required environment variables are present and valid. If any required
    variables are missing or invalid, the application will fail to start with
    a clear error message.
    
    Validated Variables:
    Required (application fails to start if missing):
    - JWT_SECRET_KEY: Must be at least 32 characters for security
    - DATABASE_URL: PostgreSQL connection string
    - OPENAI_API_KEY: Required for Physical Fitness, Mental Fitness, and Coordinator agents
    - GOOGLE_GEMINI_API_KEY: Required for Nutrition Agent (image analysis and meal planning)
    
    Optional (application continues but feature is disabled if missing):
    - TAVILY_API_KEY: Enables web search functionality for all agents
    
    Raises:
        ValueError: If any required environment variables are missing or invalid.
        The error message includes details about which variables failed validation.
    
    Note:
        This validation happens before any requests are processed, ensuring
        the application fails fast if misconfigured rather than failing during
        runtime when these values are needed. Optional variables are logged as
        warnings but do not prevent application startup.
    """
    # Dictionary defining required environment variables and their validation rules
    # Each entry specifies if the variable is required, minimum length (if applicable),
    # and a human-readable description for error messages
    required_vars = {
        "JWT_SECRET_KEY": {
            "required": True,
            "min_length": 32,  # Minimum length for cryptographic security
            "description": "JWT secret key for token signing (must be at least 32 characters)"
        },
        "DATABASE_URL": {
            "required": True,
            "description": "PostgreSQL database connection string"
        },
        "OPENAI_API_KEY": {
            "required": True,
            "description": "OpenAI API key for Physical Fitness, Mental Fitness, and Coordinator agents"
        },
        "GOOGLE_GEMINI_API_KEY": {
            "required": True,
            "description": "Google Gemini API key for Nutrition Agent (required for image analysis and meal planning)"
        }
    }
    
    # Optional variables - checked but don't fail startup if missing
    # These enable optional features but the application can function without them
    # Missing optional variables are logged as warnings to inform administrators
    optional_vars = {
        "TAVILY_API_KEY": {
            "description": "Tavily API key for web search functionality (optional - web search will be unavailable if not set)"
        }
    }
    
    # Lists to collect validation errors
    # These will be used to construct user-friendly error messages
    missing_vars = []  # Variables that are required but not set
    invalid_vars = []  # Variables that are set but don't meet validation criteria
    
    # Iterate through each required variable and validate it
    for var_name, config in required_vars.items():
        value = os.getenv(var_name)
        
        # Check if variable is missing
        if not value:
            if config["required"]:
                # Add to missing list with description for better error messages
                missing_vars.append(f"{var_name} ({config['description']})")
        else:
            # Variable exists, check if it meets validation criteria
            # Validate minimum length if specified (e.g., JWT_SECRET_KEY must be >= 32 chars)
            if "min_length" in config and len(value) < config["min_length"]:
                invalid_vars.append(
                    f"{var_name}: must be at least {config['min_length']} characters long "
                    f"(current length: {len(value)})"
                )
    
    # Check optional variables and log warnings if missing
    # Unlike required variables, missing optional variables don't prevent startup
    # but are logged so administrators know which optional features are unavailable
    for var_name, config in optional_vars.items():
        value = os.getenv(var_name)
        if not value:
            logger.warning(
                f"Optional environment variable {var_name} is not set. "
                f"{config['description']}"
            )
    
    # If any required variables are missing, fail startup with detailed error
    if missing_vars:
        error_msg = "Missing required environment variables:\n" + "\n".join(f"  - {var}" for var in missing_vars)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # If any variables are invalid (e.g., too short), fail startup with detailed error
    if invalid_vars:
        error_msg = "Invalid environment variables:\n" + "\n".join(f"  - {var}" for var in invalid_vars)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # All validations passed
    logger.info("Environment validation passed - all required variables are set and valid")
    
    # Log status of optional variables for visibility
    # This helps administrators understand which optional features are available
    # TAVILY_API_KEY enables web search functionality across all agents
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        logger.info("TAVILY_API_KEY is set - web search functionality is enabled")
    else:
        logger.info("TAVILY_API_KEY is not set - web search functionality will be unavailable")

# Register error handlers
# This middleware catches exceptions and transforms them into proper HTTP responses
# Must be registered before other middleware to catch all errors
from app.middleware.error_handler import register_error_handlers
register_error_handlers(app)

# Configure CORS (Cross-Origin Resource Sharing)
# CORS allows the frontend (running on a different origin) to make requests to this API
# Load allowed origins from environment variable (comma-separated list)
# Default to localhost ports 3000 and 3001 for local development
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
# Parse comma-separated string into list, stripping whitespace and filtering empty strings
allowed_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

# Add CORS middleware to the application
# This middleware handles CORS headers for all requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # List of allowed origins from environment variable
    allow_credentials=True,  # Allow cookies and authentication headers
    # Restrict to only the HTTP methods we actually use
    # OPTIONS is included for CORS preflight requests
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    # Restrict to only the headers we actually need
    # Content-Type for request bodies, Authorization for JWT tokens
    allow_headers=["Content-Type", "Authorization"],
)

@app.get("/")
async def root():
    """
    Root endpoint - API information.
    
    Returns basic information about the API including name and version.
    Useful for API discovery and verification that the server is running.
    
    Returns:
        dict: Dictionary containing API name and version number.
            Example: {"message": "Holos API", "version": "0.1.0"}
    """
    return {"message": "Holos API", "version": "0.1.0"}

@app.get("/health")
async def health():
    """
    Health check endpoint for monitoring and load balancers.
    
    This endpoint is used by monitoring systems, load balancers, and orchestration
    platforms (like Kubernetes) to verify that the application is running and
    ready to accept requests. Returns a simple status indicator.
    
    Returns:
        dict: Dictionary with health status.
            Example: {"status": "healthy"}
    
    Note:
        This is a basic health check. For more detailed health information,
        consider adding checks for database connectivity, external API availability, etc.
    """
    return {"status": "healthy"}

# Include routers
# Import all router modules - each router handles a specific domain of endpoints
from app.routers import auth, medical, agents, preferences, conversation, logs, cache

# Register routers with the FastAPI application
# Order matters: more specific routes should be registered before more general ones
# However, FastAPI handles route matching intelligently, so this order is primarily
# for clarity and potential future route conflicts
app.include_router(auth.router)          # Authentication endpoints (/auth/*)
app.include_router(medical.router)       # Medical history endpoints (/medical/*)
app.include_router(agents.router)        # AI agent endpoints (/agents/*)
app.include_router(preferences.router)    # User preferences endpoints (/preferences/*)
app.include_router(conversation.router)   # Conversation endpoints (/conversation/*)
app.include_router(logs.router)         # Log endpoints (/logs/*)
app.include_router(cache.router)        # Cache management endpoints (/cache/*)

# Serve uploaded images statically
# This allows the frontend to access uploaded images via URL paths
# Path object for the uploads directory - relative to project root
uploads_dir = Path("uploads/images")
# Create directory structure if it doesn't exist
# parents=True creates parent directories, exist_ok=True prevents errors if directory exists
uploads_dir.mkdir(parents=True, exist_ok=True)
# Mount static file directory at /uploads URL path
# This makes files in the "uploads" directory accessible at /uploads/* URLs
# The "name" parameter is used for reverse URL generation
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

if __name__ == "__main__":
    """
    Run the application directly (for development).
    
    This block allows running the application directly with: python app/main.py
    In production, use a proper ASGI server like uvicorn via command line or
    a process manager like systemd, supervisor, or Docker.
    
    Configuration:
    - host="0.0.0.0": Listen on all network interfaces (accessible from outside localhost)
    - port=8000: Default FastAPI development port
    - reload=True: Enable auto-reload on code changes (development only)
    """
    import uvicorn
    # Run the FastAPI application using uvicorn ASGI server
    # reload=True enables automatic reloading when code changes (development mode)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

