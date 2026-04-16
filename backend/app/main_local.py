"""Simplified FastAPI application for local testing without Docker services."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    logger.info("Starting Tomato RAG Chatbot (Local Mode)", version=settings.app_version)
    yield
    logger.info("Shutting down Tomato RAG Chatbot")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Multilingual RAG Chatbot for Tomato Cultivation (Local Testing)",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "mode": "local",
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "mode": "local_testing",
    }


# Simple chat endpoint for testing LLM connection
from pydantic import BaseModel
from typing import Optional
import litellm
import os

# Configure litellm for Anthropic
os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key


class SimpleChatRequest(BaseModel):
    message: str
    language: str = "en"


class SimpleChatResponse(BaseModel):
    response: str
    model: str


@app.post("/api/v1/chat/test", response_model=SimpleChatResponse)
async def test_chat(request: SimpleChatRequest):
    """Test chat endpoint to verify LLM connection."""

    system_prompt = """You are a helpful assistant specializing in tomato cultivation.
    For this test, just respond helpfully to the user's question.
    Keep responses concise."""

    try:
        response = await litellm.acompletion(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.message},
            ],
            temperature=settings.llm_temperature,
            max_tokens=500,
        )

        return SimpleChatResponse(
            response=response.choices[0].message.content,
            model=settings.llm_model,
        )
    except Exception as e:
        logger.error("LLM error", error=str(e))
        return SimpleChatResponse(
            response=f"Error connecting to LLM: {str(e)}",
            model=settings.llm_model,
        )


@app.get("/api/v1/config")
async def get_config():
    """Get current configuration (for debugging)."""
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "has_anthropic_key": bool(settings.anthropic_api_key and settings.anthropic_api_key != "your-anthropic-api-key"),
        "has_openai_key": bool(settings.openai_api_key and settings.openai_api_key != "your-openai-api-key"),
    }
