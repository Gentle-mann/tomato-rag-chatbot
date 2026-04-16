"""Chat API endpoints for the RAG chatbot."""

from typing import AsyncGenerator
import uuid

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import structlog

from app.config import settings
from app.services.rag_engine import RAGEngine, get_rag_engine
from app.core.redis import (
    get_conversation_history,
    add_to_conversation,
    clear_conversation,
)

logger = structlog.get_logger()
router = APIRouter()


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(default=None)
    language: str = Field(default="en", pattern="^(en|ne|ja)$")
    stream: bool = Field(default=False)


class Citation(BaseModel):
    """Citation model for source attribution."""

    source: str
    page: int
    section: str
    text_excerpt: str
    relevance_score: float


class ChatResponse(BaseModel):
    """Chat response model."""

    message: str
    session_id: str
    language: str
    citations: list[Citation]
    has_answer: bool = True
    confidence: float = Field(ge=0.0, le=1.0)


class ConversationMessage(BaseModel):
    """Conversation message model."""

    role: str
    content: str
    citations: list[Citation] | None = None


class ConversationHistoryResponse(BaseModel):
    """Conversation history response."""

    session_id: str
    messages: list[ConversationMessage]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Process a chat message and return a response with citations.

    The chatbot will ONLY answer based on the tomato cultivation PDF content.
    If the information is not in the PDF, it will respond with
    "This information is not in the cultivation manual."
    """
    session_id = request.session_id or str(uuid.uuid4())

    try:
        # Get conversation history for context
        history = await get_conversation_history(session_id)

        # Process query through RAG engine
        result = await rag_engine.query(
            query=request.message,
            language=request.language,
            conversation_history=history,
        )

        # Store user message in history
        await add_to_conversation(
            session_id=session_id,
            role="user",
            content=request.message,
        )

        # Store assistant response in history
        await add_to_conversation(
            session_id=session_id,
            role="assistant",
            content=result["response"],
            citations=[c.model_dump() for c in result["citations"]],
        )

        return ChatResponse(
            message=result["response"],
            session_id=session_id,
            language=request.language,
            citations=result["citations"],
            has_answer=result["has_answer"],
            confidence=result["confidence"],
        )

    except Exception as e:
        logger.error("Chat error", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail="Failed to process chat message")


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Stream a chat response with Server-Sent Events.

    Returns tokens as they are generated, followed by citations at the end.
    """
    session_id = request.session_id or str(uuid.uuid4())

    async def generate() -> AsyncGenerator[str, None]:
        try:
            history = await get_conversation_history(session_id)

            async for chunk in rag_engine.query_stream(
                query=request.message,
                language=request.language,
                conversation_history=history,
            ):
                if chunk["type"] == "token":
                    yield f"data: {chunk['content']}\n\n"
                elif chunk["type"] == "citations":
                    yield f"data: [CITATIONS]{chunk['content']}\n\n"
                elif chunk["type"] == "done":
                    # Store in history
                    await add_to_conversation(
                        session_id=session_id,
                        role="user",
                        content=request.message,
                    )
                    await add_to_conversation(
                        session_id=session_id,
                        role="assistant",
                        content=chunk["full_response"],
                        citations=chunk.get("citations", []),
                    )
                    yield f"data: [DONE]{session_id}\n\n"

        except Exception as e:
            logger.error("Stream error", error=str(e))
            yield f"data: [ERROR]{str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/chat/history/{session_id}", response_model=ConversationHistoryResponse)
async def get_history(session_id: str):
    """Get conversation history for a session."""
    history = await get_conversation_history(session_id)
    messages = [
        ConversationMessage(
            role=msg["role"],
            content=msg["content"],
            citations=msg.get("citations"),
        )
        for msg in history
    ]
    return ConversationHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/chat/history/{session_id}")
async def delete_history(session_id: str):
    """Clear conversation history for a session."""
    await clear_conversation(session_id)
    return {"status": "cleared", "session_id": session_id}


@router.get("/sources/search")
async def search_sources(
    query: str,
    top_k: int = 5,
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Search source documents directly without generating a response.

    Useful for exploring what information is available in the cultivation manual.
    """
    try:
        results = await rag_engine.search_sources(query=query, top_k=top_k)
        return {"query": query, "results": results}
    except Exception as e:
        logger.error("Source search error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to search sources")
