"""Document management API endpoints."""

import os
from pathlib import Path
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.config import settings
from app.core.database import get_db
from app.services.document_processor import DocumentProcessor, get_document_processor
from app.models.document import Document, DocumentStatus

logger = structlog.get_logger()
router = APIRouter()

# Data directory for uploaded PDFs
DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[5] / "data" / "pdfs")))
DATA_DIR.mkdir(parents=True, exist_ok=True)


class DocumentUploadResponse(BaseModel):
    """Response after document upload."""

    document_id: str
    filename: str
    status: str
    message: str


class DocumentInfo(BaseModel):
    """Document information model."""

    id: str
    filename: str
    status: str
    region: str = "global"
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    created_at: str
    processed_at: Optional[str] = None
    error_message: Optional[str] = None


class DocumentListResponse(BaseModel):
    """List of documents response."""

    documents: List[DocumentInfo]
    total: int


class ProcessingStatusResponse(BaseModel):
    """Document processing status response."""

    document_id: str
    status: str
    progress: float = Field(ge=0.0, le=1.0)
    message: str


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    region: str = Form("global"),
    db: AsyncSession = Depends(get_db),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """
    Upload a PDF document for processing.

    The document will be processed in the background:
    1. Extract text and tables
    2. Clean and chunk content
    3. Generate embeddings
    4. Store in vector database
    """
    # Validate file type
    allowed_ext = (".pdf", ".csv")
    if not file.filename.lower().endswith(allowed_ext):
        raise HTTPException(
            status_code=400,
            detail="Only PDF and CSV files are supported",
        )

    # Generate unique document ID
    document_id = str(uuid.uuid4())

    # Save file to disk (preserve extension for CSV support)
    ext = Path(file.filename).suffix.lower()
    file_path = DATA_DIR / f"{document_id}{ext}"
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error("Failed to save uploaded file", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Create document record in database
    document = Document(
        id=document_id,
        filename=file.filename,
        file_path=str(file_path),
        status=DocumentStatus.PENDING,
        region=region,
    )
    db.add(document)
    await db.commit()

    # Schedule background processing
    background_tasks.add_task(
        processor.process_document,
        document_id=document_id,
        file_path=str(file_path),
        region=region,
    )

    logger.info("Document uploaded", document_id=document_id, filename=file.filename)

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename,
        status="pending",
        message="Document uploaded successfully. Processing will begin shortly.",
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all uploaded documents with their processing status."""
    from sqlalchemy import select, func

    # Get total count
    count_query = select(func.count(Document.id))
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get documents
    query = select(Document).offset(skip).limit(limit).order_by(Document.created_at.desc())
    result = await db.execute(query)
    documents = result.scalars().all()

    return DocumentListResponse(
        documents=[
            DocumentInfo(
                id=doc.id,
                filename=doc.filename,
                status=doc.status.value,
                region=getattr(doc, "region", "global") or "global",
                page_count=doc.page_count,
                chunk_count=doc.chunk_count,
                created_at=doc.created_at.isoformat(),
                processed_at=doc.processed_at.isoformat() if doc.processed_at else None,
                error_message=doc.error_message,
            )
            for doc in documents
        ],
        total=total,
    )


@router.get("/documents/{document_id}", response_model=DocumentInfo)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get information about a specific document."""
    from sqlalchemy import select

    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentInfo(
        id=document.id,
        filename=document.filename,
        status=document.status.value,
        region=getattr(document, "region", "global") or "global",
        page_count=document.page_count,
        chunk_count=document.chunk_count,
        created_at=document.created_at.isoformat(),
        processed_at=document.processed_at.isoformat() if document.processed_at else None,
        error_message=document.error_message,
    )


@router.get("/documents/{document_id}/status", response_model=ProcessingStatusResponse)
async def get_processing_status(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the processing status of a document."""
    from sqlalchemy import select

    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Calculate progress based on status
    progress_map = {
        DocumentStatus.PENDING: 0.0,
        DocumentStatus.EXTRACTING: 0.25,
        DocumentStatus.CHUNKING: 0.50,
        DocumentStatus.EMBEDDING: 0.75,
        DocumentStatus.COMPLETED: 1.0,
        DocumentStatus.FAILED: 0.0,
    }

    message_map = {
        DocumentStatus.PENDING: "Waiting to start processing",
        DocumentStatus.EXTRACTING: "Extracting text from PDF",
        DocumentStatus.CHUNKING: "Chunking and cleaning text",
        DocumentStatus.EMBEDDING: "Generating embeddings",
        DocumentStatus.COMPLETED: "Processing complete",
        DocumentStatus.FAILED: f"Processing failed: {document.error_message or 'Unknown error'}",
    }

    return ProcessingStatusResponse(
        document_id=document_id,
        status=document.status.value,
        progress=progress_map[document.status],
        message=message_map[document.status],
    )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """
    Delete a document and its associated data.

    This will:
    1. Remove the document from the database
    2. Delete vectors from Qdrant
    3. Remove the PDF file
    """
    from sqlalchemy import select, delete

    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from vector store
    await processor.delete_document_vectors(document_id)

    # Delete file
    if document.file_path and os.path.exists(document.file_path):
        os.remove(document.file_path)

    # Delete from database
    await db.execute(delete(Document).where(Document.id == document_id))
    await db.commit()

    logger.info("Document deleted", document_id=document_id)

    return {"status": "deleted", "document_id": document_id}


@router.post("/documents/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """Reprocess a document that failed or needs updating."""
    from sqlalchemy import select

    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status == DocumentStatus.EXTRACTING or document.status == DocumentStatus.CHUNKING or document.status == DocumentStatus.EMBEDDING:
        raise HTTPException(
            status_code=400,
            detail="Document is currently being processed",
        )

    # Reset status
    document.status = DocumentStatus.PENDING
    document.error_message = None
    await db.commit()

    # Schedule reprocessing
    background_tasks.add_task(
        processor.process_document,
        document_id=document_id,
        file_path=document.file_path,
    )

    return {
        "status": "reprocessing",
        "document_id": document_id,
        "message": "Document reprocessing scheduled",
    }
