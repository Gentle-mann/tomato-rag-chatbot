"""Embedding service using BGE-M3 for multilingual dense + sparse embeddings."""

from typing import Dict, List, Optional, Tuple
import structlog
from FlagEmbedding import BGEM3FlagModel

from app.config import settings

logger = structlog.get_logger()


class EmbeddingService:
    """
    Embedding service using BGE-M3 model via FlagEmbedding.

    Produces both dense vectors (1024-dim) and sparse lexical weights,
    matching the CLI ingestion pipeline (ingest_utils.py) for consistency.
    """

    def __init__(self):
        self.model_name = settings.embedding_model
        self.model = None  # type: Optional[BGEM3FlagModel]
        self._initialized = False

    async def initialize(self):
        """Initialize the embedding model."""
        if self._initialized:
            return

        logger.info("Loading BGE-M3 embedding model", model=self.model_name)
        try:
            self.model = BGEM3FlagModel(self.model_name, use_fp16=False)
            self._initialized = True
            logger.info("BGE-M3 embedding model loaded (dense + sparse)")
        except Exception as e:
            logger.error("Failed to load embedding model", error=str(e))
            raise

    async def embed_documents(self, documents: List[str]) -> Tuple[List, List[Dict]]:
        """
        Generate dense + sparse embeddings for multiple documents.

        Returns:
            Tuple of (dense_vecs, sparse_weights):
                dense_vecs: list of 1024-dim vectors
                sparse_weights: list of {token_id: weight} dicts
        """
        if not self._initialized:
            await self.initialize()

        if not documents:
            return [], []

        batch_size = 32
        all_dense = []
        all_sparse = []

        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            output = self.model.encode(batch, return_dense=True, return_sparse=True)
            all_dense.extend(output["dense_vecs"])
            all_sparse.extend(output["lexical_weights"])

            logger.debug(
                "Embedded batch",
                batch_start=i,
                batch_size=len(batch),
                total=len(documents),
            )

        return all_dense, all_sparse

    async def embed_query(self, query: str) -> Tuple[List[float], Dict]:
        """Generate dense + sparse embedding for a single query."""
        if not self._initialized:
            await self.initialize()

        output = self.model.encode([query], return_dense=True, return_sparse=True)
        dense = output["dense_vecs"][0].tolist()
        sparse = output["lexical_weights"][0]
        return dense, sparse

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return settings.embedding_dimension


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


async def get_embedding_service() -> EmbeddingService:
    """Get embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
        await _embedding_service.initialize()
    return _embedding_service
