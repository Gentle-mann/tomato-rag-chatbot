"""Main FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.config import settings
from app.api.v1.endpoints import chat, documents
from app.core.database import init_db
from app.core.qdrant import init_qdrant
from app.core.redis import init_redis

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    logger.info("Starting Tomato RAG Chatbot", version=settings.app_version)

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Initialize Qdrant
    await init_qdrant()
    logger.info("Qdrant vector store initialized")

    # Initialize Redis
    await init_redis()
    logger.info("Redis cache initialized")

    yield

    # Shutdown
    logger.info("Shutting down Tomato RAG Chatbot")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Multilingual RAG Chatbot for Tomato Cultivation",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
app.include_router(documents.router, prefix="/api/v1", tags=["Documents"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }
