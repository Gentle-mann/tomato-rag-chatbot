"""Full RAG FastAPI application with all services."""

import hashlib
import os
from contextlib import asynccontextmanager
from typing import List, Optional
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import structlog
import litellm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from FlagEmbedding import BGEM3FlagModel
from sentence_transformers import CrossEncoder
from qdrant_client import QdrantClient
from qdrant_client.models import Prefetch, FusionQuery, Fusion, SparseVector, Filter, FieldCondition, MatchAny, MatchValue
import redis

from app.config import settings

logger = structlog.get_logger()

# Global clients
embedding_model: BGEM3FlagModel = None
reranker_model: CrossEncoder = None
qdrant_client: QdrantClient = None
redis_client: redis.Redis = None

COLLECTION_NAME = "tomato_cultivation"

# Agricultural glossary: Japanese terms → correct English terminology
# Included in the system prompt so the LLM uses accurate domain terms
AGRICULTURAL_GLOSSARY = """
## Agricultural Terminology Reference
Use these correct English terms when translating Japanese source material:
- 整枝 (せいし) → training / vine training
- 芽かき (めかき) → de-suckering / sucker removal
- 剪定 (せんてい) → pruning
- 摘芯 (てきしん) → topping / pinching out
- 摘果 (てきか) → fruit thinning
- 脇芽 (わきめ) → side shoot / lateral shoot / sucker
- 花房 (かぼう) → flower truss / flower cluster
- 尻腐れ (しりくされ) → blossom-end rot (BER)
- 青枯病 (あおがれびょう) → bacterial wilt
- 疫病 (えきびょう) → late blight
- 灰色かび病 → gray mold (Botrytis)
- うどんこ病 → powdery mildew
- 萎凋病 (いちょうびょう) → Fusarium wilt
- 追肥 (ついひ) → side-dressing / top-dressing
- 元肥 (もとごえ) → basal fertilizer / base dressing
- 定植 (ていしょく) → transplanting
- 育苗 (いくびょう) → seedling raising / nursery stage
- 灌水 (かんすい) → irrigation
- 畝 (うね) → raised bed / ridge
- 誘引 (ゆういん) → trellising / training (tying to support)
- マルチ → mulch / mulching
- 連作障害 → continuous cropping disorder / replant disease
- 接木 (つぎき) → grafting
- 裂果 (れっか) → fruit cracking
- 着果 (ちゃっか) → fruit set
- コナジラミ → whitefly (NOT aphid)
- アブラムシ → aphid (NOT whitefly)
- アザミウマ → thrips
- ハダニ → spider mite
- ハモグリバエ → leaf miner
- オオタバコガ → tobacco cutworm
- トマトサビダニ → tomato russet mite
- トマトキバガ → tomato leaf miner moth
- 葉かび病 → leaf mold
- 菌核病 → sclerotinia / white mold
"""

# System prompt for grounded responses
SYSTEM_PROMPT = """You are a helpful agricultural assistant specializing in tomato cultivation.
You MUST follow these rules strictly:

1. ONLY answer using the provided context (from cultivation manuals and video transcript).
2. NEVER use your training knowledge for tomato cultivation facts.
3. If the context doesn't contain the answer, simply say: "This information is not available in the reference materials." Do NOT list or cite sources that lack the answer — only mention a source when it actually supports a claim.
4. Cite EVERY factual claim using the EXACT source label shown in the context (they are already in the user's language). Copy the [Source: ...] / [出典: ...] labels verbatim — do NOT translate them.
5. When multiple sources cover the same topic, combine them into one coherent answer and cite each source where used.
6. ALWAYS respond in the SAME language the user writes their question in. Match the user's language (English, Japanese, Nepali, Indonesian, or Vietnamese).
7. Translate any Japanese source text into the response language when needed. Do NOT include raw Japanese in a non-Japanese response.
8. Format responses using markdown for readability:
   - Use **bold** for key terms, values, and important numbers
   - Use numbered lists (1. 2. 3.) for step-by-step procedures
   - Use bullet lists (- item) for options, symptoms, or conditions
   - Use ### headings to separate distinct topics in multi-part answers
   - Use markdown tables when comparing data (e.g. temperature ranges, fertilizer amounts)
   - Keep paragraphs concise (2-3 sentences max)
9. Match response length to question complexity:
   - Simple factual questions: 1-3 sentences
   - How-to questions: structured numbered list
   - Complex/multi-part questions: use headings to organize sections
10. Do NOT add summary tags like "Synthesized from multiple sources" — just cite each claim individually.
11. ONLY answer the current question. Do NOT reference or repeat information from earlier conversation turns unless directly relevant.
12. When Japanese source material uses distinct technical terms (e.g., 摘芯 vs 摘葉 vs 芽かき), ALWAYS preserve each as a separate concept with its correct English equivalent from the glossary. NEVER merge distinct operations under a single generic term like "pruning." Each operation has a different purpose and technique.
13. Answer ONLY what the user asked. If the question is about a specific operation (e.g., "how to remove side shoots"), focus your answer on THAT operation. Do NOT pad the response with unrelated operations from the context. Only include other operations if the user explicitly asks a broad question.
14. Answer from the retrieved context without commenting on which region is selected. Do not suggest that the user switch regions or mention the region selector in your answer — users control that themselves. Simply provide the best answer from the sources available.
""" + AGRICULTURAL_GLOSSARY


