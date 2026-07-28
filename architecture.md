# LexEnergy Bolivia — Architecture

## Overview

LexEnergy Bolivia is a **Legal RAG (Retrieval-Augmented Generation)** platform that answers legal questions about renewable energy investments in Bolivia. It ingests Bolivian legal texts, indexes them in a vector database, and generates structured legal analysis using an LLM.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js 16)                    │
│   Chat UI  ·  SSE Streaming  ·  Filter Panel  ·  Stats View   │
│                           :3000                                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP / SSE
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     API Layer (FastAPI)                          │
│   /query  ·  /query/stream  ·  /ingest  ·  /corpus/stats       │
│                           :8000                                  │
└──────────┬──────────────────────────────┬───────────────────────┘
           │                              │
           ▼                              ▼
┌──────────────────────┐   ┌──────────────────────────────────────┐
│    Query Service     │   │         Ingestion Pipeline           │
│  (orchestration)     │   │  parse → normalize → embed → upsert  │
└──────┬───────┬───────┘   └──────────────────────────────────────┘
       │       │
       ▼       ▼
┌────────────┐ ┌─────────────┐
│ RAG Pipeline│ │ Legal Agent │
│  (direct)   │ │ (LangGraph) │
└──────┬──────┘ └──────┬──────┘
       │               │
       ▼               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Retrieval Engine                               │
│                                                                  │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────┐ │
│  │ Metadata │  │  BM25    │  │  Dense   │  │    Reranker     │ │
│  │ Filter   │  │ (sparse) │  │ (cosine) │  │ (cross-encoder) │ │
│  └─────────┘  └──────────┘  └──────────┘  └─────────────────┘ │
│                                                                  │
│  Hybrid Fusion: α·BM25 + (1-α)·Dense  (adaptive α)             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Infrastructure                              │
│                                                                  │
│  ┌──────────┐  ┌───────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  Qdrant  │  │ Redis │  │  Ollama  │  │   BGE-M3 / BGE   │  │
│  │ vectors  │  │ cache │  │   LLM    │  │   reranker-large  │  │
│  │  :6333   │  │ :6379 │  │ :11434   │  │  (local models)   │  │
│  └──────────┘  └───────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Frontend (`frontend/`)

| Technology | Purpose |
|------------|---------|
| Next.js 16 | React framework with App Router |
| React 19 | UI library |
| shadcn/ui (Radix) | Component primitives |
| Tailwind CSS v4 | Styling |
| recharts | Corpus stats charts |
| react-markdown | LLM response rendering |

**Key files:**
- `src/app/page.tsx` — Chat interface entry
- `src/components/chat/chat-interface.tsx` — Main chat UI with SSE streaming
- `src/components/chat/message-bubble.tsx` — Message rendering (markdown, citations, risk matrix, incentives)
- `src/lib/api.ts` — Backend API client with SSE retry logic
- `src/lib/types.ts` — TypeScript type definitions

**API proxy:** `next.config.ts` rewrites `/api/v1/*` → `http://localhost:8000/api/v1/*`

### 2. API Layer (`app/api/routes.py`)

FastAPI router with endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/query` | Synchronous query → `QueryResponse` |
| `POST` | `/api/v1/query/stream` | SSE streaming query |
| `GET` | `/api/v1/health` | Liveness check |
| `GET` | `/api/v1/health/ready` | Readiness check |
| `POST` | `/api/v1/ingest` | Trigger document ingestion |
| `GET` | `/api/v1/corpus/stats` | Corpus statistics |

**Middleware:**
- CORS (configurable origins)
- Correlation ID (UUID-based, injected into logs)

### 3. Application Lifecycle (`app/main.py`)

```
FastAPI startup
    │
    ├── setup_logging()          # loguru config (JSON or human-readable)
    ├── ResourceManager()        # lightweight, no I/O yet
    ├── create_task(_background_init)  # non-blocking warmup
    │       │
    │       ├── rm.warmup()
    │       │     ├── asyncio.to_thread(load_embedder)   # BGE-M3
    │       │     └── asyncio.to_thread(load_qdrant)     # Qdrant client
    │       │
    │       ├── QueryService(rm).initialize()
    │       │     ├── RAGPipeline(qdrant).initialize()
    │       │     │     ├── RetrievalEngine(qdrant).initialize()
    │       │     │     │     ├── load BM25 index (or build from corpus)
    │       │     │     │     └── load reranker model
    │       │     │     └── LegalChain()  (LLM client)
    │       │     ├── LegalAgentGraph().initialize()
    │       │     │     └── RetrievalEngine().initialize()  ← creates separate Qdrant connection
    │       │     └── init_redis()  (optional, graceful failure)
    │       │
    │       └── app.state.ready = True
    │
    └── yield (serve requests)
            │
            └── shutdown: cancel warmup, close QueryService, close ResourceManager
