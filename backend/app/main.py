"""
Holos - AI Fitness Application Backend
FastAPI main application entry point
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os
from pathlib import Path

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Holos API",
    description="AI-powered fitness application with specialized agents",
    version="0.1.0"
)

# Validate environment variables at startup
@app.on_event("startup")
async def validate_environment():
    """Validate required environment variables at application startup"""
    required_vars = {
        "JWT_SECRET_KEY": {
            "required": True,
            "min_length": 32,
            "description": "JWT secret key for token signing (must be at least 32 characters)"
        },
        "DATABASE_URL": {
            "required": True,
            "description": "PostgreSQL database connection string"
        },
        "OPENAI_API_KEY": {
            "required": True,
            "description": "OpenAI API key for Physical Fitness, Mental Fitness, and Coordinator agents"
        }
    }
    
    missing_vars = []
    invalid_vars = []
    
    for var_name, config in required_vars.items():
        value = os.getenv(var_name)
        
        if not value:
            if config["required"]:
                missing_vars.append(f"{var_name} ({config['description']})")
        else:
            # Validate minimum length if specified
            if "min_length" in config and len(value) < config["min_length"]:
                invalid_vars.append(
                    f"{var_name}: must be at least {config['min_length']} characters long "
                    f"(current length: {len(value)})"
                )
    
    if missing_vars:
        error_msg = "Missing required environment variables:\n" + "\n".join(f"  - {var}" for var in missing_vars)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    if invalid_vars:
        error_msg = "Invalid environment variables:\n" + "\n".join(f"  - {var}" for var in invalid_vars)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("Environment validation passed - all required variables are set and valid")

# Register error handlers
from app.middleware.error_handler import register_error_handlers
register_error_handlers(app)

# Configure CORS
# Load allowed origins from environment variable (comma-separated)
# Default to localhost for development
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
allowed_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    # Restrict to only the HTTP methods we actually use
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    # Restrict to only the headers we actually need
    allow_headers=["Content-Type", "Authorization"],
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Holos API", "version": "0.1.0"}

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

# Include routers
from app.routers import auth, medical, agents, preferences, conversation, logs, cache
app.include_router(auth.router)
app.include_router(medical.router)
app.include_router(agents.router)
app.include_router(preferences.router)
app.include_router(conversation.router)
app.include_router(logs.router)
app.include_router(cache.router)

# Serve uploaded images statically
uploads_dir = Path("uploads/images")
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

