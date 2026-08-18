<<<<<<< HEAD
# EnergyMind Bolivia
=======
# EnergyMind
>>>>>>> 5a946e2 (feat: EnergyMind v1.0 demo-ready)

**EnergyMind** is a domain-specific RAG system for Bolivian energy regulation. It combines semantic retrieval with Qdrant and lexical retrieval with BM25, processes legal documents at article level, and uses a multi-provider LLM architecture for resilient generation. The system returns traceable sources and, importantly, can abstain when the retrieved evidence doesn't support an answer.

The main challenge was making heterogeneous legal documents reliably retrievable at article level while preserving provenance and avoiding hallucinations. This was solved by combining dense and lexical retrieval, structured legal metadata, and an LLM layer constrained by retrieved evidence.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                                  │
│                                                                      │
│   ┌────────────────────────────────────────────────────────────────┐ │
│   │  Frontend · Next.js 16 + React 19 + shadcn/ui + Tailwind v4   │ │
│   │  Chat interface with structured legal analysis panels          │ │
│   │  SSE streaming client with retries and backoff                 │ │
│   └───────────────────────────┬────────────────────────────────────┘ │
│                               │ HTTP + SSE                           │
├───────────────────────────────┼───────────────────────────────────────┤
│                         API LAYER · FastAPI :8000                      │
│  ┌───────────────────────────┴─────────────────────────────────────┐ │
│  │  POST /query          Blocking legal query                      │ │
│  │  POST /query/stream   Streaming SSE response                    │ │
│  │  POST /ingest         Trigger document ingestion                │ │
│  │  GET  /corpus/stats   Corpus statistics                         │ │
│  │  GET  /health         Liveness + readiness probes               │ │
│  │  Middleware: CORS + CorrelationID (X-Correlation-ID)            │ │
│  └───────────────────────────┬─────────────────────────────────────┘ │
│                               │                                       │
├───────────────────────────────┼───────────────────────────────────────┤
│                      SERVICE LAYER                                     │
│  ┌───────────────────────────┴─────────────────────────────────────┐ │
│  │  QueryService ── orchestrates cache → pipeline → cache          │ │
│  │  Redis Cache ── response dedup (TTL 1h)                         │ │
│  │  SSE Manager ── event framing for streaming                     │ │
│  └───────────────────────────┬─────────────────────────────────────┘ │
│                               │                                       │
├───────────────────────────────┼───────────────────────────────────────┤
│                       RAG LAYER                                        │
│  ┌───────────────────────────┴─────────────────────────────────────┐ │
│  │                                                                 │ │
│  │  RAGPipeline                    LegalAgentGraph (LangGraph)      │ │
│  │  ┌─────────────────────┐       ┌──────────────────────────┐     │ │
│  │  │ 1. Retrieve          │       │ retrieve → analyze       │     │ │
│  │  │ 2. Build Context     │       │   → refine (loop ×3)     │     │ │
│  │  │ 3. Generate (LLM)    │       │   → risk_assess          │     │ │
│  │  │ 4. Assemble Response │       │   → finalize             │     │ │
│  │  │                      │       │ ⚠ Incomplete             │     │ │
│  │  │ Abstains when        │       └──────────────────────────┘     │ │
│  │  │ evidence is weak     │                                       │ │
│  │  └─────────────────────┘                                       │ │
│  └───────────────────────────┬─────────────────────────────────────┘ │
│                               │                                       │
├───────────────────────────────┼───────────────────────────────────────┤
│                    RETRIEVAL ENGINE                                     │
│  ┌───────────────────────────┴─────────────────────────────────────┐ │
│  │                                                                 │ │
│  │  ┌─────────────┐  ┌─────────────┐                               │ │
│  │  │  BM25        │  │  Dense       │  ← parallel via gather()    │ │
│  │  │  (lexical)   │  │  (Qdrant)   │                               │ │
│  │  │  Spanish     │  │  MiniLM-L6   │                               │ │
│  │  │  legal token │  │  384-d COSINE│                               │ │
│  │  └──────┬──────┘  └──────┬──────┘                               │ │
│  │         └────────┬───────┘                                       │ │
│  │                  ▼                                               │ │
│  │         ┌────────────────┐                                       │ │
│  │         │  Hybrid Fusion  │  α = 0.7 (code) / 0.3 (concept)     │ │
│  │         │  min-max norm   │                                      │ │
│  │         └────────┬───────┘                                       │ │
│  │                  ▼                                               │ │
│  │         ┌────────────────┐                                       │ │
│  │         │  Reranker       │  cross-encoder (disabled for         │ │
│  │         │  (optional)     │  memory constraints)                 │ │
│  │         └────────┬───────┘                                       │ │
│  │                  ▼                                               │ │
│  │            Top-K (10 → 5)                                        │ │
│  └───────────────────────────┬─────────────────────────────────────┘ │
│                               │                                       │
├───────────────────────────────┼───────────────────────────────────────┤
│                       LLM LAYER · Multi-Provider                      │
│  ┌───────────────────────────┴─────────────────────────────────────┐ │
│  │                                                                 │ │
│  │   LLMRouter ── fallback chain with health tracking:             │ │
│  │                                                                 │ │
│  │   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │ │
│  │   │  Groq     │───▶│ Cloudflare│───▶│  Gemini   │───▶│ Ollama   │ │ │
│  │   │  Llama    │    │  Llama    │    │  Flash    │    │  Local   │ │ │
│  │   │  3.3 70B  │    │  3.1 8B   │    │  2.5      │    │  Llama   │ │ │
│  │   └──────────┘    └──────────┘    └──────────┘    └──────────┘ │ │
│  │                                                                 │ │
│  │   Provider fails → blacklisted → next provider tried             │ │
│  │   Success → blacklist reset                                      │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                    INFRASTRUCTURE                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │  Qdrant     │  │  Redis      │  │  Embeddings │  │  Legal Corpus  │ │
│  │  Vector DB  │  │  Cache      │  │  MiniLM-L6  │  │  45 articles   │ │
│  │  :6333 REST │  │  :6379      │  │  384-d CPU  │  │  5 document    │ │
│  │  :6334 gRPC │  │             │  │             │  │  types         │ │
│  └────────────┘  └────────────┘  └────────────┘  └────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

