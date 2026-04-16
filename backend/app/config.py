"""Configuration management for the Tomato RAG Chatbot."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Tomato RAG Chatbot"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/tomato_rag",
        description="PostgreSQL connection URL"
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL"
    )

    # Qdrant Vector Database
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant server URL"
    )
    qdrant_collection_name: str = "tomato_cultivation"

    # LLM Configuration
    llm_provider: Literal["openai", "anthropic", "ollama"] = "openai"
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048

    # API Keys
    openai_api_key: str = Field(default="", description="OpenAI API key")
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    llama_cloud_api_key: str = Field(default="", description="LlamaParse API key")
    google_cloud_project: str = Field(default="", description="Google Cloud project ID")

    # Embedding Configuration
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024

    # Document Processing
    chunk_size: int = 512
    chunk_overlap: int = 50
    max_chunks_per_query: int = 5

    # Translation
    default_response_language: str = "en"
    supported_languages: list[str] = ["en", "ne", "ja"]

    # Retrieval
    retrieval_top_k: int = 10
    rerank_top_k: int = 5
    similarity_threshold: float = 0.5

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