@retry(
    retry=retry_if_exception_type(litellm.RateLimitError),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
    before_sleep=lambda rs: logger.info("Rate limited, retrying", attempt=rs.attempt_number),
)
async def llm_completion(**kwargs):
    """Call litellm.acompletion with automatic retry on rate limit errors."""
    return await litellm.acompletion(**kwargs)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global embedding_model, reranker_model, qdrant_client, redis_client

    logger.info("Starting Tomato RAG Chatbot (Full Mode)")

    # Initialize embedding model (BGE-M3 with dense + sparse support)
    logger.info("Loading embedding model...")
    embedding_model = BGEM3FlagModel(settings.embedding_model, use_fp16=False)
    logger.info("Embedding model loaded (dense + sparse)")

    # Initialize reranker model
    logger.info("Loading reranker model...")
    reranker_model = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
    logger.info("Reranker model loaded")

    # Initialize Qdrant
    logger.info("Connecting to Qdrant...")
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    logger.info("Qdrant connected")

    # Initialize Redis
    logger.info("Connecting to Redis...")
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    redis_client.ping()
    logger.info("Redis connected")

    # Set Anthropic API key for litellm
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    # Initialize database (for document management + feedback)
    try:
        from app.core.database import init_db
        from app.models.feedback import Feedback  # noqa: F401 — ensure table created
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database initialization failed (document management will be unavailable)", error=str(e))

    yield

    logger.info("Shutting down Tomato RAG Chatbot")