```

### 4. Query Service (`app/services/query_service.py`)

Orchestrates the query lifecycle:
- Holds the `RAGPipeline` and `LegalAgentGraph` instances
- Manages Redis cache (SHA256 keys, 1h TTL)
- **Note:** Currently missing `process_query()` and `process_query_streaming()` methods (see report.md)

### 5. RAG Pipeline (`app/rag/pipeline.py`)

Direct query path (no agent refinement):

```
QueryRequest
    │
    ▼
RetrievalEngine.retrieve(query, metadata_filter, top_k)
    │
    ▼
ContextBuilder.build_context(documents)     ← formats legal articles for LLM
    │
    ▼
LegalChain.structured_answer(question, context)  ← LLM call
    │
    ▼
QueryResponse (RegulatoryAnalysis + RiskMatrix + IncentiveInfo)
```

### 6. Legal Agent (`app/agents/graph.py`)

LangGraph-based agent with iterative refinement:

```
retrieve → analyze → [check: insufficient_context?]
                          │                    │
                         YES                   NO
                          │                    │
                        refine ──→ retrieve    risk_assess → finalize
                          ↑         (loop)
                     iteration < 3
```

- Up to 3 refinement iterations
- Uses LLM to rephrase queries with Spanish legal terminology
- Separate `RetrievalEngine` instance (bug — should share connection)

### 7. Retrieval Engine (`app/retrieval/`)

The core retrieval pipeline:

```
User Query
    │
    ├──► MetadataFilter.infer_from_query()
    │       Extracts subsector, tipo_norma, enfoque, vigente from query text
    │
    ├──► BM25Retriever.search()               [sparse keyword match]
    │       jieba tokenization → BM25Okapi scoring
    │       CPU-bound work offloaded via asyncio.to_thread()
    │
    ├──► QdrantStore.search()                 [dense semantic search]
    │       BGE-M3 embedding → cosine similarity via Qdrant
    │
    ├──► HybridRetriever._fusion()            [score fusion]
    │       Adaptive α: 0.7 for code queries, 0.3 for conceptual
    │       Min-max normalized scores
    │
    └──► Reranker.rerank()                    [cross-encoder reranking]
            FlagEmbedding FlagReranker → CrossEncoder fallback
```

**Adaptive alpha logic:**
- `α = 0.7` (BM25-biased) when query matches code patterns: `artículo`, `ley N`, `decreto N`
- `α = 0.3` (dense-biased) when query matches conceptual patterns: `qué es`, `riesgo`, `definición`
- `α = 0.5` (balanced) otherwise

### 8. Vector Store (`vectorstore/qdrant_client.py`)

Qdrant wrapper providing:
- Collection management (auto-creates with 1024-dim cosine vectors)
- Payload indexes on: `tipo_norma`, `norma_id`, `subsector`, `enfoque`, `sector`, `vigente`, `renewable_incentive`
- Upsert (batched, 32 points/batch)
- Search with optional metadata filters
- Scroll (paginated full collection read)

### 9. Ingestion Pipeline (`ingestion/pipeline.py`)

```
CORPUS_DEFINITIONS (4 sources)
    │
    ▼
LegalDocumentParser.parse_file()
    ├── LegalTextNormalizer (normalize whitespace, unicode)
    ├── Article-level splitting (atomic legal units)
    └── Regex parsing (ideological markers)
    │
    ▼
LegalUnit objects → all_units.json
    │
    ▼
QdrantStore.upsert_units()
    ├── BGE-M3 batch embedding (1024 dims)
    └── PointStruct with full metadata payload
```

**Corpus sources:**

| File | Tipo Norma | ID | Content |
|------|------------|-----|---------|
| `constitucion_bolivia_articulos_seleccionados.txt` | Constitucion | CPE | Selected constitutional articles |
| `ley_1604_1994.txt` | Ley | 1604 | Electricity Law |
| `ley_943_modificaciones.txt` | Ley | 943 | Electricity Law modifications |
| `ds_5503_2025.txt` | Decreto Supremo | 5503 | Extraordinary Investment Regime |
| `aetn_resoluciones_muestra.txt` | Resolucion AETN | — | AETN resolutions (in config but not in CORPUS_DEFINITIONS) |

### 10. Models

**Embeddings:** `BAAI/bge-m3` (1024 dimensions)
- Loaded once as singleton via `core/embeddings.py`
- Supports 8192 token context

**Reranker:** `BAAI/bge-reranker-large`
- Fallback: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Lazy initialization, loaded on first use

**LLM:** `llama3.1` via Ollama (default) or `gpt-4o` via OpenAI

---

## Data Flow

### Query Flow

```
1. User types question in ChatInterface
2. Frontend sends POST /api/v1/query/stream
3. SSE events flow back:
   { type: "start",          correlation_id }
   { type: "retrieval",      count, filter_used }
   { type: "analysis",       regulatory_analysis (markdown) }
   { type: "citations",      legal_citations[] }
   { type: "risk_matrix",    risk_matrix }
   { type: "incentives",     incentives_detected }
   { type: "complete",       processing_time_ms }