See [architecture.md](architecture.md) for full component details.

---

## Retrieval Pipeline

Multi-stage retrieval executed per query:

1. **Metadata Filtering** — infers filters from query keywords (e.g., "solar" → subsector Solar, "ley 1604" → norma_id). Always enforces `vigente: True`.
2. **BM25 + Dense (parallel)** — lexical keyword search with a custom Spanish legal tokenizer runs concurrently with Qdrant vector search via `asyncio.gather()`. The BM25 index is pre-built from all Qdrant documents at startup and persisted to disk.
3. **Hybrid Fusion** — min-max score normalization + weighted fusion with adaptive alpha: **0.7** for legal code queries (specific norm references), **0.3** for conceptual queries, **0.5** default.
4. **Reranking** — cross-encoder refinement of top candidates (currently disabled for memory constraints).
5. **Context Building** — top articles formatted into LLM-ready context with metadata headers, capped at 5 documents.

All CPU-bound BM25 operations are offloaded to a thread pool via `asyncio.to_thread()` to avoid blocking the event loop.

---

## Legal Corpus

| Document | Type | Units |
|----------|------|-------|
| Constitution of Bolivia (2009) — selected articles | CPE | 9 |
| Ley de Electricidad N° 1604 (1994) | Law | 18 |
| Ley N° 943 (amendments to 1604) | Law | 8 |
| DS N° 5503 (2025) — Renewable Investment Regime | Decree | 10 |
| AETN administrative resolutions | Resolutions | — |

**Total indexed units:** 45 legal articles with structured metadata (risk flags, subsector, enfoque, norm type, validity status).

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for local development)
- Ollama (local LLM) or API keys for Groq/Gemini/Cloudflare

### Full Stack (Docker)

```bash
docker compose -f docker/docker-compose.yml up -d
curl http://localhost:8000/api/v1/health
```

| Service | Port |
|---------|------|
| Frontend (Next.js 16) | 3000 |
| API (FastAPI) | 8000 |
| Qdrant (vector DB) | 6333 |
| Redis (cache) | 6379 |

### Local Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
docker compose -f docker/docker-compose.yml up -d qdrant redis
cp .env.example .env
uvicorn app.main:app --reload
```

---

## API

### Query (blocking)

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Can a foreign company build a solar plant in Bolivia?", "subsector": "Solar"}'
```

