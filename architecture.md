# LexEnergy Bolivia — Architecture

## Overview

LexEnergy Bolivia is a **Legal RAG (Retrieval-Augmented Generation)** platform that answers questions about Bolivian renewable energy regulation. Users submit legal questions (Spanish/English) and receive structured answers with citations, risk analysis, and incentive detection.

---

## System Context

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Browser   │────▶│  Next.js 16  │────▶│  FastAPI    │
│ (React 19)  │◀────│  (Port 3000) │◀────│  (Port 8000)│
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                    ┌───────────────────────────┼───────────┐
                    │                           │           │
                    ▼                           ▼           ▼
              ┌──────────┐              ┌──────────┐  ┌───────┐
              │  Qdrant  │              │  Redis   │  │Ollama │
              │(VectorDB)│              │ (Cache)  │  │/OpenAI│
              └──────────┘              └──────────┘  └───────┘
```

---

## Backend Architecture

### Entry Points (defined in `pyproject.toml`)

| Command | File | Purpose |
|---------|------|---------|
| `lexenergy-api` | `app/main.py:start` | Starts FastAPI/uvicorn server |
| `lexenergy-ingest` | `ingestion.pipeline:run_ingestion` | Runs document indexing |

### API Routes (`app/api/routes.py`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/query` | Blocking legal RAG query |
| POST | `/api/v1/query/stream` | Streaming SSE query |
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/ingest` | Trigger ingestion |
| GET | `/api/v1/corpus/stats` | Corpus statistics |

### Request Flow

```
POST /api/v1/query
        │
        ▼
QueryService.process_query()
        │
        ├── use_agent=false ────► RAGPipeline.query()
        │                              │
        │                              ├── RetrievalEngine.retrieve()
        │                              │     ├── MetadataFilter (infer filters from query text)
        │                              │     ├── BM25 (sparse, thread-pooled via asyncio.to_thread)
        │                              │     ├── Qdrant (dense vector search, BGE-M3 embeddings)
        │                              │     ├── Hybrid Fusion (adaptive alpha: 0.7/0.3)
        │                              │     └── Cross-Encoder Reranker (BGE-reranker-large)
        │                              │
        │                              ├── ContextBuilder.build_context()
        │                              │     └── Format docs → LLM context with metadata headers
        │                              │
        │                              └── LegalChain.structured_answer()
        │                                    └── LLM → StructuredLegalResponse
        │                                          ├── direct_conclusion
        │                                          ├── regulatory_analysis
        │                                          ├── risk_matrix
        │                                          ├── incentives_detected
        │                                          └── insufficient_context
        │
        └── use_agent=true ────► LegalAgentGraph.run()
                                      └── LangGraph state machine
                                            retrieve → analyze → [check_refinement]
                                              │                        │
                                              │   sufficient ─────────┤
                                              │                        │
                                              │   insufficient ───────┘
                                              │      (refine → retrieve, up to 3 iterations)
                                              │
                                              └── risk_assess → finalize
```

### SSE Streaming Flow (`POST /api/v1/query/stream`)

```
SSE Events (progressive):
  start       →  { correlation_id }
  retrieval_complete  →  { doc_count }
  analysis    →  { direct_conclusion }
  risk        →  { risk_matrix }
  incentives  →  { incentive_info }
  citations   →  { citations }
  complete    →  { response }
  error       →  { detail, stage }
```

---

## Directory Layout

```
app/                          # Backend application
├── main.py                   # FastAPI app, lifespan, middleware
├── config.py                 # Pydantic Settings (env-based)
├── api/routes.py             # API endpoints
├── models/
│   ├── schemas.py            # Pydantic request/response models
│   └── legal_unit.py         # LegalUnit data model
├── prompts/legal_prompts.py  # Spanish legal system prompts
├── rag/
│   ├── pipeline.py           # RAGPipeline orchestrator
│   ├── chain.py              # LegalChain (LLM calls, structured output)
│   └── context_builder.py    # Format retrieved docs → LLM context
├── retrieval/
│   ├── engine.py             # RetrievalEngine (orchestrates all retrievers)
│   ├── bm25.py               # BM25Retriever (sparse, jieba tokenization)
│   ├── dense.py              # DenseRetriever (cosine similarity, BGE-M3)
│   ├── hybrid.py             # HybridRetriever (score fusion, adaptive alpha)
│   ├── reranker.py           # Reranker (BGE-reranker-large)
│   └── metadata_filter.py    # Infer Qdrant filters from query text
├── services/
│   ├── query_service.py      # QueryService (lifecycle, orchestration)
│   ├── cache.py              # Redis-backed cache (SHA256 key, 1h TTL)
│   ├── sse_manager.py        # SSE event formatting
│   └── embedding_service.py
├── agents/
│   └── graph.py              # LangGraph agent with refinement loop

