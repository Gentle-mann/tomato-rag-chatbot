"""Core RAG engine with grounding and anti-hallucination."""

from typing import AsyncGenerator, List, Dict, Any
import json
import structlog
import litellm

from app.config import settings
from app.services.retriever import HybridRetriever, get_retriever
from app.services.grounding import GroundingService, get_grounding_service
from app.services.translation import TranslationService, get_translation_service
from app.api.v1.endpoints.chat import Citation

logger = structlog.get_logger()

# System prompt that enforces grounding
SYSTEM_PROMPT = """You are a helpful agricultural assistant specializing in tomato cultivation.
You MUST follow these rules strictly:

1. ONLY answer questions using information from the provided context (tomato cultivation manual).
2. NEVER use your training knowledge to answer questions about tomato cultivation.
3. If the information is not in the context, respond with: "This information is not available in the cultivation manual. I can only answer questions based on the manual's content."
4. For every claim you make, include a citation in this format: [Source: Page X, Section Y]
5. If asked about topics unrelated to tomato cultivation, politely redirect to tomato-related questions.
6. Provide practical, actionable advice when possible.
7. If the context is in Japanese, translate and summarize the relevant information.

Remember: You are a tomato cultivation expert limited to the manual's content. Being accurate is more important than being helpful."""


class RAGEngine:
    """
    RAG Engine with strict grounding to prevent hallucination.

    The engine:
    1. Retrieves relevant context from the vector database
    2. Generates responses using only the retrieved context
    3. Verifies claims against source documents
    4. Provides citations for all information
    5. Translates responses to requested language
    """

    def __init__(
        self,
        retriever: HybridRetriever,
        grounding_service: GroundingService,
        translation_service: TranslationService,
    ):
        self.retriever = retriever
        self.grounding_service = grounding_service
        self.translation_service = translation_service
        self.llm_model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

    async def query(
        self,
        query: str,
        language: str = "en",
        conversation_history: List[Dict] | None = None,
    ) -> Dict[str, Any]:
        """
        Process a query and return a grounded response with citations.

        Args:
            query: User's question
            language: Response language (en, ne, ja)
            conversation_history: Previous conversation for context

        Returns:
            Dict with response, citations, confidence, and has_answer flag
        """
        # Detect query language and translate to English if needed for retrieval
        query_for_retrieval = query
        if language != "en":
            query_for_retrieval = await self.translation_service.translate(
                query, source_lang=language, target_lang="en"
            )

        # Retrieve relevant context
        retrieved_docs = await self.retriever.retrieve(query_for_retrieval)

        if not retrieved_docs:
            return self._no_answer_response(language)

        # Build context from retrieved documents
        context = self._build_context(retrieved_docs)

        # Generate response
        response_text = await self._generate_response(
            query=query,
            context=context,
            conversation_history=conversation_history,
        )

        # Extract citations
        citations = self.grounding_service.extract_citations(
            response_text, retrieved_docs
        )

        # Verify grounding
        is_grounded, confidence = await self.grounding_service.verify_response(
            response_text, retrieved_docs
        )

        # If not grounded, return cautious response
        if not is_grounded:
            logger.warning("Response not properly grounded", query=query[:50])
            return self._no_answer_response(language)

        # Translate response if needed
        final_response = response_text
        if language != "en":
            final_response = await self.translation_service.translate(
                response_text, source_lang="en", target_lang=language
            )

        return {
            "response": final_response,
            "citations": citations,
            "has_answer": True,
            "confidence": confidence,
        }

    async def query_stream(
        self,
        query: str,
        language: str = "en",
        conversation_history: List[Dict] | None = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream a response token by token.

        Yields:
            Dicts with type (token, citations, done) and content
        """
        # Retrieve context
        query_for_retrieval = query
        if language != "en":
            query_for_retrieval = await self.translation_service.translate(
                query, source_lang=language, target_lang="en"
            )

        retrieved_docs = await self.retriever.retrieve(query_for_retrieval)

        if not retrieved_docs:
            no_answer = self._no_answer_response(language)
            yield {"type": "token", "content": no_answer["response"]}
            yield {
                "type": "done",
                "full_response": no_answer["response"],
                "citations": [],
            }
            return

        context = self._build_context(retrieved_docs)
        messages = self._build_messages(query, context, conversation_history)

        # Stream response
        full_response = ""
        try:
            response = await litellm.acompletion(
                model=self.llm_model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )

            async for chunk in response:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_response += token
                    yield {"type": "token", "content": token}

        except Exception as e:
            logger.error("Streaming error", error=str(e))
            yield {"type": "token", "content": "An error occurred while generating the response."}
            yield {"type": "done", "full_response": "", "citations": []}
            return

        # Extract and send citations
        citations = self.grounding_service.extract_citations(full_response, retrieved_docs)
        yield {
            "type": "citations",
            "content": json.dumps([c.model_dump() for c in citations]),
        }

        # Translate if needed
        final_response = full_response
        if language != "en":
            final_response = await self.translation_service.translate(
                full_response, source_lang="en", target_lang=language
            )

        yield {
            "type": "done",
            "full_response": final_response,
            "citations": [c.model_dump() for c in citations],
        }

    async def search_sources(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search source documents directly."""
        results = await self.retriever.retrieve(query, top_k=top_k)
        return [
            {
                "text": r["text"][:500] + "..." if len(r["text"]) > 500 else r["text"],
                "page": r["page"],
                "section": r["section"],
                "score": r["score"],
            }
            for r in results
        ]

    def _build_context(self, documents: List[Dict]) -> str:
        """Build context string from retrieved documents."""
        context_parts = []

        for doc in documents:
            page = doc.get("page", "?")
            section = doc.get("section", "General")
            text = doc.get("text", "")

            context_parts.append(
                f"[Source: Page {page}, Section: {section}]\n{text}"
            )

        return "\n\n---\n\n".join(context_parts)

    def _build_messages(
        self,
        query: str,
        context: str,
        conversation_history: List[Dict] | None,
    ) -> List[Dict]:
        """Build messages for LLM."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add conversation history (limited)
        if conversation_history:
            for msg in conversation_history[-6:]:  # Last 3 exchanges
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        # Add current query with context
        user_message = f"""Based on the following context from the tomato cultivation manual, please answer the question.

CONTEXT:
{context}

QUESTION: {query}

Remember:
- Only use information from the context above
- Include citations [Source: Page X, Section Y] for your claims
- If the information is not in the context, say so"""

        messages.append({"role": "user", "content": user_message})

        return messages

    async def _generate_response(
        self,
        query: str,
        context: str,
        conversation_history: List[Dict] | None,
    ) -> str:
        """Generate LLM response."""
        messages = self._build_messages(query, context, conversation_history)

        try:
            response = await litellm.acompletion(
                model=self.llm_model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error("LLM generation error", error=str(e))
            raise

    def _no_answer_response(self, language: str) -> Dict[str, Any]:
        """Return response when no relevant information is found."""
        messages = {
            "en": "This information is not available in the cultivation manual. I can only answer questions based on the manual's content. Could you please ask a question about tomato cultivation that might be covered in the manual?",
            "ne": "यो जानकारी खेती पुस्तिकामा उपलब्ध छैन। म केवल पुस्तिकाको सामग्रीमा आधारित प्रश्नहरूको जवाफ दिन सक्छु। कृपया टमाटर खेतीको बारेमा प्रश्न सोध्नुहोस्।",
            "ja": "この情報は栽培マニュアルには記載されていません。マニュアルの内容に基づいた質問のみお答えできます。トマト栽培に関する質問をお願いします。",
        }

        return {
            "response": messages.get(language, messages["en"]),
            "citations": [],
            "has_answer": False,
            "confidence": 0.0,
        }


# Singleton instance
_rag_engine: RAGEngine | None = None


async def get_rag_engine() -> RAGEngine:
    """Get RAG engine instance."""
    global _rag_engine
    if _rag_engine is None:
        retriever = await get_retriever()
        grounding_service = await get_grounding_service()
        translation_service = await get_translation_service()
        _rag_engine = RAGEngine(retriever, grounding_service, translation_service)
    return _rag_engine
