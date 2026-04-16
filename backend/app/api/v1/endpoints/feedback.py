"""Feedback API endpoints for collecting user ratings."""

import hashlib
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis as redis_lib
import structlog

from app.core.database import get_db
from app.models.feedback import Feedback, FeedbackRating

logger = structlog.get_logger()

router = APIRouter()


class FeedbackRequest(BaseModel):
    session_id: str
    query: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)
    language: str = Field(default="en")
    rating: str = Field(..., pattern="^(positive|negative)$")
    comment: Optional[str] = None
    region: Optional[str] = None
    citations_count: int = Field(default=0, ge=0)
    had_answer: bool = True


class FeedbackResponse(BaseModel):
    id: str
    status: str = "saved"


class FeedbackStats(BaseModel):
    total: int
    positive: int
    negative: int
    satisfaction_rate: float


def _evict_cached_response(query: str, language: str, region: str = None):
    """Delete cached response for a query that received negative feedback.

    This ensures the next user asking the same question gets a fresh LLM answer
    instead of a cached response that was rated poorly.
    """
    try:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        r = redis_lib.from_url(redis_url, decode_responses=True)
        normalized = query.strip().lower()
        raw = f"{normalized}:{language}:{region or 'none'}"
        key = f"cache:{hashlib.sha256(raw.encode()).hexdigest()}"
        deleted = r.delete(key)
        if deleted:
            logger.info("Evicted cached response after negative feedback",
                        query=query[:50], language=language)
    except Exception as e:
        logger.warning("Cache eviction failed (non-critical)", error=str(e))


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest, db: AsyncSession = Depends(get_db)):
    """Submit thumbs up/down feedback for a chatbot response."""
    feedback = Feedback(
        id=str(uuid.uuid4()),
        session_id=request.session_id,
        query=request.query,
        response=request.response,
        language=request.language,
        rating=FeedbackRating(request.rating),
        comment=request.comment,
        citations_count=request.citations_count,
        had_answer=request.had_answer,
    )
    db.add(feedback)
    await db.flush()

    # Evict cached response on negative feedback so next query gets a fresh answer
    if request.rating == "negative":
        _evict_cached_response(request.query, request.language, region=request.region)

    return FeedbackResponse(id=feedback.id)


@router.get("/feedback/stats", response_model=FeedbackStats)
async def get_feedback_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregated feedback statistics."""
    total_q = await db.execute(select(func.count(Feedback.id)))
    total = total_q.scalar() or 0

    positive_q = await db.execute(
        select(func.count(Feedback.id)).where(Feedback.rating == FeedbackRating.POSITIVE)
    )
    positive = positive_q.scalar() or 0

    negative = total - positive
    satisfaction_rate = round((positive / total * 100), 1) if total > 0 else 0.0

    return FeedbackStats(
        total=total,
        positive=positive,
        negative=negative,
        satisfaction_rate=satisfaction_rate,
    )
