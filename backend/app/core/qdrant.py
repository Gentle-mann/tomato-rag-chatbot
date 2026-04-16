"""Qdrant vector database client and initialization."""

from typing import Dict, List, Optional

from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, SparseVector
import structlog

from app.config import settings

logger = structlog.get_logger()

# Sync client for embeddings
qdrant_client: Optional[QdrantClient] = None

# Async client for API operations
async_qdrant_client: Optional[AsyncQdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """Get synchronous Qdrant client."""
    global qdrant_client
    if qdrant_client is None:
        qdrant_client = QdrantClient(url=settings.qdrant_url)
    return qdrant_client


async def get_async_qdrant_client() -> AsyncQdrantClient:
    """Get asynchronous Qdrant client."""
    global async_qdrant_client
    if async_qdrant_client is None:
        async_qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)
    return async_qdrant_client


async def init_qdrant():
    """Initialize Qdrant collection for tomato cultivation documents."""
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    # Check if collection exists
    collections = client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if collection_name not in collection_names:
        logger.info(f"Creating Qdrant collection: {collection_name}")
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": VectorParams(
                    size=settings.embedding_dimension,
                    distance=Distance.COSINE,
                ),
            },
            # Enable sparse vectors for hybrid search
            sparse_vectors_config={
                "sparse": {},
            },
        )
        logger.info(f"Collection {collection_name} created successfully")
    else:
        logger.info(f"Collection {collection_name} already exists")


async def add_documents_to_qdrant(
    documents: List[Dict],
    dense_vecs: List,
    sparse_weights: List[Dict],
):
    """Add documents with dense+sparse embeddings to Qdrant.

    Payload format matches ingest_utils.py for consistency across
    CLI and admin upload pipelines.

    Args:
        documents: List of chunk dicts with text, source_type, source_name,
                   page, section, sub_section, timestamp, region.
        dense_vecs: List of dense embedding vectors (1024-dim).
        sparse_weights: List of {token_id: weight} dicts for sparse vectors.
    """
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    points = []
    for doc, dense_vec, sparse_w in zip(documents, dense_vecs, sparse_weights):
        point_id = doc.get("id", doc.get("source", ""))

        sparse_indices = [int(k) for k in sparse_w.keys()]
        sparse_values = [float(v) for v in sparse_w.values()]

        points.append(
            PointStruct(
                id=point_id,
                vector={
                    "dense": dense_vec.tolist() if hasattr(dense_vec, 'tolist') else dense_vec,
                    "sparse": SparseVector(
                        indices=sparse_indices,
                        values=sparse_values,
                    ),
                },
                payload={
                    "text": doc["text"],
                    "source_type": doc.get("source_type", "manual"),
                    "source_name": doc.get("source_name", ""),
                    "page": doc.get("page", 0),
                    "section": doc.get("section", "General"),
                    "sub_section": doc.get("sub_section"),
                    "timestamp": doc.get("timestamp"),
                    "region": doc.get("region", "global"),
                },
            )
        )

    # Upsert in batches to avoid Qdrant payload size limit (~32MB)
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(collection_name=collection_name, points=batch)
    logger.info(f"Added {len(points)} documents to Qdrant (in {(len(points) - 1) // batch_size + 1} batches)")


async def search_qdrant(
    query_embedding: List[float],
    top_k: int = 10,
    score_threshold: float = 0.5,
    filter_conditions: Optional[Dict] = None,
) -> List[Dict]:
    """Search Qdrant for similar documents."""
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    results = client.search(
        collection_name=collection_name,
        query_vector=("dense", query_embedding),
        limit=top_k,
        score_threshold=score_threshold,
        query_filter=filter_conditions,
        with_payload=True,
    )

    return [
        {
            "id": result.id,
            "score": result.score,
            "text": result.payload.get("text", ""),
            "source_type": result.payload.get("source_type", "manual"),
            "source_name": result.payload.get("source_name", ""),
            "page": result.payload.get("page", 0),
            "section": result.payload.get("section", "General"),
            "sub_section": result.payload.get("sub_section"),
            "region": result.payload.get("region", "global"),
        }
        for result in results
    ]