core/
└── embeddings.py             # Singleton SentenceTransformer (BGE-M3)

vectorstore/
└── qdrant_client.py          # QdrantStore (collection mgmt, upsert, search)

ingestion/                    # Document ingestion pipeline
├── pipeline.py               # IngestionPipeline
├── parsing/legal_parser.py   # LegalDocumentParser
├── parsing/regex_parser.py   # Regex-based article parser
├── normalization/normalizer.py
├── metadata/extractor.py
├── lexivox/scraper.py        # LexiVox corpus scraper
└── aetn/scraper.py           # AETN resolutions scraper

corpus/                       # Legal dataset
├── raw/                      # Raw .txt files
├── processed/
└── normalized/all_units.json # Processed corpus

frontend/                     # Next.js 16 / React 19
└── src/
    ├── app/page.tsx          # ChatInterface
    ├── components/
    │   ├── chat/             # ChatInterface, MessageBubble
    │   ├── analysis/         # LegalCitations, IncentivesPanel, RiskMatrix
    │   ├── layout/           # Header, FilterPanel
    │   └── ui/               # shadcn/ui primitives
    └── lib/
        ├── api.ts            # Backend API client
        ├── types.ts          # TypeScript types
        └── utils.ts          # cn() utility

docker/
├── docker-compose.yml        # Qdrant + Redis + API + Frontend
└── Dockerfile                # Backend image

tests/
├── test_api.py
├── test_ingestion.py
├── test_retrieval.py
├── test_retrieval_golden.py
└── test_search.py

evaluation/
└── run_ragas_eval.py
```

---

## Retrieval Pipeline (in detail)

```
                    ┌──────────────────┐
                    │   User Query     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ MetadataFilter   │  ← Infer subsector, risk flags,
                    │ infer_from_query │     renewable intent from query
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                              ▼
    ┌─────────────────┐           ┌───────────────────┐
    │  BM25Retriever  │           │  QdrantStore      │
    │  (sparse, CPU)  │           │  (dense, GPU CPU)  │
    │  jieba tokenize │           │  BGE-M3 embedding  │
    │  asyncio thread │           │  cosine similarity │
    └────────┬────────┘           └─────────┬─────────┘
              │                              │
              └──────────┬───────────────────┘
                         ▼
              ┌──────────────────┐
              │  HybridRetriever │  ← Adaptive alpha fusion
              │  score fusion    │     (0.7 BM25 for codes,
              │                  │      0.3 dense for concepts)
              └────────┬─────────┘
                         │
                         ▼
              ┌──────────────────┐
              │    Reranker      │  ← BGE-reranker-large
              │  cross-encoder   │     (re-rank top-k)
              └────────┬─────────┘
                         │
                         ▼
              ┌──────────────────┐
              │   Top-K docs     │  → LLM context
              └──────────────────┘
```

**Metadata filter inference** (`app/retrieval/metadata_filter.py`):
- Keywords like `"solar"` → `subsector=Solar`
- `"incentivo"`, `"beneficio"` → `renewable_incentive=True`
- `"riesgo"`, `"nacionalización"` → risk flag filters
- `"DS 5503"` → `norma_id=5503`

**Adaptive hybrid alpha** (`app/retrieval/hybrid.py`):
- `α = 0.7` for exact legal code queries (BM25-biased)
- `α = 0.3` for conceptual questions (dense-biased)

---

## Agentic Refinement Loop

```
                     ┌──────────┐
                     │ retrieve │
                     └────┬─────┘
                          │
                          ▼
                     ┌──────────┐
              ┌─────│ analyze  │─────┐
              │     └────┬─────┘     │
              │          │           │
              ▼          │           ▼
        ┌────────┐      │     ┌──────────┐
        │ refine │◀─────┘     │risk_assess│
        │(rephrase│           └────┬──────┘
        │ query)  │                │
        └────┬────┘                ▼
             │              ┌──────────┐
             └─────────────▶│ finalize │
                            └──────────┘