app = FastAPI(
    title="Tomato RAG Chatbot",
    version="1.0.0",
    description="Multilingual RAG Chatbot for Tomato Cultivation with Citations",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount document management router
from app.api.v1.endpoints.documents import router as documents_router
app.include_router(documents_router, prefix="/api/v1", tags=["documents"])

# Mount feedback router
from app.api.v1.endpoints.feedback import router as feedback_router
app.include_router(feedback_router, prefix="/api/v1", tags=["feedback"])


# Request/Response Models
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    language: str = Field(default="en", pattern="^(en|ne|ja|id|vi)$")
    region: Optional[str] = Field(default=None, pattern="^(global|japan|nepal|vietnam|indonesia|philippines)$")


class Citation(BaseModel):
    source_type: str = ""           # "manual" | "transcript"
    source_name: str = ""           # filename
    page: Optional[int] = None      # PDF page (None for transcript)
    timestamp: Optional[str] = None # "MM:SS" (None for manual)
    section: str
    text_excerpt: str
    relevance_score: float


class ChatResponse(BaseModel):
    response: str
    citations: List[Citation]
    session_id: str
    has_answer: bool = True
    suggestions: List[str] = Field(default_factory=list)


# Helper functions
def _is_japanese(text: str) -> bool:
    """Check if text is primarily Japanese (contains CJK/hiragana/katakana)."""
    japanese_chars = sum(
        1 for c in text
        if ('\u3040' <= c <= '\u309f')    # Hiragana
        or ('\u30a0' <= c <= '\u30ff')    # Katakana
        or ('\u4e00' <= c <= '\u9fff')    # CJK Unified Ideographs
    )
    return japanese_chars > len(text) * 0.1


async def translate_query_to_japanese(query: str) -> str:
    """Translate a non-Japanese query to Japanese for better retrieval.

    The reference manual is in Japanese, so translating the query improves
    both dense and sparse vector matching against the source content.
    """
    if _is_japanese(query):
        return query

    try:
        response = await llm_completion(
            model=settings.llm_model,
            messages=[{
                "role": "system",
                "content": (
                    "You are an agricultural translation specialist. "
                    "Translate queries to Japanese using the exact technical terms "
                    "found in Japanese tomato cultivation manuals.\n\n"
                    "CRITICAL RULE: When a query uses a BROAD term that covers multiple "
                    "distinct operations, EXPAND the translation to include ALL specific "
                    "Japanese terms IN A NATURAL SENTENCE. Do NOT just list terms — "
                    "form a proper Japanese question. Examples:\n"
                    "- 'How do I prune tomatoes?' (broad) → "
                    "トマトの整枝・摘芯・摘葉・芽かきの方法は？\n"
                    "- 'Tell me about fertilizing' (broad) → "
                    "トマトの元肥と追肥について教えてください\n\n"
                    "Key term mappings:\n"
                    "- pruning/training (broad) → 整枝, 剪定, 摘芯, 摘葉, 芽かき\n"
                    "- leaf pruning/leaf removal/defoliation → 摘葉, 葉かき\n"
                    "- de-suckering/sucker removal → 芽かき\n"
                    "- fruit thinning → 摘果\n"
                    "- topping/pinching → 摘芯\n"
                    "- blossom-end rot → 尻腐れ\n"
                    "- bacterial wilt → 青枯病\n"
                    "- late blight → 疫病\n"
                    "- gray mold → 灰色かび病\n"
                    "- powdery mildew → うどんこ病\n"
                    "- Fusarium wilt → 萎凋病\n"
                    "- side-dressing/top-dressing → 追肥\n"
                    "- basal fertilizer → 元肥\n"
                    "- transplanting → 定植\n"
                    "- seedling raising → 育苗\n"
                    "- fruit cracking → 裂果\n"
                    "- fruit set → 着果\n"
                    "- grafting → 接木\n"
                    "- trellising → 誘引\n"
                    "- mulching → マルチ\n"
                    "- flower truss → 花房\n"
                    "\nPest/disease name mappings (use exact Japanese terms):\n"
                    "- whitefly/whiteflies → コナジラミ\n"
                    "- aphid/aphids → アブラムシ\n"
                    "- thrips → アザミウマ\n"
                    "- spider mite → ハダニ\n"
                    "- leaf miner → ハモグリバエ\n"
                    "- caterpillar/armyworm → ヨトウムシ\n"
                    "- tobacco cutworm → オオタバコガ\n"
                    "- tomato russet mite → トマトサビダニ\n"
                    "- tomato leaf miner moth → トマトキバガ\n"
                    "- nematode → ネコブセンチュウ\n"
                    "- leaf mold → 葉かび病\n"
                    "- sclerotinia/white mold → 菌核病\n"
                    "- leaf spot → 斑点病\n"
                    "Return ONLY the Japanese translation, nothing else."
                ),
            }, {
                "role": "user",
                "content": f"Translate this tomato cultivation query to Japanese:\n{query}",
            }],
            temperature=0.0,
            max_tokens=256,
        )
        translated = response.choices[0].message.content.strip()
        logger.info("Query translated", original=query, translated=translated)
        return translated
    except Exception as e:
        logger.warning("Query translation failed, using original", error=str(e))
        return query


def encode_query(query: str):
    """Encode query into dense and sparse vectors using BGE-M3."""
    output = embedding_model.encode([query], return_dense=True, return_sparse=True)
    dense = output["dense_vecs"][0]
    sparse_w = output["lexical_weights"][0]
    sparse_indices = [int(k) for k in sparse_w.keys()]
    sparse_values = [float(v) for v in sparse_w.values()]
    return dense, SparseVector(indices=sparse_indices, values=sparse_values)


# Keywords that indicate the query is about pests, diseases, or agricultural chemicals.
# When these are NOT present, we exclude the "Pesticides" section from search
# to prevent the large chemical database from crowding out cultivation knowledge.
CHEMICAL_QUERY_KEYWORDS = [
    # Japanese
    "害虫", "病気", "病害", "農薬", "殺虫", "殺菌", "除草", "薬剤", "防除",
    "雑草", "カビ", "かび", "ウイルス", "ダニ", "アブラムシ", "コナジラミ",
    "アザミウマ", "疫病", "灰色", "うどんこ", "萎凋", "青枯", "斑点",
    "ﾀﾞﾆ", "ｱﾌﾞﾗﾑｼ", "ｺﾅｼﾞﾗﾐ", "ｱｻﾞﾐｳﾏ", "着果", "成長調整",
    # English
    "pest", "disease", "fungus", "fungi", "fungicid", "insecticid", "herbicid",
    "pesticide", "spray", "chemical", "mold", "mould", "blight", "wilt",
    "aphid", "whitefl", "mite", "thrip", "caterpillar", "weed",
    "rot", "virus", "bacteri",
    # Nepali
    "कीट", "रोग", "कीटनाशक", "ढुसी", "विषाणु",
    # Vietnamese
    "sâu", "bệnh", "thuốc trừ", "nấm",
]


def _is_chemical_query(query: str) -> bool:
    """Detect if a query is about pests, diseases, or agricultural chemicals."""
    q_lower = query.lower()
    return any(kw.lower() in q_lower for kw in CHEMICAL_QUERY_KEYWORDS)


def search_documents(query: str, top_k: int = 5, region: Optional[str] = None, original_query: Optional[str] = None) -> List[dict]:
    """Hybrid search: dense + sparse with RRF fusion.

    When a region is specified, uses two-pool retrieval:
    - Pool 1 (filtered): dense+sparse limited to [region, "global"]
    - Pool 2 (unfiltered): dense+sparse for broader coverage
    RRF fusion merges both pools, giving region-specific content a boost
    (it appears in both pools → higher fused score).

    Excludes the Pesticides section unless the query is about pests/diseases/chemicals.
    This prevents the large chemical database from crowding out cultivation knowledge.

    Cross-lingual pool: when the query was translated (original_query differs from query),
    also encodes the original query and adds its dense vector as an extra prefetch pool.
    BGE-M3's multilingual dense space handles cross-lingual matching well; sparse vectors
    are language-specific (Japanese tokens ≠ Nepali/Indonesian tokens), so this dense-only
    pool is essential for retrieving non-Japanese regional sources.
    """
    dense_vec, sparse_vec = encode_query(query)

    # Encode original (untranslated) query for cross-lingual dense matching.
    # Sparse search is skipped for the original query because lexical token overlap
    # across languages is near-zero and adds noise rather than signal.
    orig_dense_vec = None
    if original_query and original_query.strip().lower() != query.strip().lower():
        orig_output = embedding_model.encode(
            [original_query], return_dense=True, return_sparse=False
        )
        orig_dense_vec = orig_output["dense_vecs"][0]

    # Check both translated and original query for chemical keywords
    is_chemical = _is_chemical_query(query)
    if not is_chemical and original_query:
        is_chemical = _is_chemical_query(original_query)

    # Build filter conditions
    filter_conditions = []

    # Region filter
    if region and region != "global":
        filter_conditions.append(
            FieldCondition(key="region", match=MatchAny(any=[region, "global"]))
        )

    # Exclude pesticide section for non-chemical queries
    exclude_conditions = []
    if not is_chemical:
        exclude_conditions.append(
            FieldCondition(key="section", match=MatchValue(value="Pesticides"))
        )

    # Build combined filter
    combined_filter = None
    if filter_conditions or exclude_conditions:
        combined_filter = Filter(
            must=filter_conditions if filter_conditions else None,
            must_not=exclude_conditions if exclude_conditions else None,
        )

    # Build Pool 2 filter: for non-chemical queries exclude pesticides;
    # for chemical queries WITH a region, also enforce region (pesticide
    # availability is strictly region-dependent — Japan-approved pesticides
    # should not surface for Nepal users).
    pool2_filter = None
    if not is_chemical:
        pool2_filter = Filter(
            must_not=[FieldCondition(key="section", match=MatchValue(value="Pesticides"))]
        )
    elif is_chemical and region and region != "global":
        # Chemical query with region: Pool 2 also enforces region
        pool2_filter = Filter(
            must=[FieldCondition(key="region", match=MatchAny(any=[region, "global"]))]
        )

    if combined_filter:
        prefetch = [
            # Pool 1: Region + pesticide filtered (translated query)
            Prefetch(query=dense_vec.tolist(), using="dense", limit=20, filter=combined_filter),
            Prefetch(query=sparse_vec, using="sparse", limit=20, filter=combined_filter),
            # Pool 2: Broader filter (translated query)
            Prefetch(query=dense_vec.tolist(), using="dense", limit=10, filter=pool2_filter),
            Prefetch(query=sparse_vec, using="sparse", limit=10, filter=pool2_filter),
        ]
        # Pool 3: Cross-lingual dense pool using original query (for non-Japanese sources)
        if orig_dense_vec is not None:
            prefetch.append(
                Prefetch(query=orig_dense_vec.tolist(), using="dense", limit=15, filter=combined_filter)
            )
    elif pool2_filter:
        prefetch = [
            Prefetch(query=dense_vec.tolist(), using="dense", limit=20, filter=pool2_filter),
            Prefetch(query=sparse_vec, using="sparse", limit=20, filter=pool2_filter),
        ]
        if orig_dense_vec is not None:
            prefetch.append(
                Prefetch(query=orig_dense_vec.tolist(), using="dense", limit=15, filter=pool2_filter)
            )
    else:
        prefetch = [
            Prefetch(query=dense_vec.tolist(), using="dense", limit=20),
            Prefetch(query=sparse_vec, using="sparse", limit=20),
        ]
        if orig_dense_vec is not None:
            prefetch.append(
                Prefetch(query=orig_dense_vec.tolist(), using="dense", limit=15)
            )

    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=prefetch,
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            "text": r.payload.get("text", ""),
            "page": r.payload.get("page", 0),
            "section": r.payload.get("section", "General"),
            "source_type": r.payload.get("source_type", "manual"),
            "source_name": r.payload.get("source_name", ""),
            "timestamp": r.payload.get("timestamp"),
            "region": r.payload.get("region", "global"),
            "sub_section": r.payload.get("sub_section"),
            "score": r.score,
        }
        for r in results.points
    ]