### Query (streaming SSE)

```bash
curl -N -X POST http://localhost:8000/api/v1/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "What incentives exist under DS 5503?", "subsector": "Solar"}'
```

SSE events: `start` → `retrieval` → `analysis` → `risk` → `incentives` → `heartbeat` → `insufficient_context` → `complete` → `error`

### Other Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ingest` | Trigger document ingestion |
| GET | `/api/v1/corpus/stats` | Corpus statistics |
| GET | `/api/v1/health` | Liveness probe |
| GET | `/api/v1/health/ready` | Readiness probe |

---

## Response Format

```json
{
  "question": "...",
  "answer": {
    "direct_conclusion": "2-3 sentence answer citing specific articles",
    "regulatory_analysis": "Detailed 3-5 paragraph analysis",
    "legal_citations": [
      {
        "norma": "Ley 1604",
        "articulo": "2",
        "texto": "...",
        "tipo_norma": "Ley",
        "risk_flags": ["Private Investment"]
      }
    ],
    "risk_matrix": {
      "ideological_framework": "Mixed",
      "constitutional_conflict_risk": "Medium",
      "nationalization_risk": "Medium-High",
      "regulatory_instability": "High",
      "legal_ambiguity": "Medium",
      "arbitration_protection": "Limited"
    },
    "incentives_detected": {
      "detected": true,
      "type": "Tax Incentives",
      "articles": [],
      "description": "Custom duty exemptions and accelerated depreciation"
    },
    "insufficient_context": false
  },
  "sources": ["Ley_1604_art_2_0", "DS_5503_art_3_0"],
  "processing_time_ms": 1234,
  "cached": false
}
```

The `insufficient_context` field enables **abstention**: when the retrieved evidence is insufficient to answer the query confidently, the system signals this rather than fabricating an answer.

---

## Project Structure

```
energymind/
├── app/                    # FastAPI backend
│   ├── api/                # REST routes (blocking + SSE)
│   ├── rag/                # RAG pipeline, context builder, LLM chain
│   ├── retrieval/          # BM25, dense, hybrid fusion, reranker, metadata filter
│   ├── agents/             # LangGraph agent with refinement loop
│   ├── prompts/            # Legal prompt templates (Spanish)
│   ├── models/             # Pydantic request/response schemas
│   ├── services/           # QueryService, SSE manager, Redis cache
│   ├── llm/                # LLM provider router (Groq → Cloudflare → Gemini → Ollama)
│   ├── config.py           # Pydantic Settings (env-based)
│   └── main.py             # FastAPI app, CORS, lifespan
├── core/                   # Singleton embeddings + ResourceManager
├── ingestion/              # Scrapers (LexiVox, AETN) + parsing + normalization
├── vectorstore/            # Qdrant client wrapper
├── corpus/                 # Raw + normalized legal dataset (45 units)
├── cache/                  # BM25 index persistence
├── frontend/               # Next.js 16 + shadcn/ui chat UI
├── tests/                  # Unit, integration, golden regression tests
├── evaluation/             # RAGAS evaluation script
└── docker/                 # Dockerfile + docker-compose.yml
```

---

## Tests

```bash
pytest                    # All tests
pytest -v                 # Verbose
pytest tests/test_retrieval_golden.py  # Golden regression (10 queries)
```

---

## Technology Stack

| Category | Technology |
|----------|-----------|
| Runtime | Python 3.11.9 |
| API | FastAPI 0.115 + uvicorn |
| RAG | LangChain 0.2 / LangGraph 0.2 |
| Vector Store | Qdrant 1.13 (384-d, COSINE) |
| Embeddings | `all-MiniLM-L6-v2` (384-d, CPU) |
| Sparse Retrieval | BM25Okapi + custom Spanish legal tokenizer |
| LLM | Groq (Llama 3.3 70B) → Gemini (2.5 Flash) → Ollama (local) |
| Cache | Redis 7 (async) |
| Frontend | Next.js 16, React 19, shadcn/ui, Tailwind v4 |
| Infra | Docker Compose, multi-stage Dockerfile |

---

## Legal Risk Categories

- Constitutional Conflict Risk
- Nationalization Risk
- Regulatory Instability
- Legal Ambiguity
- Arbitration Protection Level
- Renewable Incentive Detection
- Private Investment Exposure

---

## License

MIT
