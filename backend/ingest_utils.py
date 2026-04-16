"""Shared utilities for PDF and transcript ingestion into Qdrant."""

import os
import re
import uuid
from typing import List, Optional

from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    SparseVector,
    Filter,
    FieldCondition,
    MatchValue,
)
import redis

# Configuration
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
COLLECTION_NAME = "tomato_cultivation"
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024
CHUNK_SIZE = 300
CHUNK_OVERLAP = 100

# Singletons
_embedding_model = None
_qdrant_client = None


def get_embedding_model():
    """Return a singleton BGEM3FlagModel instance."""
    global _embedding_model
    if _embedding_model is None:
        print("Loading embedding model (this may take a minute)...")
        _embedding_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
        print(f"Model loaded: {EMBEDDING_MODEL} (dim={EMBEDDING_DIM}, sparse=enabled)")
    return _embedding_model


def get_qdrant_client():
    """Return a singleton QdrantClient instance."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=QDRANT_URL)
    return _qdrant_client


def ensure_collection():
    """Create the Qdrant collection if it does not already exist."""
    client = get_qdrant_client()
    collections = client.get_collections()
    names = [c.name for c in collections.collections]

    if COLLECTION_NAME in names:
        print(f"Collection '{COLLECTION_NAME}' already exists")
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        },
        sparse_vectors_config={"sparse": {}},
    )
    print(f"Collection '{COLLECTION_NAME}' created")


def delete_source(source_name: str):
    """Delete all points in the collection that match the given source_name."""
    client = get_qdrant_client()
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[FieldCondition(key="source_name", match=MatchValue(value=source_name))]
        ),
    )
    print(f"Deleted existing vectors for source: {source_name}")


def embed_and_upsert(
    chunks: List[dict],
    source_type: str,
    source_name: str,
    region: str = "global",
    batch_size: int = 32,
):
    """Generate dense+sparse embeddings and upsert chunks into Qdrant.

    Each chunk dict must contain:
        text (str): The chunk text.
        page (int): Page number from the source document.
        section (str): Detected section label.
        timestamp (str | None): "MM:SS" for transcripts, None for PDFs.
    """
    model = get_embedding_model()
    client = get_qdrant_client()
    points = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]

        output = model.encode(texts, return_dense=True, return_sparse=True)
        dense_vecs = output["dense_vecs"]
        sparse_weights = output["lexical_weights"]

        for chunk, dense_vec, sparse_w in zip(batch, dense_vecs, sparse_weights):
            sparse_indices = [int(k) for k in sparse_w.keys()]
            sparse_values = [float(v) for v in sparse_w.values()]

            points.append(
                PointStruct(
                    id=chunk.get("id", str(uuid.uuid4())),
                    vector={
                        "dense": dense_vec.tolist(),
                        "sparse": SparseVector(
                            indices=sparse_indices,
                            values=sparse_values,
                        ),
                    },
                    payload={
                        "text": chunk["text"],
                        "source_type": source_type,
                        "source_name": source_name,
                        "page": chunk["page"],
                        "section": chunk["section"],
                        "sub_section": chunk.get("sub_section") or detect_sub_section(chunk["text"]),
                        "timestamp": chunk.get("timestamp"),
                        "region": region,
                    },
                )
            )

        progress = min(i + batch_size, len(chunks))
        print(f"  Embedded: {progress}/{len(chunks)} chunks", end="\r")

    print()

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Upserted {len(points)} vectors into '{COLLECTION_NAME}'")
    return len(points)


def register_in_postgres(filename: str, file_path: str, page_count: int, chunk_count: int, region: str = "global"):
    """Register (or update) a processed document in PostgreSQL."""
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/tomato_rag",
    )
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        import psycopg2
        from datetime import datetime

        conn = psycopg2.connect(sync_url)
        cur = conn.cursor()

        doc_id = str(uuid.uuid4())
        now = datetime.utcnow()

        cur.execute("DELETE FROM documents WHERE filename = %s", (filename,))
        cur.execute(
            """INSERT INTO documents (id, filename, file_path, status, page_count, chunk_count, region, created_at, processed_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (doc_id, filename, file_path, "COMPLETED", page_count, chunk_count, region, now, now),
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"Registered in database: {filename} (id: {doc_id[:8]}...)")
    except Exception as e:
        print(f"Warning: Could not register in database: {e}")
        print("(Vectors are in Qdrant — chat will work, but admin UI won't show this document)")


def clear_response_cache():
    """Flush all cached chat responses from Redis."""
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        cache_keys = r.keys("cache:*")
        if cache_keys:
            r.delete(*cache_keys)
            print(f"Cleared {len(cache_keys)} cached responses from Redis")
        else:
            print("No cached responses to clear")
    except Exception as e:
        print(f"Warning: Could not clear Redis cache: {e}")


# Sub-section detection patterns for fine-grained tagging.
# Each pattern maps Japanese terms to a specific agricultural operation.
SUB_SECTION_PATTERNS = [
    # Order matters: more specific patterns first
    (re.compile(r"摘芯|摘心|てきしん"), "topping"),
    (re.compile(r"摘葉|葉かき|てきよう|はかき|下葉"), "leaf_removal"),
    (re.compile(r"芽かき|脇芽|わき芽|めかき|側枝"), "de_suckering"),
    (re.compile(r"摘果|てきか|着果制限"), "fruit_thinning"),
    (re.compile(r"整枝|誘引|仕立て"), "training"),
]


def detect_sub_section(text: str) -> Optional[str]:
    """Detect specific agricultural sub-operation from chunk text.

    Returns the most specific sub-operation found, or None if the chunk
    doesn't describe a specific operation (e.g., general text).
    """
    for pattern, label in SUB_SECTION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Split text into overlapping chunks by character count.

    Uses character-based splitting (not word-based) because Japanese
    text does not use spaces between words.
    """
    text = text.strip()
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at a sentence boundary to avoid cutting mid-sentence
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
