"""Feedback database model for collecting user ratings on responses."""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Integer, Text, DateTime, Enum, Boolean

from app.core.database import Base


class FeedbackRating(enum.Enum):
    """Feedback rating type."""
    POSITIVE = "positive"
    NEGATIVE = "negative"


class Feedback(Base):
    """Model for storing user feedback on chatbot responses."""

    __tablename__ = "feedback"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), nullable=False)
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    language = Column(String(10), default="en")
    rating = Column(Enum(FeedbackRating), nullable=False)
    comment = Column(Text, nullable=True)
    citations_count = Column(Integer, default=0)
    had_answer = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Feedback(id={self.id}, rating={self.rating}, session={self.session_id[:8]}...)>"
