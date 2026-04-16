"""Document processing pipeline for PDF and CSV ingestion."""

import csv
import io
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF
import structlog
from llama_index.core import Document as LlamaDocument
from llama_index.core.node_parser import SentenceSplitter

from app.config import settings
from app.core.database import async_session_maker
from app.core.qdrant import add_documents_to_qdrant
from app.models.document import Document, DocumentStatus
from app.services.embedding import EmbeddingService, get_embedding_service

logger = structlog.get_logger()

# Import shared utilities from CLI ingestion scripts.
# These ensure admin uploads produce identical results to CLI ingestion.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Sub-section detection + character-based chunking (from ingest_utils.py)
try:
    from ingest_utils import detect_sub_section, chunk_text as char_chunk_text
except ImportError:
    def detect_sub_section(text):
        patterns = [
            (re.compile(r"摘芯|摘心"), "topping"),
            (re.compile(r"摘葉|葉かき|下葉"), "leaf_removal"),
            (re.compile(r"芽かき|脇芽|わき芽|側枝"), "de_suckering"),
            (re.compile(r"摘果|着果制限"), "fruit_thinning"),
            (re.compile(r"整枝|誘引|仕立て"), "training"),
        ]
        for pattern, label in patterns:
            if pattern.search(text):
                return label
        return None

    def char_chunk_text(text, chunk_size=300, overlap=100):
        text = text.strip()
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if end < len(text):
                for boundary in ["。", "\n", "。\n"]:
                    last_break = chunk.rfind(boundary, max(0, len(chunk) - 50))
                    if last_break != -1:
                        end = start + last_break + len(boundary)
                        chunk = text[start:end]
                        break
            chunks.append(chunk.strip())
            start = end - overlap
        return chunks

# PDF-specific utilities (sidebar stripping, table noise filter, OCR)
try:
    from process_pdf import clean_text as pdf_clean_text, is_table_noise, ocr_page
except ImportError:
    pdf_clean_text = None
    is_table_noise = None
    ocr_page = None

# Japanese text processing
try:
    import fugashi
    import jaconv
    FUGASHI_AVAILABLE = True
    tagger = fugashi.Tagger()
except ImportError:
    FUGASHI_AVAILABLE = False
    logger.warning("fugashi not available, Japanese text processing will be limited")


