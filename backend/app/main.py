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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Next.js default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
from app.routers import auth, medical, agents, preferences, conversation, logs
app.include_router(auth.router)
app.include_router(medical.router)
app.include_router(agents.router)
app.include_router(preferences.router)
app.include_router(conversation.router)
app.include_router(logs.router)

# Serve uploaded images statically
uploads_dir = Path("uploads/images")
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