# Query keywords that indicate a specific sub-section topic.
# Used to boost chunks tagged with the matching sub_section during reranking.
QUERY_SUB_SECTION_HINTS = [
    (["摘芯", "摘心", "topping", "pinch"], "topping"),
    (["摘葉", "葉かき", "leaf remov", "leaf prun", "defoliat"], "leaf_removal"),
    (["芽かき", "脇芽", "わき芽", "side shoot", "sucker", "de-sucker"], "de_suckering"),
    (["摘果", "fruit thin"], "fruit_thinning"),
    (["整枝", "仕立て", "training", "single stem", "vine shap"], "training"),
]


def _detect_query_sub_section(query: str) -> Optional[str]:
    """Detect which sub-section the query is asking about, if any."""
    q_lower = query.lower()
    for keywords, sub in QUERY_SUB_SECTION_HINTS:
        for kw in keywords:
            if kw.lower() in q_lower:
                return sub
    return None


def rerank_documents(query: str, documents: List[dict], top_k: int = 5, region: Optional[str] = None) -> List[dict]:
    """Rerank documents using a cross-encoder model with source diversity.

    Ensures both source types (manual/transcript) are represented in results
    when both have relevant matches. Guarantees at least min_per_source slots
    for the minority source, filling remaining slots by score.

    Applies a sub-section relevance boost: chunks whose sub_section matches
    the query topic get a score bonus. This helps when OCR-garbled chunks
    contain the right content but score poorly on text similarity.

    Applies a region-match boost: when a specific region is requested, chunks
    whose region exactly matches get a score bonus over global-tagged chunks.
    This prevents the Japanese manual (region=global) from crowding out
    region-specific sources (e.g. Nepal DoA book for region=nepal).
    """
    if not documents:
        return documents

    pairs = [(query, doc["text"]) for doc in documents]
    scores = reranker_model.predict(pairs)

    # Detect if query targets a specific sub-section
    target_sub = _detect_query_sub_section(query)

    for doc, score in zip(documents, scores):
        doc["rerank_score"] = float(score)
        # Boost chunks that match the query's target sub-section
        if target_sub and doc.get("sub_section") == target_sub:
            doc["rerank_score"] += 0.5
        # Boost chunks whose region exactly matches the requested region.
        # This ensures Nepal/Indonesia/etc. sources rank above global (Japanese)
        # sources when the user has explicitly selected a region.
        if region and region != "global" and doc.get("region") == region:
            doc["rerank_score"] += 0.4

    documents.sort(key=lambda x: x["rerank_score"], reverse=True)

    # Split by source type
    manual_docs = [d for d in documents if d.get("source_type") != "transcript"]
    transcript_docs = [d for d in documents if d.get("source_type") == "transcript"]

    # If only one source exists, return top_k by score
    if not manual_docs or not transcript_docs:
        return documents[:top_k]

    # Ensure at least 2 from each source, fill remaining by score
    min_per_source = 2
    selected = []
    selected.extend(manual_docs[:min_per_source])
    selected.extend(transcript_docs[:min_per_source])
    selected_ids = {id(d) for d in selected}

    # Fill remaining slots from all docs by score
    remaining = top_k - len(selected)
    for doc in documents:
        if remaining <= 0:
            break
        if id(doc) not in selected_ids:
            selected.append(doc)
            remaining -= 1

    selected.sort(key=lambda x: x["rerank_score"], reverse=True)
    return selected


SUB_SECTION_DISPLAY = {
    "topping": "topping (摘芯)",
    "leaf_removal": "leaf removal (摘葉)",
    "de_suckering": "de-suckering (芽かき)",
    "fruit_thinning": "fruit thinning (摘果)",
    "training": "training / vine shaping (整枝)",
}


def detect_sub_operations(documents: List[dict]) -> List[str]:
    """Detect distinct agricultural sub-operations in retrieved chunks.

    Uses the sub_section payload field when available (set at ingestion),
    with text-based fallback for chunks that predate the sub_section field.
    """
    found = set()
    combined = " ".join(doc["text"] for doc in documents)

    # Primary: payload-based detection
    for doc in documents:
        sub = doc.get("sub_section")
        if sub:
            found.add(sub)

    # Fallback: text-based detection for chunks without sub_section
    if "摘芯" in combined or "摘心" in combined:
        found.add("topping")
    if "摘葉" in combined or "葉かき" in combined:
        found.add("leaf_removal")
    if "芽かき" in combined or "脇芽" in combined or "わき芽" in combined:
        found.add("de_suckering")
    if "摘果" in combined:
        found.add("fruit_thinning")

    return [SUB_SECTION_DISPLAY[s] for s in found if s in SUB_SECTION_DISPLAY]