class DocumentProcessor:
    """Process PDF and CSV documents for RAG pipeline."""

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap

    async def process_document(self, document_id: str, file_path: str, region: str = "global"):
        """
        Process a document through the full pipeline.

        Supports PDF and CSV files. Steps:
        1. Extract text (PDF: PyMuPDF; CSV: parse rows into text)
        2. Clean and normalize text
        3. Chunk content semantically
        4. Generate dense + sparse embeddings (BGE-M3)
        5. Store in Qdrant with correct payload format
        """
        async with async_session_maker() as db:
            try:
                # Determine file type
                is_csv = file_path.lower().endswith('.csv')

                # Fetch original filename from DB (the file is saved as {uuid}.pdf)
                from sqlalchemy import select
                result = await db.execute(
                    select(Document.filename).where(Document.id == document_id)
                )
                original_filename = result.scalar()
                source_name = original_filename or Path(file_path).name

                # Update status to extracting
                await self._update_status(db, document_id, DocumentStatus.EXTRACTING)

                # Extract content
                logger.info("Extracting content", document_id=document_id, file_type="CSV" if is_csv else "PDF")
                if is_csv:
                    pages = await self._extract_csv_content(file_path)
                else:
                    pages = await self._extract_pdf_content(file_path)
                page_count = len(pages)

                # Update status to chunking
                await self._update_status(db, document_id, DocumentStatus.CHUNKING)

                # Clean and chunk content
                logger.info("Chunking content", document_id=document_id, pages=page_count)
                chunks = await self._chunk_content(pages, document_id, source_name, region)
                chunk_count = len(chunks)

                # Update status to embedding
                await self._update_status(db, document_id, DocumentStatus.EMBEDDING)

                # Generate dense + sparse embeddings using BGE-M3
                logger.info("Generating embeddings", document_id=document_id, chunks=chunk_count)
                dense_vecs, sparse_weights = await self.embedding_service.embed_documents(
                    [chunk["text"] for chunk in chunks]
                )

                # Store in Qdrant with correct payload format
                logger.info("Storing in Qdrant", document_id=document_id)
                await add_documents_to_qdrant(chunks, dense_vecs, sparse_weights)

                # Mark as completed
                await self._update_status(
                    db,
                    document_id,
                    DocumentStatus.COMPLETED,
                    page_count=page_count,
                    chunk_count=chunk_count,
                )

                logger.info(
                    "Document processing completed",
                    document_id=document_id,
                    pages=page_count,
                    chunks=chunk_count,
                )

            except Exception as e:
                logger.error("Document processing failed", document_id=document_id, error=str(e))
                await self._update_status(
                    db,
                    document_id,
                    DocumentStatus.FAILED,
                    error_message=str(e),
                )
                raise

    async def _extract_pdf_content(self, file_path: str) -> List[Dict]:
        """Extract text and tables from PDF using PyMuPDF.

        Uses the same cleaning pipeline as process_pdf.py (sidebar stripping,
        OCR fallback for image pages) when available.
        """
        pages = []
        doc = fitz.open(file_path)

        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text")

            # OCR fallback for image-based pages (same as CLI)
            images = page.get_images()
            if len(text.strip()) < 20 and len(images) > 0 and ocr_page is not None:
                try:
                    text = ocr_page(page)
                    if text.strip():
                        logger.info("OCR extracted text", page=page_num, chars=len(text))
                except Exception as e:
                    logger.warning("OCR failed", page=page_num, error=str(e))

            # Use CLI's clean_text (with sidebar stripping) if available
            if pdf_clean_text is not None:
                cleaned_text = pdf_clean_text(text)
            else:
                cleaned_text = self._clean_text(text)

            # Extract tables
            table_text = ""
            try:
                table_finder = page.find_tables()
                for table in table_finder:
                    table_data = table.extract()
                    if table_data:
                        table_text += "\n" + self._table_to_text(table_data)
            except Exception:
                pass

            combined = cleaned_text
            if table_text.strip():
                combined += "\n\n" + table_text.strip()

            if combined.strip():
                pages.append({
                    "page_number": page_num,
                    "text": combined.strip(),
                    "tables": [],
                    "has_images": len(images) > 0,
                })

        doc.close()
        return pages

    async def _extract_csv_content(self, file_path: str) -> List[Dict]:
        """Extract content from a CSV file.

        Reads CSV rows and groups them into page-like blocks.
        Each block of ~50 rows becomes a 'page' for chunking.
        """
        pages = []
        rows_per_page = 50

        # Try multiple encodings for Japanese CSV
        content = None
        for encoding in ["utf-8", "shift_jis", "cp932", "euc-jp"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            raise ValueError("Could not decode CSV file with any supported encoding")

        reader = csv.reader(io.StringIO(content))
        rows = list(reader)

        if not rows:
            return []

        headers = rows[0]
        data_rows = rows[1:]

        # Convert rows to readable text blocks
        for page_idx in range(0, len(data_rows), rows_per_page):
            block_rows = data_rows[page_idx:page_idx + rows_per_page]
            text_parts = []
            for row in block_rows:
                parts = []
                for idx, cell in enumerate(row):
                    if cell and cell.strip() and idx < len(headers) and headers[idx].strip():
                        parts.append(f"{headers[idx].strip()}: {cell.strip()}")
                if parts:
                    text_parts.append(", ".join(parts))

            if text_parts:
                pages.append({
                    "page_number": (page_idx // rows_per_page) + 1,
                    "text": "\n".join(text_parts),
                    "tables": [],
                    "has_images": False,
                })

        return pages

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text, especially Japanese content."""
        if not text:
            return ""

        text = text.strip()

        if FUGASHI_AVAILABLE:
            text = jaconv.z2h(text, kana=False, digit=True, ascii=True)

        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^-\s*\d+\s*-$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    async def _chunk_content(self, pages: List[Dict], document_id: str, source_name: str, region: str = "global") -> List[Dict]:
        """Chunk document content using character-based chunking.

        Uses the same chunking strategy as the CLI pipeline (process_pdf.py):
        300 chars, 100 overlap, sentence-boundary-aware splitting.

        Produces chunks with the same payload fields as ingest_utils.py:
        id, text, source_type, source_name, page, section, sub_section, timestamp, region
        """
        chunks = []

        for page in pages:
            if not page["text"]:
                continue

            page_chunks = char_chunk_text(page["text"])

            for idx, chunk_text in enumerate(page_chunks):
                # Skip short chunks and table noise (same as CLI)
                if len(chunk_text) < 50:
                    continue
                if is_table_noise is not None and is_table_noise(chunk_text):
                    continue

                section = self._detect_section(chunk_text)
                sub_section = detect_sub_section(chunk_text)

                chunks.append({
                    "id": str(uuid.uuid4()),
                    "text": chunk_text,
                    "source_type": "manual",
                    "source_name": source_name,
                    "page": page["page_number"],
                    "section": section,
                    "sub_section": sub_section,
                    "timestamp": None,
                    "region": region,
                })

        return chunks

    def _table_to_text(self, table: list) -> str:
        """Convert table data to readable text format."""
        if not table or len(table) < 2:
            return ""

        rows = []
        headers = table[0]

        for row in table[1:]:
            row_text = []
            for idx, cell in enumerate(row):
                if cell and idx < len(headers) and headers[idx]:
                    row_text.append(f"{headers[idx]}: {cell}")
            if row_text:
                rows.append(", ".join(row_text))

        return "\n".join(rows)

    def _detect_section(self, text: str) -> str:
        """Detect section/topic from text content."""
        section_patterns = {
            r"(播種|はしゅ|seeding|種まき)": "Seeding",
            r"(育苗|いくびょう|seedling|苗)": "Seedling Care",
            r"(定植|ていしょく|transplant|植え付け)": "Transplanting",
            r"(施肥|せひ|fertiliz|肥料)": "Fertilization",
            r"(灌水|かんすい|irrigation|水やり|watering)": "Irrigation",
            r"(病害|びょうがい|disease|病気)": "Disease Management",
            r"(害虫|がいちゅう|pest|虫)": "Pest Control",
            r"(収穫|しゅうかく|harvest|採)": "Harvesting",
            r"(剪定|せんてい|pruning|整枝)": "Pruning",
            r"(温度|おんど|temperature|気温)": "Temperature Management",
            r"(品種|ひんしゅ|variety|種類)": "Varieties",
            r"(農薬|pesticide|殺虫|殺菌|薬剤)": "Pesticides",
            r"(栽培|さいばい|cultivation|育て方)": "General Cultivation",
        }

        text_lower = text.lower()
        for pattern, section in section_patterns.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                return section

        return "General"

    async def delete_document_vectors(self, document_id: str):
        """Delete all vectors associated with a document from Qdrant."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        from app.core.qdrant import get_qdrant_client

        client = get_qdrant_client()

        # Try both payload formats (source for old uploads, source_name for new)
        for key in ["source", "source_name"]:
            try:
                client.delete(
                    collection_name=settings.qdrant_collection_name,
                    points_selector=Filter(
                        must=[
                            FieldCondition(
                                key=key,
                                match=MatchValue(value=document_id),
                            )
                        ]
                    ),
                )
            except Exception:
                pass

        logger.info("Deleted vectors for document", document_id=document_id)

    async def _update_status(
        self,
        db,
        document_id: str,
        status: DocumentStatus,
        page_count: Optional[int] = None,
        chunk_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        """Update document processing status in database."""
        from sqlalchemy import update

        stmt = (
            update(Document)
            .where(Document.id == document_id)
            .values(
                status=status,
                page_count=page_count,
                chunk_count=chunk_count,
                error_message=error_message,
                processed_at=datetime.utcnow() if status == DocumentStatus.COMPLETED else None,
            )
        )
        await db.execute(stmt)
        await db.commit()


# Singleton instance
_document_processor: Optional[DocumentProcessor] = None


async def get_document_processor() -> DocumentProcessor:
    """Get document processor instance."""
    global _document_processor
    if _document_processor is None:
        embedding_service = await get_embedding_service()
        _document_processor = DocumentProcessor(embedding_service)
    return _document_processor
