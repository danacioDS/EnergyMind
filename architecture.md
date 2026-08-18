# EnergyMind — Architecture

## Overview

**EnergyMind** is a domain-specific RAG (Retrieval-Augmented Generation) system for Bolivian energy regulation. It combines semantic retrieval with Qdrant and lexical retrieval with BM25, processes legal documents at article level, and uses a multi-provider LLM architecture for resilient generation. The system returns traceable sources and can abstain when the retrieved evidence doesn't support an answer.

This document describes the architecture **as implemented** in the current codebase.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                    │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  Frontend · Next.js 16 (React 19, shadcn/ui, Tailwind v4)         │  │
│  │  Port 3000 — rewrites /api/* → backend                             │  │
│  │  Chat interface with structured legal analysis panels              │  │
│  └─────────────────────────────┬──────────────────────────────────────┘  │
│                                 │ HTTP + SSE                              │
├─────────────────────────────────┼─────────────────────────────────────────┤
│                      API LAYER · FastAPI :8000                             │
│  ┌─────────────────────────────┴──────────────────────────────────────┐  │
│  │  app/api/routes.py   (prefix /api/v1)                              │  │
│  │   POST /query        POST /query/stream                             │  │
│  │   POST /ingest       GET  /corpus/stats                             │  │
│  │   GET  /health       GET  /health/ready                             │  │
│  │  Middlewares: CORS (open) + CorrelationID (X-Correlation-ID)       │  │
│  └─────────────────────────────┬──────────────────────────────────────┘  │
│                                 │                                         │
├─────────────────────────────────┼─────────────────────────────────────────┤
│                       SERVICE LAYER                                        │
│  ┌─────────────────────────────┴──────────────────────────────────────┐  │
│  │  QueryService         — orchestrates: cache → pipeline → cache     │  │
│  │  SSEStreamManager     — wraps events in text/event-stream frames   │  │
│  │  Redis Cache          — response dedup (TTL 1h)                    │  │
│  └─────────────────────────────┬──────────────────────────────────────┘  │
│                                 │                                         │
├─────────────────────────────────┼─────────────────────────────────────────┤
│                        RAG / AGENT LAYER                                   │
│  ┌─────────────────────────────┴──────────────────────────────────────┐  │
│  │                                                                     │  │
│  │  RAGPipeline (primary)           LegalAgentGraph (LangGraph)        │  │
│  │  ┌────────────────────────┐     ┌───────────────────────────┐      │  │
│  │  │ retrieve → context     │     │ retrieve → analyze         │      │  │
│  │  │   → LLM generate       │     │   → refine (loop ×3)       │      │  │
│  │  │   → assemble response  │     │   → risk_assess            │      │  │
│  │  │                        │     │   → finalize               │      │  │
│  │  │ Abstains when evidence │     │                            │      │  │
│  │  │ is insufficient        │     │ ⚠ INCOMPLETE              │      │  │
│  │  └────────────────────────┘     └───────────────────────────┘      │  │
│  └─────────────────────────────┬──────────────────────────────────────┘  │
│                                 │                                         │
├─────────────────────────────────┼─────────────────────────────────────────┤
│                    RETRIEVAL ENGINE                                         │
│  ┌─────────────────────────────┴──────────────────────────────────────┐  │
│  │  RetrievalEngine                                                            │  │
│  │                                                                             │  │
│  │  ┌─────────────┐  ┌─────────────┐                                          │  │
│  │  │  BM25         │  │  Dense        │  ← parallel via asyncio.gather()     │  │
│  │  │  (sparse)     │  │  (Qdrant)     │                                       │  │
│  │  │  Spanish      │  │  MiniLM-L6    │                                       │  │
│  │  │  legal token  │  │  384-d COSINE │                                       │  │
│  │  └──────┬───────┘  └──────┬───────┘                                        │  │
│  │         └──────────┬──────┘                                                 │  │
│  │                    ▼                                                        │  │
│  │           ┌────────────────┐                                                │  │
│  │           │  Hybrid Fusion  │  α = 0.7 (code) / 0.3 (concept) / 0.5 (def) │  │
│  │           │  min-max norm   │                                               │  │
│  │           └────────┬───────┘                                                │  │
│  │                    ▼                                                        │  │
│  │           ┌────────────────┐                                                │  │
│  │           │  Reranker       │  cross-encoder (disabled for memory)          │  │
│  │           └────────┬───────┘                                                │  │
│  │                    ▼                                                        │  │
│  │              Top-K (10 → 5)                                                 │  │
│  └─────────────────────────────┬──────────────────────────────────────┘  │
│                                 │                                         │
├─────────────────────────────────┼─────────────────────────────────────────┤
│                       LLM LAYER · Multi-Provider                           │
│  ┌─────────────────────────────┴──────────────────────────────────────┐  │
│  │  LLMRouter ── fallback chain with health tracking:                  │  │
│  │                                                                     │  │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐     │  │
│  │  │  Groq     │───▶│Cloudflare│───▶│  Gemini   │───▶│ Ollama   │     │  │
│  │  │  Llama    │    │  Llama    │    │  Flash    │    │  Local   │     │  │
│  │  │  3.3 70B  │    │  3.1 8B   │    │  2.5      │    │  Llama   │     │  │
│  │  └──────────┘    └──────────┘    └──────────┘    └──────────┘     │  │
│  │                                                                     │  │
│  │  Provider fails → blacklisted → next provider tried                 │  │
│  │  Success → blacklist reset                                          │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                       INFRASTRUCTURE                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Qdrant      │  │  Redis       │  │  Embeddings   │  │  Legal Corpus   │  │
│  │  Vector DB   │  │  Cache       │  │  MiniLM-L6    │  │  45 articles    │  │
│  │  :6333 REST  │  │  :6379       │  │  384-d CPU    │  │  5 doc types    │  │
│  │  :6334 gRPC  │  │              │  │               │  │                 │  │
│  └─────────────┘  └─────────────┘  └──────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. API Layer (`app/api/routes.py`)

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/api/v1/query` | POST | Blocking RAG query | ⚠ 503 (app.state.ready never set) |
| `/api/v1/query/stream` | POST | Streaming SSE query | ⚠ 503 |
| `/api/v1/ingest` | POST | Trigger ingestion | ❌ 500 (await on sync func) |
| `/api/v1/corpus/stats` | GET | Corpus statistics | ⚠ Partial (total_units only) |
| `/api/v1/health` | GET | Liveness | ✅ `{"status":"alive"}` |
| `/api/v1/health/ready` | GET | Readiness | ❌ Duplicated + 503 always |

**Middlewares** (`app/main.py`):
- **CORS**: `allow_origins=["*"]`, `allow_credentials=True`
- **CorrelationIDMiddleware**: injects `X-Correlation-ID` into loguru context

### 2. Service Layer (`app/services/`)

- **`QueryService`** — orchestrates the flow: cache key generation → Redis lookup → `RAGPipeline` (or `LegalAgentGraph` if `use_agent=true`) → cache response → attach `processing_time_ms`.
- **`SSEStreamManager`** — wraps async event generators into SSE frames (`event: <type>\n data: {...}\n\n`), with `error` event on exceptions.
- **`cache.py`** — async Redis wrapper (`init_redis`, `get_cached`, `set_cached`). Uses double-hashed keys for consistency.

### 3. RAG / Agent Layer

#### RAGPipeline (`app/rag/pipeline.py`)

The primary query path. Steps:
1. `retrieve()` → `RetrievalEngine` (BM25 + dense + fusion + rerank)
2. If no documents → responds with "insufficient context" (detects language: es/en/pt)
3. `_build_context()` — formats documents as `[N] <id>:\n<text>` blocks (max 5)
4. Generates an **inline prompt** (does not use `app/prompts/`)
5. `LegalChain.generate()` → `LLMRouter` → provider chain
6. Assembles `QueryResponse` with risk_matrix and incentives

**Abstention**: the system explicitly sets `insufficient_context: true` when retrieved evidence is too weak to support a confident answer, rather than fabricating.

#### LegalAgentGraph (`app/agents/graph.py`) — ⚠ INCOMPLETE

LangGraph state machine with 5 nodes:
```
retrieve → analyze ──(needs_refinement && iter<3)──→ refine → retrieve
                    └──(else)──→ risk_assess → finalize → END
```

Current issues preventing operation:
- `_analyze_node` calls `chain.structured_answer(...)` — does not exist on `LegalChain`
- `_risk_assess_node` calls `chain.analyze_risk(...)` — does not exist
- `_refine_node` uses `chain.llm.ainvoke(...)` — `LegalChain` has no `llm` attribute
- `QueryService` passes `QueryRequest` but `run()` expects `(question, subsector, tipo_norma)`

### 4. Retrieval Engine (`app/retrieval/`)

Per-query flow (`RetrievalEngine.retrieve`):

```
Query
  │
  ├─ 1. Metadata Filter ──────────────── keyword → filter inference
  │     "solar" → subsector: Solar
  │     "ley 1604" → norma_id: 1604
  │     Always forces: vigente: True
  │
  ├─ 2. BM25 (sparse) ──────────────── asyncio: hybrid.bm25.search()
  │     • Spanish legal tokenizer (custom stopwords)
  │     • Index built at startup from Qdrant (scroll_all)
  │     • Persisted to cache/bm25_index.pkl
  │
  ├─ 3. Dense (vectorial) ──────────── run_in_executor: qdrant.search()
  │     • Embeddings MiniLM-L6-v2 (384-d) → Qdrant COSINE search
  │     • Qdrant payload filters (if available)
  │
  ├─ 4. Hybrid Fusion ──────────────── HybridRetriever._fusion()
  │     • Min-max normalization per list
  │     • score = α·bm25_norm + (1-α)·dense_norm
  │     • Adaptive α: 0.7 (legal code) / 0.3 (concept) / 0.5 (default)
  │
  ├─ 5. Reranking ──────────────────── Reranker (cross-encoder)
  │     • DISABLED (no-op) for Render Free memory
  │     • ⚠ await on sync method → silent exception → fallback
  │
  └─ 6. Top-K final ────────────────── reranked[:top_k] (default 10, final 5)
```

**MetadataFilter** — keyword→filter map (solar→subsector Solar, ley 1604→norma_id, inversión→enfoque, etc.). Always injects `vigente: True`. ⚠ Request filters from `QueryRequest` are not propagated here (see report §7.4).

### 5. LLM Layer (`app/llm/`)

- **`LLMRouter`** — provider list with automatic fallback:
  1. **Groq** (primary): `llama-3.3-70b-versatile` via `groq` SDK, `temperature=0.1`
  2. **Cloudflare** (fallback): `llama-3.1-8b` via `cloudflare-ai` SDK
  3. **Gemini** (fallback): `gemini-2.0-flash` via `google-generativeai`
  4. **Ollama** (local fallback): `llama-3.2-1b` via HTTP
- On provider failure: adds to `failed_providers`, skips in next call; resets on success
- `generate()` is **synchronous** → blocks the event loop during LLM calls (2-10s)
- SDK clients are recreated per call (no pooling)

### 6. Ingestion Pipeline (`ingestion/`)

```
corpus/raw/*.txt
  │
  ├─ LegalTextNormalizer ── removes headers/footers, normalizes "Art."→"Artículo",
  │                          normalizes norm IDs (Ley N°, DS)
  ├─ LegalDocumentParser ── regex pattern per norm type to split articles,
  │                          extracts article number, detects type if missing
  ├─ Metadata Extractor ── risk_flags, subsector, enfoque, tipo_norma, incentive
  │                          (keyword-based) + override from CORPUS_DEFINITIONS
  ├─ all_units.json ────── exports to corpus/normalized/all_units.json
  └─ QdrantStore.upsert ── embeddings in batch → upsert of 32
                            UUID5(unit.id) → idempotent
```

**CORPUS_DEFINITIONS** (`ingestion/pipeline.py`):

| File | Type | ID | Metadata Override |
|------|------|----|-------------------|
| `constitucion_bolivia_articulos_seleccionados.txt` | Constitucion | CPE | subsector General, enfoque Regulacion, risk [Constitutional Hierarchy] |
| `ley_1604_1994.txt` | Ley | 1604 | risk [Market Framework] |
| `ley_943_modificaciones.txt` | Ley | 943 | — |
| `ds_5503_2025.txt` | Decreto Supremo | 5503 | enfoque Inversion, risk [Regulatory Instability, Nationalization Risk] |

> ⚠ `aetn_resoluciones_muestra.txt` exists but is **not in** `CORPUS_DEFINITIONS`.

**Scrapers** (`ingestion/lexivox/`, `ingestion/aetn/`) — httpx async clients for LexiVox and AETN; implemented but **not connected** to the pipeline.

### 7. Core / Resources (`core/`)

- **`embeddings.py`** — thread-safe singleton (`get_embedder()`) with lazy-loading of `all-MiniLM-L6-v2` on CPU.
- **`resource_manager.py`** — `ResourceManager.warmup()` loads embedder and Qdrant in parallel; `embedder()`/`qdrant()` raise errors if no warmup occurred.

### 8. Vector Store (`vectorstore/qdrant_client.py`)

- `QdrantStore` — **synchronous** wrapper around `qdrant-client`.
- Collection `energymind`, 384-d vectors, COSINE distance.
- Payload indexes: `tipo_norma`, `norma_id`, `subsector`, `enfoque`, `sector` (keyword) + `vigente`, `renewable_incentive` (bool).
- `search()` with `build_filter()` (MUST conditions) and `scroll_all()` for BM25 bootstrap.

### 9. Data Models (`app/models/`)

- **`LegalUnit`** — article-level legal unit with rich metadata: `id`, `tipo_norma`, `norma_id`, `articulo`, `tema`, `vigente`, `sector`, `subsector`, `enfoque`, `risk_flags`, `renewable_incentive`, `texto`.
- **`QueryRequest`** — `question`, `subsector`, `tipo_norma`, `vigente`, `top_k`, `use_agent`.
- **`QueryResponse`** — `question`, `answer: RegulatoryAnalysis` (direct_conclusion, regulatory_analysis, legal_citations, risk_matrix, incentives_detected, insufficient_context), `sources`, `processing_time_ms`, `cached`.

### 10. Frontend (`frontend/`)

- **Next.js 16** with App Router, React 19, TypeScript, Tailwind v4.
- **`lib/api.ts`** — robust SSE client: retries with exponential backoff (max 3), inactivity timeout (60s), sequence guards (`seq`, `Last-Event-Id`), `AbortSignal` support.
- **`lib/types.ts`** — TypeScript interfaces aligned with backend schemas (StreamEvent: start, retrieval, analysis, risk, incentives, heartbeat, insufficient_context, complete, error).
- **`chat-interface.tsx`** — chat view: blocking mode (`use_agent`) or streaming (SSE); renders structured analysis.
- **`stats/page.tsx`** — dashboard with recharts metrics.
- **`next.config.ts`** — rewrites `/api/:path*` → `${API_URL}` (default localhost:8000).

---

## Data Flow: Query Lifecycle

```
 1.  Frontend → POST /api/v1/query {question, subsector, tipo_norma, use_agent}
 2.  FastAPI (CORS + CorrelationID) → routes.py
 3.  get_query_service() → requires app.state.ready ⚠ (never set → 503)
 4.  QueryService.process_query(request)
 5.    → _get_cache_key() (sha256 of question + filters)
 6.    → Redis get_cached (if hit → return cached response)
 7.    → RAGPipeline.query(request)  [or agent.run() — broken]
 8.      → RetrievalEngine.retrieve(query, metadata_filter=None ⚠)
 9.        → BM25 (async) ‖ Dense via Qdrant (threadpool)
10.        → HybridRetriever._fusion(adaptive alpha)
11.        → Reranker (no-op) → top_k
12.      → _build_context(documents[:5])
13.      → LegalChain.generate(prompt) → LLMRouter → Groq → Gemini
14.      → QueryResponse with risk_matrix/incentives
15.  QueryService → Redis set_cached (TTL 3600s)
16.  → JSON to client
```

### SSE Flow (`/query/stream`)

`start` → `retrieval_start` → `retrieval_complete` → `generation_start` → `chunk` (simulated, text splitting) → `sources` → `complete`.

> Note: event types documented in the frontend (`analysis`, `risk`, `incentives`, `heartbeat`, `insufficient_context`) **are not emitted** by the current backend; the real stream only emits `start/retrieval_start/retrieval_complete/generation_start/chunk/sources/complete`.

---

## Startup and Lifecycle

```
 1. uvicorn app.main:app → FastAPI lifespan
 2. setup_logging() → loguru with correlation_id
 3. lifespan: _warmup_started=True → asyncio.create_task(_background_init)
 4. _background_init → ResourceManager.warmup()
       ├─ _load_embedder (threadpool)  — MiniLM-L6-v2
       └─ _load_qdrant                 — QdrantClient + ensure collection
    → _warmup_complete=True (global)
 5. ⚠ app.state.ready NEVER set → all query endpoints return 503
 6. Readiness exposed by 2 routes with same URL (inconsistent)
```

> The intended design was: background warmup + readiness gating (503 → 200) and `QueryService` initialized in parallel (`_init_pipeline`, `_init_agent`, `_init_redis`). These methods exist in `QueryService` but are **never invoked** from the lifespan.

---

## Technology Stack

| Category | Technology |
|----------|-----------|
| Runtime | Python 3.11.9 |
| API | FastAPI 0.115 + uvicorn |
| RAG | LangChain 0.2 / LangGraph 0.2 (incomplete agent) |
| Vector Store | Qdrant 1.13 (collection `energymind`, COSINE, 384-d) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (CPU) |
| Reranker | cross-encoder (config) — disabled |
| Sparse | rank-bm25 (BM25Okapi) + Spanish legal tokenizer |
| LLM | Groq `llama-3.3-70b-versatile` → Gemini `gemini-2.0-flash` |
| Cache | Redis 7 (async redis-py) |
| Validation | Pydantic v2 / pydantic-settings |
| Logging | loguru with correlation IDs |
| Frontend | Next.js 16, React 19, shadcn/ui, Tailwind v4, recharts |
| Infra | Docker Compose, multi-stage Dockerfile, render.yaml |
| Tests | pytest + pytest-asyncio |
| Eval | RAGAS (script) |

---

## Deployment

`docker/docker-compose.yml`:

| Service | Image | Port | Volume |
|---------|-------|------|--------|
| `qdrant` | qdrant/qdrant:v1.13.2 | 6333 (REST) / 6334 (gRPC) | `qdrant_storage` |
| `redis` | redis:7-alpine | 6379 | `redis_data` |
| `lexenergy-api` | build multi-stage | 8000 | corpus/, logs/ |
| `lexenergy-frontend` | build frontend | 3000 | — |

Notes:
- `lexenergy-api` mounts `corpus/` and `logs/`, reads `../.env`, and connects `host.docker.internal` for Ollama (optional local LLM).
- Multi-stage Dockerfile: build stage installs torch CPU and downloads the embedding model; final image copies site-packages, HF cache, and code.
- ⚠ `Dockerfile` contains a hardcoded `HF_TOKEN` (lines 27 and 56).
- `render.yaml` deploys the API on Render Free tier.

---

## Project Structure

```
energymind/
├── app/                    # FastAPI backend
│   ├── api/routes.py       # REST endpoints + SSE
│   ├── rag/                # RAGPipeline, LegalChain, ContextBuilder
│   ├── retrieval/          # BM25, dense, hybrid, reranker, metadata filter
│   ├── agents/graph.py     # LangGraph graph (incomplete)
│   ├── llm/                # Providers + router with fallback
│   ├── models/             # Pydantic schemas
│   ├── services/           # QueryService, SSE, Redis cache
│   ├── prompts/            # Legal prompt templates
│   ├── config.py           # Configuration (pydantic-settings)
│   └── main.py             # FastAPI app + lifespan
├── core/                   # Embeddings singleton + ResourceManager
├── ingestion/              # Parsing, normalization, metadata, scrapers
├── vectorstore/            # Qdrant wrapper
├── corpus/                 # raw / processed / normalized
├── cache/                  # Persisted BM25 index
├── frontend/               # Next.js 16 (chat + stats)
├── tests/                  # Unit + golden regression
├── evaluation/             # RAGAS evaluation script
└── docker/                 # Dockerfile + docker-compose.yml
```

---

## Documentation vs. Implementation Divergences

| Documented (README/prev arch) | Actual |
|-------------------------------|--------|
| BGE-M3 embeddings (1024-d) | `all-MiniLM-L6-v2` (384-d) |
| BM25 tokenization with jieba | Custom Spanish legal tokenizer |
| Active BGE-reranker-large | Reranker **disabled** (no-op) |
| SSE events: analysis/risk/incentives/heartbeat | Only start/retrieval/generation/chunk/sources/complete |
| Readiness 200 after warmup | Permanent 503 (`app.state.ready` never set) |
| Working agent mode | Nonexistent methods → crash |
| Ingestion via API | `await` on sync func → 500 |
| Risk matrix derived from content | Hardcoded values |
| Scrapers LexiVox/AETN connected | Implemented, not used |
| Functional RAGAS | Script with outdated API |

---

## Ingestion Sequence Diagram

```
CLI/API                          IngestionPipeline                    Qdrant
  │  ingest                            │                                │
  ├─► run() ──────────────────────────►│                                │
  │     process_raw_files()            │                                │
  │       for each CORPUS_DEFINITION   │                                │
  │         parse_file()               │                                │
  │           normalize() → split_articles() → LegalUnit[]             │
  │         apply metadata override     │                                │
  │       to_json() → all_units.json   │                                │
  │     index_to_qdrant(units)         │                                │
  │       QdrantStore.initialize() ────┼──────────────────────────────►│
  │       upsert_units(units)          │  embed → upsert batch 32      │
  │                                    │◄──────────────────────────────│
  │◄─ count total ─────────────────────│                                │
```

---

## Quick Reference: Key Files

| File | Responsibility |
|------|----------------|
| `app/main.py` | FastAPI app, lifespan, background warmup, global readiness |
| `app/api/routes.py` | Endpoints, QueryService dependency injection |
| `app/services/query_service.py` | Query orchestration + cache |
| `app/rag/pipeline.py` | RAG pipeline (retrieve → context → generate) |
| `app/retrieval/engine.py` | Multi-stage retrieval engine |
| `app/retrieval/hybrid.py` | Hybrid fusion with adaptive alpha |
| `app/retrieval/bm25.py` | Spanish BM25 index + persistence |
| `vectorstore/qdrant_client.py` | Qdrant wrapper (search, upsert, filters) |
| `ingestion/pipeline.py` | Corpus definitions + ingestion flow |
| `core/runtime/resource_manager.py` | Embedder and Qdrant warmup |
| `frontend/src/lib/api.ts` | SSE client with retries |
| `docker/docker-compose.yml` | Service orchestration |
