"""Redis client for caching and session management."""

import json
from typing import Any

import redis.asyncio as redis
import structlog

from app.config import settings

logger = structlog.get_logger()

redis_client: redis.Redis | None = None


async def init_redis():
    """Initialize Redis connection."""
    global redis_client
    redis_client = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    # Test connection
    await redis_client.ping()
    logger.info("Redis connection established")


async def get_redis() -> redis.Redis:
    """Get Redis client."""
    global redis_client
    if redis_client is None:
        await init_redis()
    return redis_client


async def cache_get(key: str) -> Any | None:
    """Get value from cache."""
    client = await get_redis()
    value = await client.get(key)
    if value:
        return json.loads(value)
    return None


async def cache_set(key: str, value: Any, expire_seconds: int = 3600):
    """Set value in cache with expiration."""
    client = await get_redis()
    await client.set(key, json.dumps(value), ex=expire_seconds)


async def cache_delete(key: str):
    """Delete key from cache."""
    client = await get_redis()
    await client.delete(key)


async def get_conversation_history(session_id: str) -> list[dict]:
    """Get conversation history for a session."""
    key = f"conversation:{session_id}"
    history = await cache_get(key)
    return history or []


async def add_to_conversation(
    session_id: str,
    role: str,
    content: str,
    citations: list[dict] | None = None,
):
    """Add message to conversation history."""
    key = f"conversation:{session_id}"
    history = await get_conversation_history(session_id)

    message = {
        "role": role,
        "content": content,
    }
    if citations:
        message["citations"] = citations

    history.append(message)

    # Keep last 50 messages
    if len(history) > 50:
        history = history[-50:]

    await cache_set(key, history, expire_seconds=86400)  # 24 hours


async def clear_conversation(session_id: str):
    """Clear conversation history for a session."""
    key = f"conversation:{session_id}"
    await cache_delete(key)