# Follow-up suggestion templates per sub-operation, per language
FOLLOW_UP_TEMPLATES = {
    "en": {
        "topping": "How and when should I top my tomato plants?",
        "leaf_removal": "Which leaves should I remove and when?",
        "de_suckering": "How do I remove side shoots (suckers)?",
        "fruit_thinning": "When and how should I thin tomato fruits?",
        "training": "How do I train tomatoes to a single stem?",
    },
    "ja": {
        "topping": "摘芯はいつ、どのように行いますか？",
        "leaf_removal": "摘葉はどの葉を取りますか？",
        "de_suckering": "脇芽かきの方法を教えてください",
        "fruit_thinning": "摘果のタイミングと方法は？",
        "training": "一本仕立ての整枝方法を教えてください",
    },
    "ne": {
        "topping": "टमाटरको टुप्पो कसरी र कहिले काट्ने?",
        "leaf_removal": "कुन पात हटाउनुपर्छ?",
        "de_suckering": "छेउका गोली कसरी हटाउने?",
        "fruit_thinning": "फल पातलो कहिले र कसरी गर्ने?",
        "training": "एकल डाँठमा कसरी तालिम दिने?",
    },
    "vi": {
        "topping": "Khi nào và cách bấm ngọn cà chua?",
        "leaf_removal": "Nên cắt tỉa lá nào và khi nào?",
        "de_suckering": "Cách loại bỏ chồi bên?",
        "fruit_thinning": "Khi nào và cách tỉa quả cà chua?",
        "training": "Cách uốn cà chua thành một thân?",
    },
    "id": {
        "topping": "Kapan dan bagaimana cara memotong pucuk tomat?",
        "leaf_removal": "Daun mana yang harus dipangkas?",
        "de_suckering": "Bagaimana cara membuang tunas samping?",
        "fruit_thinning": "Kapan dan bagaimana cara menipiskan buah tomat?",
        "training": "Bagaimana cara melatih tomat menjadi satu batang?",
    },
}


def generate_suggestions(sub_ops_found: List[str], language: str) -> List[str]:
    """Generate follow-up question suggestions based on detected sub-operations.

    Only generates suggestions when 2+ sub-operations are detected (broad query).
    Returns up to 3 suggestions for operations covered in the response.
    """
    if len(sub_ops_found) < 2:
        return []

    templates = FOLLOW_UP_TEMPLATES.get(language, FOLLOW_UP_TEMPLATES["en"])

    # Map display names back to keys
    display_to_key = {v: k for k, v in SUB_SECTION_DISPLAY.items()}

    suggestions = []
    for op_display in sub_ops_found:
        key = display_to_key.get(op_display)
        if key and key in templates:
            suggestions.append(templates[key])

    return suggestions[:3]


def _display_source_name(source_name: str) -> str:
    """Format source filename for display (strip .pdf, truncate)."""
    name = source_name
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    if len(name) > 40:
        name = name[:37] + "..."
    return name


LANGUAGE_NAMES = {
    "en": "English",
    "ja": "Japanese",
    "ne": "Nepali",
    "id": "Indonesian",
    "vi": "Vietnamese",
}

LANGUAGE_TO_REGION = {
    "ja": "japan",
    "ne": "nepal",
    "vi": "vietnam",
    "id": "indonesia",
    "en": None,  # English is global — no default region
}

REGION_DISPLAY_NAMES = {
    "japan": "Japan",
    "nepal": "Nepal",
    "vietnam": "Vietnam",
    "indonesia": "Indonesia",
    "philippines": "Philippines",
}


def detect_query_language(text: str, fallback: str = "en") -> str:
    """Detect query language from character scripts. Falls back to selector language.

    Only overrides the fallback when the dominant non-Latin script accounts for
    more than 30% of meaningful characters. This prevents a few embedded Japanese
    terms in an English sentence (e.g., "What is 摘芯?") from flipping the
    detected language.
    """
    import unicodedata
    counts = {"ja": 0, "ne": 0}
    total_alpha = 0
    for ch in text:
        if ch.isspace() or ch in '.,;:!?()[]{}"\'-/':
            continue
        total_alpha += 1
        try:
            name = unicodedata.name(ch, "")
        except ValueError:
            continue
        if "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name:
            counts["ja"] += 1
        elif "DEVANAGARI" in name:
            counts["ne"] += 1
    # Vietnamese uses Latin + diacritics, hard to distinguish from English by script
    # so we only auto-detect Japanese and Nepali; otherwise use fallback
    if total_alpha == 0:
        return fallback
    dominant = max(counts, key=counts.get)
    ratio = counts[dominant] / total_alpha
    if counts[dominant] >= 2 and ratio > 0.3:
        return dominant
    return fallback

# Localized citation labels per language
CITATION_LABELS = {
    "en": {"source": "Source", "page": "Page", "section": "Section", "video": "Video Transcript"},
    "ja": {"source": "出典", "page": "ページ", "section": "セクション", "video": "動画トランスクリプト"},
    "ne": {"source": "स्रोत", "page": "पृष्ठ", "section": "खण्ड", "video": "भिडियो ट्रान्सक्रिप्ट"},
    "id": {"source": "Sumber", "page": "Halaman", "section": "Bagian", "video": "Transkrip Video"},
    "vi": {"source": "Nguồn", "page": "Trang", "section": "Phần", "video": "Bản ghi video"},
}

