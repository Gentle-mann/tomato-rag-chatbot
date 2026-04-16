"""Hybrid retrieval service with dense + sparse search."""

from typing import List, Dict, Any
import structlog

from app.config import settings
from app.core.qdrant import search_qdrant
from app.services.embedding import EmbeddingService, get_embedding_service

logger = structlog.get_logger()


class HybridRetriever:
    """
    Hybrid retrieval combining dense (semantic) and sparse (keyword) search.

    For the tomato cultivation chatbot, we use:
    - Dense search: BGE-M3 embeddings for semantic similarity
    - Sparse search: BM25-like scoring for keyword matching
    - Reranking: Cross-encoder for final relevance scoring
    """

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        self.top_k = settings.retrieval_top_k
        self.rerank_top_k = settings.rerank_top_k
        self.similarity_threshold = settings.similarity_threshold

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filter_conditions: dict | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents for a query.

        Args:
            query: The search query
            top_k: Number of results to return
            filter_conditions: Optional Qdrant filter conditions

        Returns:
            List of relevant documents with scores and metadata
        """
        top_k = top_k or self.top_k

        # Generate query embedding
        query_embedding = await self.embedding_service.embed_query(query)

        # Search Qdrant
        results = await search_qdrant(
            query_embedding=query_embedding,
            top_k=top_k * 2,  # Retrieve more for reranking
            score_threshold=self.similarity_threshold,
            filter_conditions=filter_conditions,
        )

        if not results:
            logger.info("No results found for query", query=query[:50])
            return []

        # Rerank results
        reranked = await self._rerank_results(query, results)

        # Return top results after reranking
        return reranked[:self.rerank_top_k]

    async def _rerank_results(
        self,
        query: str,
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Rerank results using a simple scoring heuristic.

        For production, consider using a cross-encoder model like
        ms-marco-MiniLM-L-6-v2 for better reranking.
        """
        # Simple reranking based on:
        # 1. Original similarity score
        # 2. Query term overlap
        # 3. Section relevance

        query_terms = set(query.lower().split())

        for result in results:
            text_lower = result["text"].lower()

            # Count query term matches
            term_matches = sum(1 for term in query_terms if term in text_lower)
            term_score = term_matches / max(len(query_terms), 1)

            # Boost for exact phrase matches
            phrase_boost = 1.2 if query.lower() in text_lower else 1.0

            # Combine scores
            original_score = result["score"]
            combined_score = (original_score * 0.7 + term_score * 0.3) * phrase_boost

            result["rerank_score"] = combined_score
            result["term_matches"] = term_matches

        # Sort by reranked score
        results.sort(key=lambda x: x["rerank_score"], reverse=True)

        return results

    async def search_by_section(
        self,
        query: str,
        section: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search within a specific section of the cultivation manual."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        filter_conditions = Filter(
            must=[
                FieldCondition(
                    key="section",
                    match=MatchValue(value=section),
                )
            ]
        )

        return await self.retrieve(
            query=query,
            top_k=top_k,
            filter_conditions=filter_conditions,
        )

    async def get_context_window(
        self,
        document_id: str,
        chunk_index: int,
        window_size: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Get surrounding chunks for better context.

        Retrieves chunks before and after the target chunk
        to provide more complete information.
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

        from app.core.qdrant import get_qdrant_client

        client = get_qdrant_client()

        # Get chunks within the window
        results = client.scroll(
            collection_name=settings.qdrant_collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=document_id),
                    ),
                    FieldCondition(
                        key="metadata.chunk_index",
                        range=Range(
                            gte=max(0, chunk_index - window_size),
                            lte=chunk_index + window_size,
                        ),
                    ),
                ]
            ),
            limit=window_size * 2 + 1,
            with_payload=True,
        )

        return [
            {
                "id": point.id,
                "text": point.payload.get("text", ""),
                "metadata": point.payload.get("metadata", {}),
                "page": point.payload.get("page", 0),
                "section": point.payload.get("section", ""),
            }
            for point in results[0]
        ]


# Singleton instance
_retriever: HybridRetriever | None = None


async def get_retriever() -> HybridRetriever:
    """Get retriever instance."""
    global _retriever
    if _retriever is None:
        embedding_service = await get_embedding_service()
        _retriever = HybridRetriever(embedding_service)
    return _retriever