```

- Maximum 3 refinement iterations
- Refinement rephrases query using Spanish legal terminology
- `_check_refinement` routes to `risk_assess` or `refine` based on `insufficient_context`

---

## LLM Integration

Two providers via `LegalChain._init_llm()`:

| Provider | Class | Config |
|----------|-------|--------|
| Ollama (local) | `ChatOllama` | `llama3.1`, temperature=0.1, `num_predict=4096` |
| OpenAI | `ChatOpenAI` | `gpt-4o`, temperature=0.1 |

**Chains**:
- `qa_chain` → `StrOutputParser` (free-text answer)
- `risk_chain` → `StrOutputParser` (risk analysis)
- `structured_chain` → `with_structured_output(StructuredLegalResponse)` (JSON mode for Ollama, tool calling for OpenAI)

---

## Legal Corpus

| Source | Type | Norm ID | Flags |
|--------|------|---------|-------|
| Constitución Política del Estado | Constitución | CPE | Constitutional Hierarchy |
| Ley de Electricidad No. 1604/1994 | Ley | 1604 | Market Framework |
| Ley No. 943 (modificaciones) | Ley | 943 | — |
| DS No. 5503/2025 | Decreto Supremo | 5503 | Regulatory Instability, Nationalization Risk |

Each legal document is parsed into **articles** as atomic units. Articles carry metadata: `tipo_norma`, `norma_id`, `articulo`, `subsector`, `enfoque`, `risk_flags`, `renewable_incentive`, `vigente`.

---

## Data Models

```
QueryRequest
├── question: str
├── subsector: Optional[str]
├── tipo_norma: Optional[str]
├── vigente: Optional[bool]
├── top_k: Optional[int] (default 5)
└── use_agent: Optional[bool] (default false)

StructuredLegalResponse (LLM output)
├── direct_conclusion: str
├── regulatory_analysis: str
├── risk_matrix: RiskMatrix
│   ├── ideological_framework
│   ├── constitutional_conflict_risk
│   ├── nationalization_risk
│   ├── regulatory_instability
│   ├── legal_ambiguity
│   └── arbitration_protection
├── incentives_detected: IncentiveInfo
│   ├── detected: bool
│   ├── type: Optional[str]
│   ├── articles: list[str]
│   └── description: Optional[str]
└── insufficient_context: bool

QueryResponse
├── question: str
├── answer: RegulatoryAnalysis
│   ├── direct_conclusion
│   ├── regulatory_analysis
│   ├── legal_citations: list[LegalCitation]
│   ├── risk_matrix
│   ├── incentives_detected
│   └── insufficient_context
├── sources: list[str]
├── processing_time_ms: Optional[int]
└── cached: bool
```

---

## Caching

- **Backend**: Redis (optional, graceful degradation)
- **Key**: SHA256 of `question + subsector + tipo_norma + use_agent`
- **TTL**: 1 hour
- **Init**: `QueryService.initialize()` with 15s timeout — cache disabled if Redis unavailable

---

## Frontend

- **Next.js 16** + **React 19** + **TypeScript 5**
- **shadcn/ui** (Radix primitives) + **Tailwind CSS v4**
- API calls via `frontend/src/lib/api.ts`
- Next.js rewrites proxy `/api/*` to FastAPI backend
- Components: `ChatInterface`, `MessageBubble`, `LegalCitations`, `RiskMatrix`, `IncentivesPanel`, `FilterPanel`

---

## Infrastructure

```
docker-compose.yml
├── qdrant (v1.13.2, ports 6333/6334)
├── redis (7-alpine, port 6379)
├── lexenergy-api (FastAPI, port 8000)
└── lexenergy-frontend (Next.js, port 3000)
```

Key env vars: `QDRANT_HOST`, `QDRANT_PORT`, `REDIS_HOST`, `REDIS_PORT`, `OLLAMA_BASE_URL`, `LLM_PROVIDER`, `LLM_MODEL`.

---

## Key Design Decisions

1. **Article-level chunking** — No naive text splitting. Articles are the atomic legal unit, preserving structure and enabling precise citations.
2. **Singleton embedding model** (`core/embeddings.py`) — BGE-M3 loaded once, shared across QdrantStore and DenseRetriever.
3. **Thread-pooled BM25** — CPU-bound scoring offloaded via `asyncio.to_thread` to avoid blocking the event loop.
4. **Lazy reranker init** — Cross-encoder loaded on first use (not construction), with automatic fallback from FlagReranker to CrossEncoder.
5. **Adaptive hybrid fusion** — Alpha weight between BM25 and dense dynamically adjusted per query type.
6. **Metadata-first retrieval** — Filters inferred from query before vector search, narrowing the search space.
7. **Optional LangGraph agent** — Refinement loop rephrases queries up to 3 iterations when results are insufficient.
8. **Graceful degradation** — Redis cache, BM25 index, and reranker all have fallback paths if unavailable.