# Section name translations (English keys stored in Qdrant → localized display names)
SECTION_TRANSLATIONS = {
    "ja": {
        "Varieties": "品種",
        "Pruning": "剪定・整枝",
        "Seedling Care": "育苗",
        "Seeding": "播種",
        "Transplanting": "定植",
        "Fertilization": "施肥",
        "Irrigation": "灌水",
        "Disease Management": "病害管理",
        "Pest Control": "害虫防除",
        "Harvesting": "収穫",
        "Temperature": "温度管理",
        "General": "全般",
        "Fruit Cracking": "裂果",
        "Photosynthesis": "光合成",
        "Fruiting": "着果",
        "Growth": "生育",
    },
    "ne": {
        "Varieties": "जातहरू",
        "Pruning": "काँटछाँट",
        "Seedling Care": "बिरुवा हेरचाह",
        "Seeding": "बीउ रोप्ने",
        "Transplanting": "रोपाइँ",
        "Fertilization": "मल दिने",
        "Irrigation": "सिंचाइ",
        "Disease Management": "रोग व्यवस्थापन",
        "Pest Control": "कीट नियन्त्रण",
        "Harvesting": "कटनी",
        "Temperature": "तापक्रम",
        "General": "सामान्य",
    },
}


def _translate_section(section: str, language: str) -> str:
    """Translate an English section name to the target language."""
    if language == "en" or language not in SECTION_TRANSLATIONS:
        return section
    return SECTION_TRANSLATIONS[language].get(section, section)


def build_context(documents: List[dict], language: str = "en") -> str:
    """Build context string from retrieved documents with localized labels."""
    labels = CITATION_LABELS.get(language, CITATION_LABELS["en"])
    context_parts = []
    for doc in documents:
        section = _translate_section(doc["section"], language)
        if doc.get("source_type") == "transcript":
            ts = doc.get("timestamp", "0:00")
            header = f"[{labels['source']}: {labels['video']}, ~{ts}, {labels['section']}: {section}]"
        else:
            name = _display_source_name(doc.get("source_name", "Manual"))
            header = f"[{labels['source']}: {name}, {labels['page']} {doc['page']}, {labels['section']}: {section}]"
        context_parts.append(f"{header}\n{doc['text']}")
    return "\n\n---\n\n".join(context_parts)


def get_conversation_history(session_id: str) -> List[dict]:
    """Get conversation history from Redis."""
    key = f"conversation:{session_id}"
    history = redis_client.get(key)
    return json.loads(history) if history else []


def save_conversation(session_id: str, messages: List[dict]):
    """Save conversation history to Redis."""
    key = f"conversation:{session_id}"
    # Keep last 20 messages
    redis_client.setex(key, 86400, json.dumps(messages[-20:]))


def extract_citations(documents: List[dict]) -> List[Citation]:
    """Extract citations from retrieved documents."""
    return [
        Citation(
            source_type=doc.get("source_type", "manual"),
            source_name=doc.get("source_name", ""),
            page=doc.get("page") if doc.get("source_type") != "transcript" else None,
            timestamp=doc.get("timestamp") if doc.get("source_type") == "transcript" else None,
            section=doc["section"],
            text_excerpt=doc["text"][:200] + "..." if len(doc["text"]) > 200 else doc["text"],
            relevance_score=round(doc["score"], 3),
        )
        for doc in documents
    ]


CACHE_TTL = 86400  # 24 hours


def get_cache_key(query: str, language: str, region: Optional[str] = None) -> str:
    """Generate a cache key from normalized query + language + region."""
    normalized = query.strip().lower()
    raw = f"{normalized}:{language}:{region or 'none'}"
    return f"cache:{hashlib.sha256(raw.encode()).hexdigest()}"


def get_cached_response(query: str, language: str, region: Optional[str] = None) -> Optional[dict]:
    """Look up a cached chat response in Redis."""
    key = get_cache_key(query, language, region)
    data = redis_client.get(key)
    if data:
        logger.info("Cache hit", query=query[:50], language=language, region=region)
        return json.loads(data)
    return None


def set_cached_response(query: str, language: str, response_data: dict, region: Optional[str] = None):
    """Store a chat response in Redis cache."""
    key = get_cache_key(query, language, region)
    redis_client.setex(key, CACHE_TTL, json.dumps(response_data))
    logger.info("Cached response", query=query[:50], language=language, region=region)


# Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "mode": "full_rag",
        "qdrant": "connected",
        "redis": "connected",
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Tomato RAG Chatbot",
        "version": "1.0.0",
        "mode": "full_rag",
        "docs": "/docs",
    }


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint with RAG and citations.

    The chatbot will ONLY answer based on the tomato cultivation PDF content.
    Every response includes citations to the source material.
    """
    import uuid

    session_id = request.session_id or str(uuid.uuid4())

    # Detect actual query language (overrides selector when user types in a different language)
    detected_lang = detect_query_language(request.message, fallback=request.language)

    # Resolve effective region: explicit request > inferred from language
    effective_region = request.region or LANGUAGE_TO_REGION.get(detected_lang)

    # Check conversation history to determine if this is a fresh question
    history = get_conversation_history(session_id)

    # Check cache for fresh questions (no prior conversation context)
    if not history:
        cached = get_cached_response(request.message, detected_lang, region=effective_region)
        if cached:
            # Save to history so follow-ups work naturally
            history.append({"role": "user", "content": request.message})
            history.append({"role": "assistant", "content": cached["response"]})
            save_conversation(session_id, history)
            return ChatResponse(
                response=cached["response"],
                citations=[Citation(**c) for c in cached["citations"]],
                session_id=session_id,
                has_answer=cached["has_answer"],
            )

    # Translate non-Japanese queries for better retrieval against Japanese source
    retrieval_query = await translate_query_to_japanese(request.message)

    # Search for relevant documents (retrieve 10, rerank to top 5)
    documents = search_documents(retrieval_query, top_k=15, region=effective_region, original_query=request.message)

    if not documents or documents[0]["score"] < 0.15:
        return ChatResponse(
            response="This information is not available in the reference materials. I can only answer questions based on the provided sources. Could you please ask a question about tomato cultivation?",
            citations=[],
            session_id=session_id,
            has_answer=False,
        )

    documents = rerank_documents(retrieval_query, documents, top_k=5, region=effective_region)

    # Fallback: if translation may have hurt retrieval, retry with original query
    if (documents and documents[0].get("rerank_score", 0) < 0.3
            and retrieval_query != request.message):
        logger.info("Low rerank scores after translation, trying original query",
                     top_score=round(documents[0].get("rerank_score", 0), 3))
        fallback_docs = search_documents(request.message, top_k=15, region=effective_region)
        if fallback_docs and fallback_docs[0]["score"] >= 0.15:
            fallback_reranked = rerank_documents(request.message, fallback_docs, top_k=5, region=effective_region)
            if (fallback_reranked
                    and fallback_reranked[0].get("rerank_score", 0) > documents[0].get("rerank_score", 0)):
                documents = fallback_reranked
                logger.info("Using original query results (better rerank scores)")

    # Detect if retrieved chunks cover multiple distinct sub-operations
    sub_ops = detect_sub_operations(documents)
    disambiguation_hint = ""
    if len(sub_ops) >= 2:
        ops_list = ", ".join(sub_ops)
        disambiguation_hint = (
            f"\n- The context covers {len(sub_ops)} distinct operations: {ops_list}. "
            f"Organize your answer with a clear subheading (###) for EACH operation. "
            f"Use the specific technical term for each — never merge them under a generic word like 'pruning'."
        )

    # Add region awareness hint for the LLM
    region_hint = ""
    if effective_region and effective_region != "global":
        display_region = REGION_DISPLAY_NAMES.get(effective_region, effective_region)
        region_hint = (
            f"\n- REGION RULE: The user is farming in {display_region}. "
            f"You MUST prioritize sources tagged for {display_region} over global/Japanese sources. "
            f"Only use Japanese manual content if no {display_region}-specific source covers the topic. "
            f"If you must use Japanese content as a fallback, explicitly state: "
            f"'Note: this is from Japanese reference materials and may not apply directly to {display_region}.'"
        )

    response_lang = detected_lang
    response_lang_name = LANGUAGE_NAMES.get(response_lang, "English")

    # Build context with localized citation labels
    context = build_context(documents, response_lang)

    # Build messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add history (last 3 exchanges)
    for msg in history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current query with context
    user_message = f"""Answer ONLY the question below using the provided context. Do not reference previous conversation topics.

CONTEXT:
{context}

QUESTION: {request.message}

RESPOND IN: {response_lang_name}

Rules:
- Cite every claim using the exact source labels from the CONTEXT above — copy them verbatim, do NOT translate them
- You MUST respond in {response_lang_name} regardless of conversation history or context language
- If the answer is not in the context, say so
- Do not add summary tags like "Synthesized from multiple sources" {disambiguation_hint}{region_hint}"""

    messages.append({"role": "user", "content": user_message})

    # Generate response
    try:
        response = await llm_completion(
            model=settings.llm_model,
            messages=messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        answer = response.choices[0].message.content
    except Exception as e:
        logger.error("LLM error", error=str(e))
        return ChatResponse(
            response=f"Sorry, I encountered an error: {str(e)}",
            citations=[],
            session_id=session_id,
            has_answer=False,
        )

    # Save to history
    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": answer})
    save_conversation(session_id, history)

    # Extract citations
    citations = extract_citations(documents)

    # Generate follow-up suggestions for broad queries
    suggestions = generate_suggestions(sub_ops, response_lang)

    # Cache the response for fresh questions (no prior history)
    if len(history) == 2:  # Only the current Q&A pair
        set_cached_response(request.message, detected_lang, {
            "response": answer,
            "citations": [c.model_dump() for c in citations],
            "has_answer": True,
            "suggestions": suggestions,
        }, region=effective_region)

    return ChatResponse(
        response=answer,
        citations=citations,
        session_id=session_id,
        has_answer=True,
        suggestions=suggestions,
    )


@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream chat response with Server-Sent Events."""
    import uuid

    session_id = request.session_id or str(uuid.uuid4())

    # Detect actual query language
    detected_lang = detect_query_language(request.message, fallback=request.language)

    # Resolve effective region
    effective_region = request.region or LANGUAGE_TO_REGION.get(detected_lang)

    # Check cache for fresh questions
    history = get_conversation_history(session_id)
    cached = None
    if not history:
        cached = get_cached_response(request.message, detected_lang, region=effective_region)

    async def generate():
        nonlocal cached, history

        # Serve from cache if available — simulate streaming for consistent UX
        if cached:
            import asyncio
            text = cached["response"]
            # Stream in word-sized chunks (~3-5 chars) with tiny delays
            chunk_size = 4
            for i in range(0, len(text), chunk_size):
                yield f"data: {json.dumps(text[i:i+chunk_size])}\n\n"
                if i % 20 == 0:  # yield control every ~5 chunks
                    await asyncio.sleep(0.01)
            yield f"data: [CITATIONS]{json.dumps(cached['citations'])}\n\n"
            if cached.get("suggestions"):
                yield f"data: [SUGGESTIONS]{json.dumps(cached['suggestions'])}\n\n"
            # Save to history
            history.append({"role": "user", "content": request.message})
            history.append({"role": "assistant", "content": cached["response"]})
            save_conversation(session_id, history)
            yield f"data: [DONE]{session_id}\n\n"
            return

        # Translate non-Japanese queries for better retrieval
        retrieval_query = await translate_query_to_japanese(request.message)

        # Search for relevant documents (retrieve 10, rerank to top 5)
        documents = search_documents(retrieval_query, top_k=15, region=effective_region, original_query=request.message)

        if not documents or documents[0]["score"] < 0.15:
            yield f"data: This information is not available in the reference materials.\n\n"
            yield f"data: [DONE]{session_id}\n\n"
            return

        documents = rerank_documents(retrieval_query, documents, top_k=5, region=effective_region)

        # Fallback: if translation may have hurt retrieval, retry with original query
        if (documents and documents[0].get("rerank_score", 0) < 0.3
                and retrieval_query != request.message):
            logger.info("Low rerank scores after translation, trying original query",
                         top_score=round(documents[0].get("rerank_score", 0), 3))
            fallback_docs = search_documents(request.message, top_k=15, region=effective_region)
            if fallback_docs and fallback_docs[0]["score"] >= 0.15:
                fallback_reranked = rerank_documents(request.message, fallback_docs, top_k=5, region=effective_region)
                if (fallback_reranked
                        and fallback_reranked[0].get("rerank_score", 0) > documents[0].get("rerank_score", 0)):
                    documents = fallback_reranked
                    logger.info("Using original query results (better rerank scores)")

        # Detect if retrieved chunks cover multiple distinct sub-operations
        sub_ops = detect_sub_operations(documents)
        disambiguation_hint = ""
        if len(sub_ops) >= 2:
            ops_list = ", ".join(sub_ops)
            disambiguation_hint = (
                f"\n- The context covers {len(sub_ops)} distinct operations: {ops_list}. "
                f"Organize your answer with a clear subheading (###) for EACH operation. "
                f"Use the specific technical term for each — never merge them under a generic word like 'pruning'."
            )

        # Add region awareness hint for the LLM
        region_hint = ""
        if effective_region and effective_region != "global":
            display_region = REGION_DISPLAY_NAMES.get(effective_region, effective_region)
            region_hint = (
                f"\n- REGION RULE: The user is farming in {display_region}. "
                f"You MUST prioritize sources tagged for {display_region} over global/Japanese sources. "
                f"Only use Japanese manual content if no {display_region}-specific source covers the topic. "
                f"If you must use Japanese content as a fallback, explicitly state: "
                f"'Note: this is from Japanese reference materials and may not apply directly to {display_region}.'"
            )

        response_lang = detected_lang
        response_lang_name = LANGUAGE_NAMES.get(response_lang, "English")

        context = build_context(documents, response_lang)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        user_message = f"""Answer ONLY the question below using the provided context. Do not reference previous conversation topics.

CONTEXT:
{context}

QUESTION: {request.message}

RESPOND IN: {response_lang_name}

Rules:
- Cite every claim using the exact source labels from the CONTEXT above — copy them verbatim, do NOT translate them
- You MUST respond in {response_lang_name} regardless of conversation history or context language
- If the answer is not in the context, say so
- Do not add summary tags like "Synthesized from multiple sources" {disambiguation_hint}{region_hint}"""

        messages.append({"role": "user", "content": user_message})

        try:
            response = await llm_completion(
                model=settings.llm_model,
                messages=messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                stream=True,
            )

            full_response = ""
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_response += token
                    yield f"data: {json.dumps(token)}\n\n"

            # Send citations
            citations = extract_citations(documents)
            yield f"data: [CITATIONS]{json.dumps([c.model_dump() for c in citations])}\n\n"

            # Send follow-up suggestions
            suggestions = generate_suggestions(sub_ops, response_lang)
            if suggestions:
                yield f"data: [SUGGESTIONS]{json.dumps(suggestions)}\n\n"

            # Save history
            history.append({"role": "user", "content": request.message})
            history.append({"role": "assistant", "content": full_response})
            save_conversation(session_id, history)

            # Cache fresh questions
            if len(history) == 2:
                set_cached_response(request.message, detected_lang, {
                    "response": full_response,
                    "citations": [c.model_dump() for c in citations],
                    "has_answer": True,
                    "suggestions": suggestions,
                }, region=effective_region)

            yield f"data: [DONE]{session_id}\n\n"

        except Exception as e:
            logger.error("Stream error", error=str(e))
            yield f"data: [ERROR]{str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


