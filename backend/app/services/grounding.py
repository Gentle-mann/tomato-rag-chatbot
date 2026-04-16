"""Grounding and anti-hallucination service."""

import re
from typing import List, Dict, Any, Tuple
import structlog

from app.api.v1.endpoints.chat import Citation
from app.services.embedding import EmbeddingService, get_embedding_service

logger = structlog.get_logger()


class GroundingService:
    """
    Service for verifying responses are grounded in source documents.

    Implements several anti-hallucination mechanisms:
    1. Citation extraction and validation
    2. Claim-to-source verification
    3. Confidence scoring based on semantic similarity
    """

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        self.min_confidence_threshold = 0.5

    def extract_citations(
        self,
        response: str,
        source_documents: List[Dict[str, Any]],
    ) -> List[Citation]:
        """
        Extract citations from response and match to source documents.

        Looks for patterns like [Source: Page X, Section Y] and matches
        them to the actual source documents.
        """
        citations = []
        seen = set()

        # Pattern for explicit citations
        citation_pattern = r'\[Source:\s*Page\s*(\d+),?\s*(?:Section:?\s*)?([^\]]*)\]'
        matches = re.findall(citation_pattern, response, re.IGNORECASE)

        for page_str, section in matches:
            page = int(page_str)
            section = section.strip() or "General"

            # Find matching source document
            for doc in source_documents:
                if doc.get("page") == page:
                    citation_key = f"{page}_{section}"
                    if citation_key not in seen:
                        seen.add(citation_key)
                        citations.append(
                            Citation(
                                source=doc.get("source", "unknown"),
                                page=page,
                                section=section,
                                text_excerpt=doc.get("text", "")[:200] + "...",
                                relevance_score=doc.get("score", 0.0),
                            )
                        )
                    break

        # If no explicit citations found, create from top sources
        if not citations and source_documents:
            for doc in source_documents[:3]:  # Top 3 sources
                citations.append(
                    Citation(
                        source=doc.get("source", "unknown"),
                        page=doc.get("page", 0),
                        section=doc.get("section", "General"),
                        text_excerpt=doc.get("text", "")[:200] + "...",
                        relevance_score=doc.get("score", 0.0),
                    )
                )

        return citations

    async def verify_response(
        self,
        response: str,
        source_documents: List[Dict[str, Any]],
    ) -> Tuple[bool, float]:
        """
        Verify that a response is grounded in the source documents.

        Returns:
            Tuple of (is_grounded, confidence_score)
        """
        if not source_documents:
            return False, 0.0

        # Combine all source text
        source_text = " ".join(doc.get("text", "") for doc in source_documents)

        # Extract claims from response (sentences)
        claims = self._extract_claims(response)

        if not claims:
            return True, 1.0  # No claims to verify

        # Verify each claim
        grounded_claims = 0
        total_confidence = 0.0

        for claim in claims:
            is_grounded, confidence = await self._verify_claim(claim, source_text)
            if is_grounded:
                grounded_claims += 1
            total_confidence += confidence

        # Calculate overall grounding score
        grounding_ratio = grounded_claims / len(claims)
        avg_confidence = total_confidence / len(claims)

        # Response is grounded if most claims are verified
        is_grounded = grounding_ratio >= 0.6 and avg_confidence >= self.min_confidence_threshold

        return is_grounded, avg_confidence

    def _extract_claims(self, response: str) -> List[str]:
        """Extract factual claims from response."""
        # Remove citations for claim extraction
        clean_response = re.sub(r'\[Source:[^\]]*\]', '', response)

        # Split into sentences
        sentences = re.split(r'[.!?]\s+', clean_response)

        # Filter to likely factual claims
        claims = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue
            # Skip questions and generic phrases
            if sentence.endswith('?'):
                continue
            if sentence.lower().startswith(('i ', 'you ', 'please ', 'let me ')):
                continue
            claims.append(sentence)

        return claims

    async def _verify_claim(
        self,
        claim: str,
        source_text: str,
    ) -> Tuple[bool, float]:
        """
        Verify a single claim against source text.

        Uses semantic similarity to check if the claim is supported.
        """
        # Get embeddings
        claim_embedding = await self.embedding_service.embed_query(claim)
        source_embedding = await self.embedding_service.embed_query(source_text[:2000])

        # Compute similarity
        similarity = await self.embedding_service.compute_similarity(
            claim_embedding, source_embedding
        )

        # Claim is grounded if similarity is above threshold
        is_grounded = similarity >= self.min_confidence_threshold

        return is_grounded, similarity

    def check_hallucination_indicators(self, response: str) -> List[str]:
        """
        Check for common hallucination indicators in the response.

        Returns list of potential issues found.
        """
        issues = []

        # Check for hedging language that might indicate uncertainty
        hedging_patterns = [
            r'\b(i think|i believe|probably|possibly|might be|could be)\b',
            r'\b(generally|typically|usually|often)\b',
            r'\b(in my experience|as far as i know)\b',
        ]

        for pattern in hedging_patterns:
            if re.search(pattern, response.lower()):
                issues.append(f"Hedging language detected: {pattern}")

        # Check for specific claims without citations
        specific_patterns = [
            r'\d+\s*(degrees?|°|celsius|fahrenheit)',  # Temperature claims
            r'\d+\s*(days?|weeks?|months?)',  # Time claims
            r'\d+\s*(cm|mm|meters?|inches?)',  # Measurement claims
            r'\d+\s*%',  # Percentage claims
        ]

        for pattern in specific_patterns:
            matches = re.findall(pattern, response.lower())
            if matches:
                # Check if these have citations nearby
                for match in matches:
                    context = response[max(0, response.lower().find(match) - 100):response.lower().find(match) + 100]
                    if '[source:' not in context.lower():
                        issues.append(f"Specific claim without citation: {match}")

        return issues

    def add_missing_citations(
        self,
        response: str,
        source_documents: List[Dict[str, Any]],
    ) -> str:
        """
        Add citations to claims that are missing them.

        Uses semantic matching to find the most relevant source for each claim.
        """
        # This is a simplified implementation
        # In production, you'd want more sophisticated matching

        sentences = re.split(r'([.!?]\s+)', response)
        result = []

        for i, part in enumerate(sentences):
            if re.match(r'[.!?]\s*$', part):
                result.append(part)
                continue

            # Skip if already has citation
            if '[source:' in part.lower():
                result.append(part)
                continue

            # Skip non-factual sentences
            if not part.strip() or len(part.strip()) < 20:
                result.append(part)
                continue

            # Find best matching source
            best_match = None
            best_score = 0

            for doc in source_documents:
                # Simple keyword matching
                doc_words = set(doc.get("text", "").lower().split())
                part_words = set(part.lower().split())
                overlap = len(doc_words & part_words)
                if overlap > best_score:
                    best_score = overlap
                    best_match = doc

            # Add citation if we found a good match
            if best_match and best_score > 3:
                page = best_match.get("page", "?")
                section = best_match.get("section", "General")
                citation = f" [Source: Page {page}, Section: {section}]"
                result.append(part + citation)
            else:
                result.append(part)

        return "".join(result)


# Singleton instance
_grounding_service: GroundingService | None = None


async def get_grounding_service() -> GroundingService:
    """Get grounding service instance."""
    global _grounding_service
    if _grounding_service is None:
        embedding_service = await get_embedding_service()
        _grounding_service = GroundingService(embedding_service)
    return _grounding_service
