# EnergyMind — Architecture Document

**Version**: 1.0.0

---

## 1. System Overview

EnergyMind is a Legal RAG (Retrieval-Augmented Generation) platform built on a **layered, async-first architecture**. Queries flow through a multi-stage retrieval pipeline, optional agentic refinement, and structured LLM generation — all exposed via a FastAPI server with a Next.js frontend.

```
┌──────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 16)                      │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────────┐   │
│  │Chat      │  │Filter        │  │Risk      │  │Legal        │   │
│  │Interface │  │Panel         │  │Matrix    │  │Citations    │   │
│  └──────────┘  └──────────────┘  └──────────┘  └─────────────┘   │
│         │              │              │              │            │
│         └──────────────┴──────┬───────┴──────────────┘            │
│                               │ API client (fetch + SSE)          │
└───────────────────────────────┼──────────────────────────────────┘
                                │ HTTP / SSE
┌───────────────────────────────┼──────────────────────────────────┐
│                     BACKEND (FastAPI)                             │
│  ┌────────────────────────────┼────────────────────────────┐      │
│  │                    API Layer                              │      │
│  │  POST /query  POST /query/stream  GET /health  ...       │      │
│  └────────────────────────────┬────────────────────────────┘      │
│                               │                                    │
│  ┌────────────────────────────▼────────────────────────────┐      │
│  │                    QueryService                           │      │
│  │  • Cache check (Redis, SHA256 key, 1h TTL)              │      │
│  │  • Route to RAGPipeline or LegalAgentGraph               │      │
│  │  • SSE streaming orchestration                           │      │
│  └────────────────────────────┬────────────────────────────┘      │
│                               │                                    │
│           ┌───────────────────┼───────────────────┐                │
│           │                   │                   │                │
│  ┌────────▼────────┐  ┌──────▼──────┐  ┌─────────▼──────────┐     │
│  │   RAGPipeline    │  │ LegalChain  │  │  LegalAgentGraph    │     │
│  │  (no agent)      │  │ (LLM wrap)  │  │  (LangGraph,       │     │
│  │                  │  │            │  │   up to 3 iters)    │     │
│  └────────┬─────────┘  └──────┬──────┘  └─────────┬──────────┘     │
│           │                   │                   │                │
│           └───────────────────┼───────────────────┘                │
│                               │                                    │
│  ┌────────────────────────────▼────────────────────────────┐      │
│  │                  RetrievalEngine                         │      │
│  │  • BM25 index load (from pickle cache or Qdrant scroll) │      │
│  │  • Parallel BM25 + Dense search via asyncio.gather()    │      │
│  │  • Hybrid fusion with adaptive alpha                     │      │
│  │  • Cross-encoder reranking                               │      │
│  └───────────┬──────────────────────────┬──────────────────┘      │
│              │                          │                           │
│     ┌────────▼────────┐       ┌─────────▼─────────┐               │
│     │   BM25Retriever  │       │  DenseRetriever    │               │
│     │  (sparse, full   │       │  (Qdrant, dense)   │               │
│     │   corpus, CPU)   │       │                    │               │
│     └────────┬─────────┘       └─────────┬──────────┘               │
│              │                          │                           │
│              └──────────┬───────────────┘                           │
│                         │                                           │
│                ┌────────▼────────┐                                  │
│                │ HybridRetriever  │                                  │
│                │ (fusion + alpha) │                                  │
│                └────────┬────────┘                                  │
│                         │                                           │
│                ┌────────▼────────┐                                  │
│                │   Reranker       │                                  │
│                │ (cross-encoder)  │                                  │
│                └────────┬────────┘                                  │
│                         │                                           │
│                ┌────────▼────────┐                                  │
│                │  ContextBuilder  │                                  │
│                │ (format → LLM)   │                                  │
│                └─────────────────┘                                  │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                    ResourceManager                          │    │
│  │  • Warmup: load BGE-M3 embedder + connect Qdrant           │    │
│  │  • Background startup (API ready before warmup complete)   │    │
│  │  • Singleton accessors                                      │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌───────────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ QdrantStore       │  │ Redis Cache  │  │ LLMRouter            │  │
│  │ (vector DB)       │  │ (optional)   │  │ Groq → Gemini        │  │
│  └───────────────────┘  └──────────────┘  └─────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer Architecture

### 2.1 API Layer (`app/api/`)

FastAPI application with CORS middleware, correlation ID middleware, and structured logging via loguru. All endpoints are async.

**Lifespan**: On startup, `ResourceManager` warmup is kicked off as a background task. The API returns `200` on `/health` immediately, but `503` on `/health/ready` until warmup completes.

### 2.2 Service Layer (`app/services/`)

**QueryService** is the central orchestrator:
1. Accepts `QueryRequest` (question, subsector, filters, use_agent flag)
2. Generates SHA256 cache key, checks Redis
3. On miss: instantiates `RAGPipeline` (or `LegalAgentGraph` if `use_agent=true`)
4. Returns `QueryResponse` (blocking) or async generator (SSE)

**SSEStreamManager** formats events as SSE protocol with proper `event:` and `data:` fields, including heartbeats and error handling.

### 2.3 Retrieval Layer (`app/retrieval/`)

#### 2.3.1 MetadataFilter
Heuristic keyword matching to infer Qdrant `must` filters:
- `subsector`: Solar, Wind, Biomass, Hydro, Geothermal, General
- `enfoque`: Generation, Transmission, Distribution, Commercialization
- `tipo_norma`: Constitution, Law, Decree, Resolution
- `renewable_incentive`: boolean
- `vigente`: boolean

#### 2.3.2 BM25Retriever
- Uses `BM25Okapi` from `rank_bm25`
- Tokenization via `jieba` for Spanish
- Index built on startup from all Qdrant documents (via `scroll_all`)
- Persisted to `cache/bm25_index.pkl`
- `search()` runs in thread pool via `asyncio.to_thread()`

#### 2.3.3 DenseRetriever
- Uses shared BGE-M3 embedding model (1024-dim)
- Encodes query, searches Qdrant via `qdrant_client.search()`
- Returns top-k results with scores

#### 2.3.4 HybridRetriever
- Normalizes BM25 and dense scores to [0,1]
- Weighted fusion: `score = α * dense + (1-α) * bm25`
- Adaptive α: 0.7 for code/quota queries, 0.3 for conceptual, 0.5 default
- Takes top-k after fusion for reranking

#### 2.3.5 Reranker
- Lazy-loaded on first use
- Tries `FlagReranker` (BAAI/bge-reranker-large) first
- Falls back to `CrossEncoder` (ms-marco-MiniLM)
- Reranks top candidates and returns final ranked results

### 2.4 RAG Layer (`app/rag/`)

#### 2.4.1 RAGPipeline
- Orchestrates: retrieval → context building → LLM generation
- `query()` returns `StructuredLegalResponse`
- `query_stream()` yields progressive SSE events

#### 2.4.2 ContextBuilder
- Formats each retrieved document with metadata header:
  ```
  [Tipo: Ley | Artículo: 2 | Subsector: General | Riesgos: Private Investment]
  ```
- Extracts `LegalCitation` objects (norma, articulo, texto excerpt)
- Prepares the LLM prompt with constitutional hierarchy instructions

#### 2.4.3 LegalChain
- Wraps `LLMRouter` for LLM invocation
- Detects input language (Spanish/English/Portuguese) via keyword heuristics
- Sets appropriate system prompt based on language

### 2.5 Agent Layer (`app/agents/`)

**LegalAgentGraph** (LangGraph):
- 5 nodes in a `StateGraph`:
  1. `retrieve` — runs the retrieval engine
  2. `analyze` — generates legal analysis
  3. `risk_assess` — assesses risk matrix
  4. `finalize` — produces final structured output
  5. `refine` — (conditional) rephrases query if insufficient context
- Conditional edge: if insufficient context and iterations < 3, loop back to `retrieve`
- Uses `LLMRouter` for all LLM calls within nodes

### 2.6 Ingestion Layer (`ingestion/`)

Processes raw legal text → `LegalUnit` → Qdrant index.

**Pipeline stages**:
1. **Scraping**: `AETNScraper` (Bolivian energy regulator), `LexivoxScraper` (legal database) — async HTTP/Playwright scrapers
2. **Parsing**: `LegalDocumentParser` splits by article boundaries (regex per norm type); `RegexLegalParser` extracts structural patterns
3. **Normalization**: `LegalTextNormalizer` cleans whitespace, removes headers/footers/page numbers, normalizes article references
4. **Metadata Extraction**: Identifies risk flags (7 categories), subsector, enfoque, norm type, renewable incentive indicators
5. **Indexing**: `IngestionPipeline` batches `LegalUnit` objects and upserts to Qdrant via `QdrantStore`

### 2.7 LLM Layer (`app/llm/`)

**LLMRouter**:
- Maintains ordered list of providers: `[GroqLLM, GeminiLLM]`
- Tracks consecutive failures per provider
- On failure, moves to next provider; if all fail, raises exception

**GroqLLM**: Llama 3.3 70B via Groq API (low-latency inference)
**GeminiLLM**: Gemini 2.0 Flash via Google AI API (fallback)

### 2.8 Core Layer (`core/`)

**Embeddings** (`core/embeddings.py`):
- Singleton `get_embedder()` returns BGE-M3 model
- Shared across `DenseRetriever` and `QdrantStore`
- Async warmup function loads model in executor

**ResourceManager** (`core/runtime/resource_manager.py`):
- Background warmup: loads embedder + connects to Qdrant concurrently
- `is_ready()` flag for readiness check
- Singleton access via class methods

### 2.9 Vector Store (`vectorstore/`)

**QdrantStore**:
- Connects to Qdrant cloud or local instance
- Creates collection named `legal_units` with:
  - 1024-dim vectors (cosine distance)
  - Payload indexes on: `tipo_norma`, `subsector`, `enfoque`, `risk_flags`, `vigente`, `renewable_incentive`
- Upserts in batches of 32
- Scroll all for BM25 index building
- Search with metadata filter support

---

## 3. Data Models

### 3.1 LegalUnit
```python
{
  "id": "Ley_1604_art_2",
  "tipo_norma": "Ley",
  "norma_id": "Ley N° 1604",
  "articulo": "2",
  "texto": "...",
  "subsector": "Electricidad",
  "enfoque": "Generation",
  "risk_flags": ["Private Investment"],
  "renewable_incentive": True,
  "vigente": True,
  "ideological_framework": "Mixed",
  "norma": "Ley N° 1604",
  "metadata": {...}
}
```

### 3.2 QueryResponse (StructuredLegalResponse)
```python
{
  "direct_conclusion": "...",
  "regulatory_analysis": "...",
  "legal_citations": [{"norma": "...", "articulo": "...", ...}],
  "risk_matrix": {
    "ideological_framework": "Mixed",
    "constitutional_conflict_risk": "Medium",
    "nationalization_risk": "Medium-High",
    "regulatory_instability": "High",
    "legal_ambiguity": "Medium",
    "arbitration_protection": "Limited"
  },
  "incentives_detected": {"detected": True, "type": "...", ...},
  "insufficient_context": False
}
```

---

## 4. Request Flow (Detailed)

### Blocking Query
```
1. POST /api/v1/query {question, subsector, filters, use_agent}
2. QueryService.query()
3.   Check Redis cache (SHA256(question + filters))
4.   Cache HIT → return cached QueryResponse immediately
5.   Cache MISS:
6.     If use_agent:
7.       LegalAgentGraph.invoke()
8.     Else:
9.       RAGPipeline.query()
10.      RetrievalEngine.search(query, filters)
11.        MetadataFilter.infer(query) → Qdrant must_filters
12.        bm25_task = asyncio.to_thread(BM25Retriever.search, query)
13.        dense_task = DenseRetriever.search(query, filters)
14.        bm25_results, dense_results = await asyncio.gather(bm25_task, dense_task)
15.        HybridRetriever.fuse(bm25_results, dense_results, adaptive_alpha)
16.        Reranker.rerank(fused_results)
17.      ContextBuilder.build_context(reranked_results)
18.      LegalChain.invoke(context + query) → StructuredLegalResponse
19.   Cache the response
20.   Return QueryResponse
```

### Streaming Query
```
1. POST /api/v1/query/stream {question, filters}
2. QueryService.query_stream() → async generator
3.   yield SSE start event
4.   yield SSE retrieval event (status)
5.   yield SSE analysis event (direct_conclusion)
6.   yield SSE risk event (risk_matrix)
7.   yield SSE incentives event (incentives_detected)
8.   yield SSE complete event (processing_time_ms, sources)
9.   On error: yield SSE error event
10.  Heartbeats sent every N seconds during LLM inference
```

---

## 5. Startup Sequence

```
1. FastAPI app created
2. Lifespan handler starts
3.   ResourceManager.warmup() scheduled as background task:
4.     Task 1: get_embedder() → loads BGE-M3 (in executor)
5.     Task 2: QdrantStore.connect() → verifies connection
6.   await asyncio.gather(task1, task2)
7.   BM25 index loaded (from pickle or built from Qdrant scroll)
8.   Set is_ready = True
9. API starts accepting requests immediately
10. /health returns 200
11. /health/ready returns 503 until is_ready
```

---

## 6. Configuration

All configuration via environment variables loaded in `app/config.py` using Pydantic Settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_URL` | — | Qdrant endpoint |
| `QDRANT_API_KEY` | — | Qdrant API key |
| `GROQ_API_KEY` | — | Groq API key |
| `GEMINI_API_KEY` | — | Google AI API key |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `RETRIEVAL_TOP_K` | `20` | Initial retrieval count |
| `RERANKER_TOP_K` | `10` | After reranking count |
| `LLM_PROVIDER` | `groq` | Default LLM provider |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding model name |

