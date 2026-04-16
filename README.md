# Tomato RAG Chatbot / トマトRAGチャットボット

A multilingual, source-grounded RAG chatbot for tomato cultivation. Every answer is based exclusively on provided reference materials (Japanese cultivation manual + YouTube video transcript + region-specific sources) and includes per-chunk citations. Supports English, Japanese, Nepali, Indonesian, and Vietnamese.

トマト栽培のための多言語RAGチャットボットです。各回答は、提供された参照資料（日本語栽培マニュアル、YouTube動画の書き起こし、地域別資料）のみに基づき、チャンク単位の引用を必ず付与します。英語、日本語、ネパール語、インドネシア語、ベトナム語に対応。

---

## Features / 機能

| EN | JP |
|---|---|
| **Grounded answers** — every response cites specific pages/timestamps; no hallucination | **根拠ある回答** — ページ／タイムスタンプの引用付き、幻覚なし |
| **5 UI languages** with cross-lingual retrieval | **5言語UI**、言語横断検索対応 |
| **Regional context** — answers tailored to Japan, Nepal, Vietnam, Indonesia, Philippines | **地域対応** — 日本、ネパール、ベトナム、インドネシア、フィリピンの文脈別 |
| **Voice input** — browser-native, region-aware language detection | **音声入力** — ブラウザネイティブ、地域別言語検出 |
| **Streaming responses** via Server-Sent Events | **ストリーミング応答** (SSE) |
| **Hybrid search** — dense (BGE-M3) + sparse vectors with RRF fusion | **ハイブリッド検索** — 密 + 疎ベクトル、RRF融合 |
| **Reranking** — cross-encoder re-scoring for top results | **再ランキング** — クロスエンコーダによる上位結果の再評価 |
| **Response caching** — Redis, 24h TTL (~300× speedup on cache hit) | **応答キャッシュ** — Redis、24時間TTL (キャッシュヒット時約300倍高速) |
| **Feedback loop** — 👎 evicts the cached response | **フィードバックループ** — 👎でキャッシュ無効化 |
| **Admin UI** — document upload, reprocess, delete | **管理UI** — ドキュメントのアップロード/再処理/削除 |

---

## Tech Stack / 技術スタック

| Component / コンポーネント | Technology / 技術 |
|---|---|
| Backend / バックエンド | FastAPI (Python 3.9+) |
| Frontend / フロントエンド | Next.js 14 + TypeScript + Tailwind CSS |
| LLM | Claude via LiteLLM (`anthropic/claude-3-haiku-20240307`) |
| Embedding / 埋め込み | BGE-M3 (dense 1024-dim + sparse) via FlagEmbedding |
| Reranker / リランカー | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` |
| Vector DB / ベクトルDB | Qdrant (named vectors + RRF fusion) |
| Database / データベース | PostgreSQL (async SQLAlchemy) |
| Cache / キャッシュ | Redis |
| Container / コンテナ | Docker Compose |

---

## Quick Start / クイックスタート

### Prerequisites / 前提条件

- Docker & Docker Compose
- Python 3.9 or higher / Python 3.9以上
- Node.js 20 or higher / Node.js 20以上
- Anthropic API key / Anthropic APIキー

### 1. Clone & Configure / クローン & 設定

```bash
git clone <repository-url>
cd tomato-rag-chatbot

# Backend environment
cp backend/.env.example backend/.env
# Edit backend/.env — set ANTHROPIC_API_KEY
# backend/.env を編集し、ANTHROPIC_API_KEY を設定

# Frontend environment
cp web/.env.example web/.env
```

### 2. Start Docker services / Docker起動

```bash
docker compose up -d postgres redis qdrant
```

### 3. Start backend / バックエンド起動

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main_full:app --host 0.0.0.0 --port 8000
```

### 4. Start frontend / フロントエンド起動

```bash
cd web
npm install
npm run dev
```

### 5. Ingest source materials / 資料の取り込み

Place PDFs in `data/pdfs/` and transcripts in `data/transcripts/`, then:
PDFを `data/pdfs/`、書き起こしを `data/transcripts/` に配置後：

