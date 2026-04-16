"""Document database models."""

import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, Enum
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class DocumentStatus(enum.Enum):
    """Document processing status."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    """Document model for tracking uploaded PDFs."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)

    # Processing metadata
    page_count = Column(Integer, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    # Document metadata extracted from PDF
    title = Column(String(512), nullable=True)
    author = Column(String(255), nullable=True)
    language = Column(String(10), default="ja")
    region = Column(String(50), default="global")
    extra_metadata = Column("metadata", JSONB, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status})>"