---

## 7. Containers (Docker Compose)

```yaml
services:
  qdrant:       # Vector DB, port 6333
  redis:        # Cache, port 6379
  lexenergy-api:# FastAPI backend, port 8000
  lexenergy-    # Next.js frontend, port 3000
  frontend:
```

Network: internal bridge. Frontend proxies `/api/*` to backend via Next.js rewrites.

---

## 8. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Legal-first chunking** | Legal documents are naturally structured by articles; naive text splitting would destroy semantic boundaries |
| **Hybrid retrieval** | BM25 captures exact legal terminology (article numbers, norm IDs); dense captures semantic similarity; together they outperform either alone |
| **Thread-pooled BM25** | BM25 scoring is CPU-bound; running it synchronously would block the async event loop |
| **Lazy reranker** | Cross-encoders are memory-heavy (~2GB); loading on first use avoids wasting resources when reranking isn't needed |
| **Singleton embeddings** | BGE-M3 is ~1.5GB in memory; loading multiple copies would be wasteful |
| **SSE streaming** | LLM inference takes 3-15 seconds; streaming gives users progressive feedback and improves perceived responsiveness |
| **LLM provider fallback** | Ensures availability if one provider is down or rate-limited |
| **Graceful degradation** | Each component (Redis, BM25, reranker) has a fallback so the system remains functional even if parts are unavailable |
| **Constitutional hierarchy** | Bolivian law has a strict hierarchy (CPE Art. 410); prompts enforce this to ensure correct legal reasoning |