4. Frontend renders progressive updates in the chat bubble
```

### Ingestion Flow

```
1. POST /api/v1/ingest (or CLI: python -m ingestion.pipeline)
2. Parse raw .txt files → LegalUnit objects
3. Apply metadata overrides from CORPUS_DEFINITIONS
4. Save normalized units to corpus/normalized/all_units.json
5. Batch embed with BGE-M3 (normalize=True)
6. Upsert to Qdrant (batch_size=32)
7. BM25 index built from Qdrant scroll (cached to cache/bm25_index.pkl)
```

---

## Configuration

All configuration is loaded from `.env` via `pydantic-settings` in `app/config.py`:

| Category | Key Variables | Defaults |
|----------|---------------|----------|
| Qdrant | `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION` | `localhost:6333`, `lexenergy_bolivia` |
| Embeddings | `EMBEDDINGS_MODEL`, `EMBEDDINGS_DIMENSIONS` | `BAAI/bge-m3`, `1024` |
| Reranker | `RERANKER_MODEL`, `RERANKER_DEVICE` | `BAAI/bge-reranker-large`, `cpu` |
| LLM | `LLM_MODEL`, `LLM_PROVIDER`, `OLLAMA_BASE_URL` | `llama3.1`, `ollama`, `localhost:11434` |
| API | `API_HOST`, `API_PORT`, `API_WORKERS` | `0.0.0.0`, `8000`, `4` |
| Redis | `REDIS_HOST`, `REDIS_PORT` | `localhost:6379` |
| Retrieval | `TOP_K`, `BM25_TOP_K`, `DENSE_TOP_K`, `FINAL_TOP_K`, `HYBRID_ALPHA` | `10`, `20`, `20`, `5`, `0.5` |

---

## Docker Infrastructure

`docker/docker-compose.yml` defines 4 services:

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| `qdrant` | `qdrant/qdrant:v1.13.2` | 6333, 6334 | Vector database |
| `redis` | `redis:7-alpine` | 6379 | Query cache |
| `api` | Custom (python:3.11-slim) | 8000 | FastAPI backend |
| `frontend` | Custom (node:22-alpine) | 3000 | Next.js frontend |

---

## Project Structure

```
EnergyMind/
├── app/                          # Backend application
│   ├── main.py                   # FastAPI lifespan, middleware
│   ├── config.py                 # Pydantic Settings
│   ├── api/routes.py             # API endpoints
│   ├── models/                   # Pydantic schemas + LegalUnit
│   ├── prompts/                  # Spanish legal LLM prompts
│   ├── rag/                      # RAG pipeline + LLM chain
│   ├── retrieval/                # BM25, Dense, Hybrid, Reranker, MetadataFilter
│   ├── services/                 # QueryService, cache, SSE, ingestion
│   └── agents/                   # LangGraph refinement agent
├── core/                         # Shared singletons
│   ├── embeddings.py             # BGE-M3 singleton
│   └── runtime/resource_manager.py  # Startup lifecycle
├── vectorstore/                  # Qdrant client wrapper
├── ingestion/                    # Document parsing + indexing
│   ├── pipeline.py               # IngestionPipeline + CORPUS_DEFINITIONS
│   ├── parsing/                  # Legal document parsers
│   ├── normalization/            # Text normalization
│   ├── metadata/                 # Risk flag extraction
│   ├── lexivox/                  # LexiVox web scraper
│   └── aetn/                     # AETN resolutions scraper
├── corpus/                       # Legal document corpus
│   ├── raw/                      # Source .txt files
│   └── normalized/               # Parsed JSON output
├── tests/                        # Test suite
├── evaluation/                   # RAGAS evaluation
├── docker/                       # Docker Compose + Dockerfiles
├── frontend/                     # Next.js 16 + React 19 + shadcn/ui
├── requirements.txt              # Python dependencies (98 packages)
├── pyproject.toml                # Project metadata
└── .env                          # Environment configuration
```
