# LexEnergy Bolivia — Architecture

## System Overview

LexEnergy Bolivia is a **Legal RAG (Retrieval-Augmented Generation) platform** specialized in Bolivian renewable energy legislation. The system ingests legal documents (constitution, laws, decrees, resolutions), indexes them in a vector database, and exposes a multi-stage retrieval pipeline with LLM-powered legal reasoning through a FastAPI backend and Next.js frontend.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                                │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Next.js 16 Frontend (shadcn/ui, React 19)                   │  │
│  │  Port 3000                                                    │  │
│  └─────────────────────────┬─────────────────────────────────────┘  │
│                            │ HTTP/SSE                               │
├────────────────────────────┼────────────────────────────────────────┤
│                     API LAYER (FastAPI)                             │
│  ┌────────────────────────┴─────────────────────────────────────┐  │
│  │  app/api/routes.py                                           │  │
│  │  POST /api/v1/query           GET  /api/v1/health            │  │
│  │  POST /api/v1/query/stream    GET  /api/v1/health/ready      │  │
│  │  POST /api/v1/ingest          GET  /api/v1/corpus/stats      │  │
│  └────────────────────────┬─────────────────────────────────────┘  │
│                           │                                         │
├───────────────────────────┼─────────────────────────────────────────┤
│                   SERVICE LAYER                                     │
│  ┌────────────────────────┴─────────────────────────────────────┐  │
│  │  QueryService  │  SSEStreamManager  │  Redis Cache           │  │
│  │  (orchestrator)│  (streaming events)│  (query result cache)   │  │
│  └────────────────────────┬─────────────────────────────────────┘  │
│                           │                                         │
├───────────────────────────┼─────────────────────────────────────────┤
│                    RAG / AGENT LAYER                                │
│  ┌────────────────────────┴─────────────────────────────────────┐  │
│  │  RAGPipeline (no agent)    │  LegalAgentGraph (LangGraph)     │  │
│  │  - retrieve → generate    │  - retrieve → analyze → risk     │  │
│  │  - streaming support      │    → refine (3x max) → finalize  │  │
│  └────────────────────────┬─────────────────────────────────────┘  │
│                           │                                         │
├───────────────────────────┼─────────────────────────────────────────┤
│                  RETRIEVAL PIPELINE                                 │
│  ┌────────────────────────┴─────────────────────────────────────┐  │
│  │  RetrievalEngine                                             │  │
│  │                                                              │  │
│  │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  │  │
│  │  │Metadata  │   │  BM25    │   │  Dense   │   │ Hybrid   │  │  │
│  │  │ Filter   │   │ (sparse) │   │ (dense)  │   │ Fusion   │  │  │
│  │  └──────────┘   └──────────┘   └──────────┘   └──────────┘  │  │
│  │                                                              │  │
│  │  ┌──────────────────────────────────────────────────────┐    │  │
│  │  │           Cross-Encoder Reranker (BGE)               │    │  │
│  │  └──────────────────────────────────────────────────────┘    │  │
│  └────────────────────────┬─────────────────────────────────────┘  │
│                           │                                         │
├───────────────────────────┼─────────────────────────────────────────┤
│                  INFRASTRUCTURE LAYER                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────┐ │
│  │  Qdrant    │  │  Redis     │  │  Ollama    │  │  External    │ │
│  │  (vector   │  │  (cache)   │  │  (local    │  │  LLM APIs    │ │
│  │   store)   │  │            │  │   LLM)     │  │  (Groq,etc)  │ │
│  │  :6333     │  │  :6379     │  │  :11434    │  │              │ │
│  └────────────┘  └────────────┘  └────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. API Layer (`app/api/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/query` | POST | Blocking RAG query |
| `/api/v1/query/stream` | POST | SSE streaming query |
| `/api/v1/ingest` | POST | Trigger document ingestion |
| `/api/v1/corpus/stats` | GET | Corpus statistics |
| `/api/v1/health` | GET | Liveness check |
| `/api/v1/health/ready` | GET | Readiness check |

Middleware:
- **CORS** — configured from `FRONTEND_ORIGINS` env var
- **CorrelationIDMiddleware** — injects `X-Correlation-ID` header for request tracing

### 2. Service Layer (`app/services/`)

- **`QueryService`** — orchestrates the query flow: checks Redis cache, routes to `RAGPipeline` or `LegalAgentGraph` based on `use_agent` flag, caches responses
- **`SSEStreamManager`** — wraps async generators into SSE protocol (`text/event-stream`) with typed events: `start`, `retrieval`, `analysis`, `risk`, `incentives`, `heartbeat`, `complete`, `error`
- **`Cache`** — async Redis client wrapper for query result caching (TTL: 1h)

### 3. RAG / Agent Layer

#### RAGPipeline (Standard)
- **Retrieve**: calls `RetrievalEngine.retrieve()`
- **Build context**: formats retrieved documents with metadata headers
- **Generate**: sends prompt to LLM via `LegalChain`
- **Streaming**: yields progressive SSE events with chunked text output

#### LegalAgentGraph (LangGraph Agent)
- State graph with 5 nodes: `retrieve` → `analyze` → (`risk_assess` | `refine`) → `finalize`
- **Refinement loop**: if insufficient context detected, the agent rephrases the query and retries (max 3 iterations)
- **Risk assessment**: structured risk analysis node executed after successful analysis

### 4. Retrieval Pipeline (`app/retrieval/`)

Multi-stage retrieval executed per query:

```
Query
  │
  ├── 1. MetadataFilter ─── infer subsector, enfoque, tipo_norma from query text
  │
  ├── 2. BM25 (Sparse) ─── executed in thread pool via asyncio.to_thread()
  │                        Tokenizes with jieba (Chinese segmenter for Spanish text)
  │                        Index persisted to cache/bm25_index.pkl
  │
  ├── 3. Dense (Vector) ─── Qdrant vector search with BGE-M3 embeddings (1024-d)
  │                        Cosine similarity
  │                        Optional metadata filtering (Qdrant payload index)
  │
  ├── 4. Hybrid Fusion ─── Score normalization (min-max) + weighted sum
  │                        Adaptive alpha: 0.7 for code queries, 0.3 for concept
  │
  ├── 5. Cross-Encoder ─── BAAI/bge-reranker-large (FlagEmbedding)
  │       Reranker          Fallback: cross-encoder/ms-marco-MiniLM-L-6-v2
  │
  └── 6. Top-K ────────── Returns final_k (configurable, default 5)
```

### 5. LLM Layer (`app/llm/`)

- **`LLMRouter`** — multi-provider with automatic fallback:
  1. **Groq** (primary) — Llama 3.3 70B via Groq API
  2. **Gemini** (fallback) — Gemini 2.0 Flash via Google Generative AI
- Providers configured via env variables; router tracks failed providers and skips them

### 6. Ingestion Pipeline (`ingestion/`)

```
Raw Text Files
  │
  ├── LegalDocumentParser ─── Regex-based article splitting
  │                           Per-norm-type patterns (Constitución, Ley, Decreto)
  │                           Article number extraction
  │
  ├── LegalTextNormalizer ─── Unicode normalization, whitespace cleanup
  │
  ├── Metadata Extractor ─── Per-article metadata inference
  │                           (tipo_norma, subsector, enfoque, risk_flags)
  │
  ├── QdrantStore.upsert ─── BGE-M3 embeddings computed in batch
  │                           Points upserted in batches of 32
  │                           UUID5 derived from unit ID for idempotency
  │
  └── JSON Export ────────── all_units.json saved to corpus/normalized/
```

**Corpus definitions** (defined in `ingestion/pipeline.py`):
| File | Type | ID |
|------|------|----|
| `constitucion_bolivia_articulos_seleccionados.txt` | Constitución | CPE |
| `ley_1604_1994.txt` | Ley | 1604 |
| `ley_943_modificaciones.txt` | Ley | 943 |
| `ds_5503_2025.txt` | Decreto Supremo | 5503 |

### 7. Core / Embeddings (`core/`)

- **Singleton embedder** (`BAAI/bge-m3`) — lazy-loaded, thread-safe via `get_embedder()`
- **ResourceManager** — async warmup of embedder and Qdrant in parallel at startup

### 8. Vector Store (`vectorstore/`)

- **QdrantStore** — synchronous wrapper around `qdrant-client`
  - Collection: `energymind` with 1024-d COSINE vectors
  - Payload indexes: `tipo_norma`, `norma_id`, `subsector`, `enfoque`, `sector`, `vigente`, `renewable_incentive`
  - Supports scroll_all for BM25 index bootstrapping
  - Batch upsert (32 per batch) with pre-computed embeddings

### 9. Data Models (`app/models/`)

- **`LegalUnit`** — Pydantic model for a single legal article with rich metadata
  - `id`, `tipo_norma`, `norma_id`, `articulo`, `tema`, `vigente`, `sector`, `subsector`, `enfoque`, `risk_flags`, `renewable_incentive`, `texto`, `created_at`
- **`QueryRequest`** — question, optional filters, top_k, use_agent flag
- **`QueryResponse`** — structured legal answer with risk matrix, citations, incentives
- **`StructuredLegalResponse`** — agent-specific structured output schema

### 10. Frontend (`frontend/`)

- **Next.js 16** with React 19, TypeScript
- **shadcn/ui** components (Radix primitives, Tailwind CSS v4)
- **lucide-react** icons, **recharts** for risk visualization
- **react-markdown** + **remark-gfm** for rendering legal text
- Dockerized, connects to API via `API_URL` env variable

---

## Data Flow: Query Lifecycle

```
1. Client → POST /api/v1/query {question: "...", subsector: "Solar"}
2. FastAPI routes → injects correlation ID → calls QueryService
3. QueryService → checks Redis cache (hash of question+filters)
4. Cache miss → RAGPipeline.query(request)
5.   → RetrievalEngine.retrieve(query, metadata_filter)
6.     → MetadataFilter.infer_from_query() (keyword-based subsector detection)
7.     → asyncio.gather(BM25 search, Dense search) — parallel
8.     → HybridRetriever._fusion() — normalize + weighted merge
9.     → Reranker.rerank() — cross-encoder refinement
10.  → ContextBuilder.build_context() — formatted LLM context
11.  → LegalChain.generate() → LLMRouter → Groq/Gemini
12.  → QueryResponse assembled with citations + risk matrix
13. QueryService → caches response in Redis (TTL 3600s)
14. QueryService returns QueryResponse → FastAPI → JSON to client
```

---

## Technology Stack

| Category | Technology | Version |
|----------|-----------|---------|
| **Runtime** | Python | >= 3.11 |
| **API Framework** | FastAPI | 0.115 |
| **RAG Framework** | LangChain + LangGraph | 0.3 / 0.2 |
| **Vector Store** | Qdrant | 1.13 |
| **Embeddings** | BAAI/bge-m3 | 1024-d |
| **Reranker** | BAAI/bge-reranker-large | — |
| **Sparse Retrieval** | rank-bm25 (BM25Okapi) | 0.2 |
| **Tokenization** | jieba (Chinese segmenter) | 0.42 |
| **LLM Providers** | Groq (Llama 3.3 70B), Gemini 2.0 Flash | — |
| **Cache** | Redis (async) | 7 |
| **Validation** | Pydantic v2 | 2.10 |
| **Frontend** | Next.js 16 + React 19 + shadcn/ui | — |
| **Infrastructure** | Docker Compose | — |
| **Testing** | pytest + pytest-asyncio | 8.3 |
| **Evaluation** | RAGAS | 0.2 |
| **Logging** | loguru + structlog | — |
| **Monitoring** | Prometheus client | — |

---

## Deployment

Docker Compose services:
| Service | Image | Port |
|---------|-------|------|
| `qdrant` | qdrant/qdrant:v1.13.2 | 6333 (REST), 6334 (gRPC) |
| `redis` | redis:7-alpine | 6379 |
| `lexenergy-api` | custom Dockerfile (multi-stage) | 8000 |
| `lexenergy-frontend` | custom Dockerfile | 3000 |

Storage volumes: `qdrant_storage`, `redis_data`

---

## Startup Sequence

1. FastAPI lifespan starts → `setup_logging()`
2. `_background_init()` launched as asyncio task:
   - `ResourceManager.warmup()` → loads BGE-M3 embedder + connects Qdrant (parallel)
   - `QueryService.initialize()` → inits RAGPipeline, LegalAgentGraph, Redis (parallel, 120s timeout)
   - Sets `app.state.ready = True`
3. During warmup, endpoints return 503 with "Service warming up"
4. Readiness endpoint (`/health/ready`) reflects warmup status

---

## Project Structure

```
lexenergy/
├── app/                    # FastAPI backend
│   ├── api/routes.py       # REST endpoints
│   ├── rag/                # RAG pipeline, chain, context builder
│   ├── retrieval/          # BM25, dense, hybrid, reranker, metadata filter
│   ├── agents/graph.py     # LangGraph state machine
│   ├── llm/                # Provider abstraction + router
│   ├── models/             # Pydantic schemas
│   ├── services/           # Query orchestration, SSE, cache
│   ├── prompts/            # Legal prompt templates
│   ├── config.py           # Pydantic Settings
│   └── main.py             # FastAPI app factory
├── core/                   # Embeddings singleton, resource manager
├── ingestion/              # Parsing, normalization, metadata extraction
├── vectorstore/            # Qdrant client wrapper
├── corpus/                 # Raw / processed / normalized legal texts
├── cache/                  # BM25 index persistence
├── frontend/               # Next.js 16 UI
├── tests/                  # Unit + integration + golden regression
├── evaluation/             # RAGAS evaluation script
└── docker/                 # Docker infrastructure
```