```bash
cd backend
source venv/bin/activate
python process_pdf.py           # Ingest PDF manual / マニュアル取り込み
python process_transcript.py    # Ingest video transcript / 動画書き起こし取り込み
```

### Access / アクセス

- Web UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Admin Panel: http://localhost:3000/admin/documents

---

## Project Structure / ディレクトリ構成

```
tomato-rag-chatbot/
├── backend/
│   ├── app/
│   │   ├── main_full.py               # Main FastAPI backend with full RAG
│   │   ├── config.py                  # Settings
│   │   ├── api/v1/endpoints/          # API routes (chat, documents, feedback)
│   │   ├── core/                      # DB, Qdrant, Redis clients
│   │   ├── models/                    # SQLAlchemy models
│   │   └── services/                  # Document processing, embeddings
│   ├── ingest_utils.py                # Shared ingestion utilities
│   ├── process_pdf.py                 # PDF manual ingestion script
│   ├── process_transcript.py          # Video transcript ingestion script
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── web/
│   ├── app/
│   │   ├── page.tsx                   # Main chat page
│   │   └── admin/documents/           # Admin UI
│   ├── components/chat/               # Chat components
│   │   ├── ChatInput.tsx              # Input + voice button
│   │   ├── ChatMessage.tsx
│   │   ├── CitationCard.tsx
│   │   ├── LanguageSelector.tsx
│   │   ├── RegionSelector.tsx
│   │   └── WelcomeScreen.tsx
│   ├── lib/
│   │   ├── api.ts                     # API client
│   │   ├── i18n.ts                    # UI translations (5 languages)
│   │   ├── store.ts                   # Zustand state
│   │   └── useSpeechRecognition.ts    # Voice input hook
│   ├── Dockerfile
│   └── .env.example
├── data/
│   ├── pdfs/                          # Source PDFs (delivered separately)
│   └── transcripts/                   # Video transcripts (delivered separately)
├── docker-compose.yml
├── README.md
└── HANDOFF.md                         # Detailed handoff guide
```

---

## API Endpoints / APIエンドポイント

### Chat
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Send a message (blocking) |
| `POST` | `/api/v1/chat/stream` | Stream a response via SSE |
| `GET` | `/api/v1/chat/history/{session_id}` | Conversation history |
| `DELETE` | `/api/v1/chat/history/{session_id}` | Clear history |

### Documents
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/documents/upload` | Upload a PDF |
| `GET` | `/api/v1/documents` | List all documents |
| `GET` | `/api/v1/documents/{id}/status` | Processing status |
| `DELETE` | `/api/v1/documents/{id}` | Delete a document |
| `POST` | `/api/v1/documents/{id}/reprocess` | Reprocess a document |

### Admin & Feedback
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/api/v1/stats` | Vector count, cache entry count |
| `DELETE` | `/api/v1/cache` | Clear response cache |
| `POST` | `/api/v1/feedback` | Submit 👍 / 👎 feedback |

---

## Data Sources / データソース

Source materials (Japanese tomato cultivation manual, YouTube video transcript, region-specific pest/disease PDFs) are **not included in this repository**. They are delivered separately to NTT East as per the partnership agreement.

原資料（日本語トマト栽培マニュアル、YouTube動画書き起こし、地域別病害虫PDF等）は **このリポジトリには含まれていません**。連携協定に基づき、NTT東日本に別途提供されます。

See [HANDOFF.md](./HANDOFF.md) for ingestion procedures. / 取り込み手順は [HANDOFF.md](./HANDOFF.md) 参照。

---

## Documentation / ドキュメント

- [HANDOFF.md](./HANDOFF.md) — Detailed handoff guide (setup, architecture, extension points) / 引き継ぎガイド（セットアップ、アーキテクチャ、拡張ポイント）

---

## License / ライセンス

Private — Developed by Team TerraLogic (Minerva University) in partnership with NTT East Agriculture.
非公開 — ミネルバ大学 TerraLogic チーム、NTT東日本農業部との協業で開発。