@app.get("/api/v1/sources/search")
async def search_sources(query: str, top_k: int = 5):
    """Search source documents directly."""
    documents = search_documents(query, top_k=top_k)
    return {
        "query": query,
        "results": [
            {
                "text": doc["text"][:500] + "..." if len(doc["text"]) > 500 else doc["text"],
                "source_type": doc.get("source_type", "manual"),
                "page": doc["page"],
                "section": doc["section"],
                "timestamp": doc.get("timestamp"),
                "score": round(doc["score"], 3),
            }
            for doc in documents
        ],
    }


@app.delete("/api/v1/chat/history/{session_id}")
async def clear_history(session_id: str):
    """Clear conversation history."""
    key = f"conversation:{session_id}"
    redis_client.delete(key)
    return {"status": "cleared", "session_id": session_id}


@app.get("/api/v1/stats")
async def get_stats():
    """Get system statistics."""
    collection_info = qdrant_client.get_collection(COLLECTION_NAME)

    # Count cached responses
    cache_keys = redis_client.keys("cache:*")
    cache_count = len(cache_keys)

    # Fetch feedback stats
    feedback_stats = {"total": 0, "positive": 0, "negative": 0}
    try:
        from app.core.database import async_session_maker
        from app.models.feedback import Feedback as FeedbackModel, FeedbackRating
        from sqlalchemy import select, func
        async with async_session_maker() as db:
            total_q = await db.execute(select(func.count(FeedbackModel.id)))
            feedback_total = total_q.scalar() or 0
            pos_q = await db.execute(
                select(func.count(FeedbackModel.id)).where(
                    FeedbackModel.rating == FeedbackRating.POSITIVE
                )
            )
            feedback_positive = pos_q.scalar() or 0
            feedback_stats = {
                "total": feedback_total,
                "positive": feedback_positive,
                "negative": feedback_total - feedback_positive,
            }
    except Exception:
        pass

    return {
        "vectors_count": collection_info.points_count,
        "collection": COLLECTION_NAME,
        "embedding_model": settings.embedding_model,
        "llm_model": settings.llm_model,
        "cached_responses": cache_count,
        "feedback": feedback_stats,
    }


@app.delete("/api/v1/cache")
async def clear_cache():
    """Clear all cached chat responses."""
    cache_keys = redis_client.keys("cache:*")
    if cache_keys:
        redis_client.delete(*cache_keys)
    return {"status": "cleared", "keys_removed": len(cache_keys)}
