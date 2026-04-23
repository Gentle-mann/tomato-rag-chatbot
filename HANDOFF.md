# Handoff Guide / 引き継ぎガイド

**Target / 対象：** NTT East Agriculture Team / NTT東日本 農業チーム
**Version / バージョン：** v1.0.0
**Handed off / 引き継ぎ日：** April 2026

---

## Table of Contents / 目次

1. [Overview / 概要](#1-overview--概要)
2. [Architecture / アーキテクチャ](#2-architecture--アーキテクチャ)
3. [Environment Variables / 環境変数](#3-environment-variables--環境変数)
4. [Data Ingestion / データ取り込み](#4-data-ingestion--データ取り込み)
5. [Japanese-Specific Considerations / 日本語固有の注意点](#5-japanese-specific-considerations--日本語固有の注意点)
6. [Running in Production / 本番運用](#6-running-in-production--本番運用)
7. [Feedback Loop / フィードバックループ](#7-feedback-loop--フィードバックループ)
8. [Known Limitations / 既知の制限](#8-known-limitations--既知の制限)
9. [Extension Points / 拡張ポイント](#9-extension-points--拡張ポイント)
10. [Contact / 連絡先](#10-contact--連絡先)

---

## 1. Overview / 概要

This document walks through everything needed to operate, maintain, and extend the Tomato RAG Chatbot. Read §2–4 before first deployment. If you have questions, contact the original development team (§10).

本書は、トマトRAGチャットボットの運用・保守・拡張に必要な情報をまとめたものです。初回デプロイ前に §2〜4 をお読みください。不明点は §10 の連絡先までご連絡ください。

---

## 2. Architecture / アーキテクチャ

```
                    User (Browser / ブラウザ)
                              │
                              ▼ HTTPS
              Next.js frontend (port 3000)
                              │
                              ▼ REST / SSE
              FastAPI backend (port 8000)
                              │
        ┌─────────┬───────────┼──────────┬───────────────┐
        ▼         ▼           ▼          ▼               ▼
     Qdrant     Redis     PostgreSQL  Anthropic   FlagEmbedding
   (port 6333) (port 6379) (port 5432)  Claude       (BGE-M3)
```

**Query flow / クエリの流れ：**

1. Browser sends query → backend (/api/v1/chat/stream)
2. Backend translates non-Japanese queries to Japanese (for retrieval)
3. **Hybrid search** over Qdrant:
   - Dense vectors (BGE-M3, 1024-dim) — top 20
   - Sparse vectors (BGE-M3 lexical weights) — top 20
   - RRF fusion → top 10
4. **Cross-encoder reranks** top 10 → top 5
5. **Region boost** (+0.4 score for sources matching user's selected region)
6. Prompt assembled with retrieved chunks + conversation history
7. Claude Haiku generates response in user's UI language
8. Response **cached in Redis** (24h TTL, key = SHA-256(query + language))
9. Response streamed to browser via SSE

---

## 3. Environment Variables / 環境変数

### `backend/.env`

| Variable / 変数 | Required / 必須 | Default / デフォルト | Description / 説明 |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | — | Anthropic API key (console.anthropic.com) |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://postgres:postgres@localhost:5432/tomato_rag` | PostgreSQL URL |
| `REDIS_URL` | ✅ | `redis://localhost:6379` | Redis URL |
| `QDRANT_URL` | ✅ | `http://localhost:6333` | Qdrant URL |
| `QDRANT_COLLECTION_NAME` | ✅ | `tomato_cultivation` | Qdrant collection name |
| `LLM_MODEL` | ✅ | `anthropic/claude-haiku-4-5-20251001` | LiteLLM format: `<provider>/<model>` |
| `LLM_TEMPERATURE` | — | `0.1` | Low for factual grounding |
| `LLM_MAX_TOKENS` | — | `2048` | Max output tokens |
| `EMBEDDING_MODEL` | ✅ | `BAAI/bge-m3` | Multilingual dense+sparse |
| `CHUNK_SIZE` | — | `300` | Char-based, tuned for Japanese |
| `CHUNK_OVERLAP` | — | `100` | Overlap to preserve context |
| `RETRIEVAL_TOP_K` | — | `10` | Candidates before reranking |
| `RERANK_TOP_K` | — | `5` | Final chunks sent to LLM |
| `SIMILARITY_THRESHOLD` | — | `0.15` | Min relevance score |
| `DEBUG` | — | `false` | Enable verbose logging |

### `web/.env`

| Variable | Required | Default | Description |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | ✅ | `http://localhost:8000` | Backend URL visible to browser |

---

## 4. Data Ingestion / データ取り込み

### 4.1 Source Materials / 原資料

Source PDFs and transcripts are **delivered separately** (not in this repository). Request them from the TerraLogic team (§10) before first ingestion.

原資料PDFおよび書き起こしは **リポジトリに含まれておらず、別途提供** されます。初回取り込み前に §10 のチームへご連絡ください。

Materials include / 資料内容：
- `Japan's Tomato Cultivation Manual.pdf` — primary Japanese manual
- YouTube video transcript PDF
- Region-specific pest/disease PDFs (Nepal, Indonesia, etc.)
- FAMIC pesticide CSV databases

### 4.2 Ingest PDF Manual / PDFマニュアルの取り込み

```bash
cd backend
source venv/bin/activate
# Place PDF at data/pdfs/<name>.pdf
python process_pdf.py
```

**What it does / 処理内容：**
- Character-based chunking (300 chars, 100 overlap) — required for Japanese
- Sidebar stripping (vegetable name on every odd page)
- Page number removal via `page.find_tables()`
- OCR fallback for image-based pages (Tesseract)
- Non-destructive: deletes by `source_name` filter, then upserts (safe to re-run)

### 4.3 Ingest Video Transcript / 動画書き起こしの取り込み

```bash
python process_transcript.py
```

Expects timestamp-formatted text with `##` section headers. Timestamps are embedded in each chunk's payload (`timestamp: "MM:SS"`) so the frontend can link directly to the video moment.

### 4.4 Adding New Source Types / 新しい資料タイプの追加

Follow the pattern in `backend/ingest_utils.py`:

1. Create a new `process_<type>.py` script
2. Use `get_embedding_model()` for the BGE-M3 singleton
3. Call `delete_by_source(source_name)` before upsert (non-destructive scoped delete)
4. Build payloads with `{text, source_type, source_name, ...metadata}`
5. Call `clear_response_cache()` at end to invalidate stale cached answers

### 4.5 Region-Specific Sources / 地域別資料

Each chunk can have a `region` field: `japan`, `nepal`, `vietnam`, `indonesia`, or `philippines`. When a user selects a region in the UI, retrieval adds a **+0.4 score boost** to matching-region chunks. Existing data can be backfilled with region metadata — ask the TerraLogic team for the backfill scripts if needed (`backend/backfill_region.py`, delivered separately).

### 4.6 Clearing the Response Cache / 応答キャッシュのクリア

After re-ingesting, the response cache is **automatically cleared** by the ingestion scripts. To clear manually:

```bash
curl -X DELETE http://localhost:8000/api/v1/cache
```

---

## 5. Japanese-Specific Considerations / 日本語固有の注意点

### 5.1 Why BGE-M3 / BGE-M3を採用した理由

Japanese text has **no word boundaries** — traditional tokenizer-based sparse vectors (BM25) fail. BGE-M3 provides both dense (semantic) and sparse (lexical-weighted) vectors that handle Japanese without external tokenizers like MeCab.

日本語には単語境界がないため、従来のトークナイザーベースの疎ベクトル（BM25等）では不十分です。BGE-M3は、MeCab等の外部トークナイザー不要で、密ベクトル（意味的）と疎ベクトル（語彙的）の両方を生成します。

### 5.2 Character-based Chunking / 文字ベースのチャンキング

`process_pdf.py` uses **300-character chunks with 100-character overlap**. Word-based chunking (typical for English) produces garbled chunks for Japanese because there are no spaces to split on.

### 5.3 Query Translation / クエリ翻訳

Non-Japanese queries are translated to Japanese by Claude before retrieval. Sparse vectors are token-based and require the same language as the corpus; dense vectors cross-lingually correlate but quality improves with translation.

非日本語クエリは、検索前にClaudeによって日本語に翻訳されます。疎ベクトルはトークンベースのため対象言語と一致している必要があり、密ベクトルは言語横断的ではあるものの、翻訳によって品質が向上します。

### 5.4 Response Language / 応答言語

The response is **always generated in the user's UI language**. The LLM synthesizes from Japanese source chunks and outputs in the user's chosen language (English, Japanese, Nepali, Indonesian, Vietnamese).

応答は **常にユーザーのUI言語で生成** されます。LLMは日本語のソースチャンクから情報を合成し、ユーザーが選択した言語（英語、日本語、ネパール語、インドネシア語、ベトナム語）で出力します。

---

## 6. Running in Production / 本番運用

### 6.1 Docker Compose (simplest) / Docker Compose（最もシンプル）

```bash
docker compose up -d
```

Current `docker-compose.yml` runs postgres, redis, qdrant as services. The backend and frontend Dockerfiles are provided — uncomment their services in `docker-compose.yml` to run everything in Docker, or run them on the host for development.

### 6.2 Scaling Notes / スケーリングに関する注意

- **Backend**: Stateless. Scale horizontally behind a load balancer. Session state is in Redis, so affinity is not required.
- **Qdrant**: Single-node is fine for <100k chunks. Switch to clustered mode for larger corpora (see [Qdrant docs](https://qdrant.tech/documentation/guides/distributed_deployment/)).
- **Redis**: Cache + conversation history (1h TTL for history, 24h for responses). Safe to flush periodically.
- **PostgreSQL**: Document metadata only. Low write volume.

### 6.3 Cost Estimate / コスト概算

- Claude Haiku: ~$0.25 per 1M input tokens, ~$1.25 per 1M output tokens
- Average query: ~2K input + ~500 output tokens ≈ **$0.00113 per query**
- **Cache hit rate** (~60% after warmup): no API cost for cached queries
- Qdrant/Redis/PostgreSQL: self-hosted, no per-query cost

### 6.4 Monitoring / 監視

- `GET /health` — liveness check (returns `{"status": "healthy", ...}`)
- `GET /api/v1/stats` — vector count, cache entry count
- Backend logs via `structlog` (stdout JSON)

---

## 7. Feedback Loop / フィードバックループ

Users click 👍 / 👎 on responses. **Negative feedback (👎)**:

1. Evicts the cached response for that specific query
2. Logs to the PostgreSQL `feedback` table with the query, response, and optional comment

Reviewing negative feedback / ネガティブフィードバックの確認：

```sql
SELECT query, response, comment, created_at
FROM feedback
WHERE rating = 'negative'
ORDER BY created_at DESC
LIMIT 50;
```

This enables continuous improvement: bad answers surface, get examined, and the source materials / prompts / retrieval tuning can be adjusted.

---

## 8. Known Limitations / 既知の制限

1. **Voice input quality varies by language.** Chrome has the best support for all 5 languages. Firefox lacks the Web Speech API. Nepali recognition accuracy is lower than English/Japanese.

   **音声入力の品質は言語によって異なります。** Chromeが全5言語で最良。FirefoxはWeb Speech API非対応。ネパール語の認識精度は英語・日本語より低い。

2. **Philippine Tagalog not fully supported.** Speech recognition uses `en-US` for the Philippines region.

3. **No evaluation pipeline.** MRR / recall metrics are not measured. Consider adding a test question set with expected citations (see §9).

4. **No per-source filtering in UI.** Users cannot search within only the manual or only the transcript — all sources are searched together.

5. **Response caching is query-level, not conversation-aware.** Multi-turn queries with history are not cached (intentional, to avoid stale context).

6. **OCR fallback is CPU-only.** Image-heavy PDFs are slow to ingest. Consider GPU-enabled Tesseract or Cloud Vision API for production scale.

7. **Single LLM provider (Claude).** Failover to OpenAI is configured via LiteLLM but not automatically triggered.

---

## 9. Extension Points / 拡張ポイント

- **Additional UI languages**: Add to `Language` type in `web/lib/store.ts`, add translations in `web/lib/i18n.ts`, update BCP-47 map in `web/lib/useSpeechRecognition.ts`.

- **Additional source types**: Follow the `ingest_utils.py` pattern (§4.4).

- **Improved reranker**: Current model is `mmarco-mMiniLMv2-L12-H384-v1`. Try `BAAI/bge-reranker-v2-m3` for better Japanese ranking (larger, slower).

- **Evaluation framework**: Create `backend/eval/` with a test set. Use MRR@5 and Recall@10 against expected citations. Automate regression checks in CI.

- **Per-source filtering**: Add a source selector in the UI (`lib/store.ts` → `sourceFilter`), filter the Qdrant query by `source_type`.

- **Voice language auto-detection**: Replace Web Speech API with a server-side Whisper call for better accuracy and true language auto-detection (adds ~1–2s latency and ~$0.006/min cost).

---

## 10. Contact / 連絡先

**Original development team / 開発チーム：**

| Name / 氏名 | Email |
|---|---|
| Khalifa (Ishaq) Ibrahim | ishaqibrahim017@gmail.com |
| Ramazan Bolatkhan | rambol1@uni.minerva.edu |
| Wolfgang Sander | wolfgang.sander@uni.minerva.edu |

**Institution / 所属：** Minerva University Civic Project 2025–2026
**Partner / 連携先：** NTT East Agriculture Department

For questions within 30 days of handoff, please contact the team members above. After that period, ongoing support may be arranged via the team lead.

引き継ぎ後30日以内の質問は上記チームまでご連絡ください。その後のサポートについては、チームリーダーまで別途ご相談ください。
