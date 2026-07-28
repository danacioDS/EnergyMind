# 📘 LexEnergy Bolivia

LexEnergy Bolivia is a specialized **Legal RAG (Retrieval-Augmented Generation) platform** that analyzes Bolivian legislation related to renewable energy investment. It combines **FastAPI, LangChain/LangGraph, Qdrant, and hybrid retrieval (BM25 + dense embeddings + cross-encoder reranking)** to deliver structured legal reasoning over national regulatory frameworks.

---

## 🧠 Architecture

```
                        ┌─────────────┐
                        │  FastAPI     │
                        │  API Layer   │
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │ QueryService │
                        │  + Redis     │
                        │  + SSE       │
                        └──────┬──────┘
                               │
                    ┌──────────┼──────────┐
                    │          │          │
            ┌───────▼──────┐  │  ┌───────▼────────┐
            │ RAGPipeline   │  │  │ LangGraph      │
            │ (no agent)    │  │  │ Agent          │
            └───────┬──────┘  │  └────────────────┘
                    │         │
            ┌───────▼──────┐  │
            │ Retrieval    │  │
            │ Engine       │  │
            └───────┬──────┘  │
                    │         │
         ┌──────────┼──────────┘
         │          │
    ┌────▼────┐ ┌───▼────┐
    │  BM25   │ │ Qdrant │
    │ (full   │ │ (dense)│
    │ corpus) │ └───┬────┘
    └────┬────┘     │
         └────┬─────┘
              ▼
        ┌──────────┐
        │Reranker  │
        │(BGE-cross)│
        └──────────┘
```

---

## 🔎 Retrieval Pipeline

Multi-stage retrieval executed per query:

1. **Metadata Filtering** — filters by subsector, norm type, validity before search
2. **BM25 + Dense (parallel)** — sparse keyword search over the full corpus runs concurrently with Qdrant vector search via `asyncio.gather()`. BM25 index is pre-built from all Qdrant documents at startup.
3. **Hybrid Fusion** — score normalization + weighted fusion with adaptive alpha (code vs concept queries)
4. **Cross-Encoder Reranking** — BAAI/bge-reranker-large refines the top candidates
5. **Context Building** — retrieved articles formatted into LLM-ready context with metadata headers

All CPU-bound BM25 operations (`get_scores`, `BM25Okapi`) are offloaded to a thread pool via `asyncio.to_thread()` to avoid blocking the event loop.

---

## ⚖️ Legal Corpus Coverage

- 🇧🇴 Constitution of Bolivia (2009) — selected articles
- ⚡ Ley de Electricidad N° 1604 (1994)
- 📜 Ley N° 943 (amendments)
- 🏗️ DS N° 5503 (2025) — Investment Regime
- 🏛️ AETN administrative resolutions (scraped)

---

## 🚀 Setup

### Prerequisites

- Docker + Docker Compose (for Full Stack mode)
- Python 3.11+ (for local development)
- Ollama (local LLM) or OpenAI API key

---

### 🐳 Full Stack (Docker) — End-to-end in 2 commands

```bash
# 1. Start everything (Qdrant + Redis + API + Frontend)
docker compose -f docker/docker-compose.yml up -d

# 2. Verify — API health
curl http://localhost:8000/api/v1/health
```

Services:

| Service | Port | URL |
|---------|------|-----|
| **Frontend** (Next.js 16) | 3000 | http://localhost:3000 |
| **API** (FastAPI) | 8000 | http://localhost:8000/docs |
| **Qdrant** (vector DB) | 6333 | — |
| **Redis** (cache) | 6379 | — |

After startup:
- **UI** → http://localhost:3000 (ChatInterface ready)
- **API docs** → http://localhost:8000/docs
- **Corpus is pre-ingested** → `POST /api/v1/query` responds immediately

---

### ⚡ Quick Start (Local)

```bash
# Clone repository
cd energy_lex

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start Qdrant + Redis
docker compose -f docker/docker-compose.yml up -d qdrant redis

# Configure environment
cp .env.example .env

# Pull local LLM
ollama pull llama3.1
ollama serve

# Ingest legal corpus
python -c "import asyncio; from ingestion.pipeline import run_ingestion; asyncio.run(run_ingestion())"

# Run API
uvicorn app.main:app --reload
```

---

## 📡 API Usage

### Query (blocking)

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can a foreign company build a solar plant in Bolivia?",
    "subsector": "Solar"
  }'
```

### Query (streaming SSE)

```bash
curl -N -X POST http://localhost:8000/api/v1/query/stream \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What incentives exist under DS 5503?",
    "subsector": "Solar"
  }'
```

SSE events are emitted progressively as each stage completes, with proper SSE `id`, `event`, and `data` fields. The `X-Accel-Buffering: no` header is set for nginx compatibility.

### Agent mode (LangGraph refinement loop)

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Compare solar vs wind investment risks",
    "use_agent": true
  }'
```

### Trigger ingestion

```bash
curl -X POST http://localhost:8000/api/v1/ingest
```

### Corpus statistics

```bash
curl http://localhost:8000/api/v1/corpus/stats
```

### Health check

```bash
curl http://localhost:8000/api/v1/health
```

---

## 📤 Response Format

### Blocking response

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

### SSE stream events

| Event | Payload | When |
|---|---|---|---|
| `start` | `{correlation_id}` | Connection established |
| `retrieval` | `{status}` | Documents fetched |
| `analysis` | `{direct_conclusion}` | LLM direct conclusion |
| `risk` | `{matrix}` | Risk matrix available |
| `incentives` | `{detected}` | Incentive info available |
| `heartbeat` | — | Keep-alive ping |
| `insufficient_context` | — | Corpus lacks sufficient info |
| `complete` | `{processing_time_ms, sources}` | Response finished |
| `error` | `{detail, stage}` | Error occurred |

---

## 📁 Project Structure

```
lexenergy/
├── app/
│   ├── api/              # FastAPI routes (blocking + SSE)
│   ├── rag/              # RAG pipeline, context builder, LLM chain
│   ├── retrieval/        # BM25, dense, hybrid fusion, reranker
│   ├── agents/           # LangGraph agent with refinement loop
│   ├── prompts/          # Legal prompt templates (Spanish)
│   ├── models/           # Pydantic request/response schemas
│   ├── services/         # QueryService, SSE manager, Redis cache
│   ├── config.py         # Pydantic Settings (env-based)
│   └── main.py           # FastAPI app, CORS, lifespan
│
├── core/                 # Singleton embeddings (BGE-M3)
├── ingestion/            # Scrapers (LexiVox, AETN) + normalization pipeline
├── corpus/               # Raw/normalized legal dataset
├── cache/                # BM25 index persistence
├── vectorstore/          # Qdrant client wrapper
├── frontend/             # Next.js 16 + shadcn/ui
├── tests/
└── docker/
```

---

## 🧩 Key Design Decisions

- **Legal-first chunking** — articles as atomic units (no naive text splitting)
- **Metadata-first retrieval** — filter before vector search reduces noise
- **Constitutional hierarchy** — CPE Art. 410 priority enforced in prompts
- **Hybrid retrieval** — BM25 (full corpus) + Qdrant dense in parallel, fused with adaptive alpha
- **Thread-pooled BM25** — CPU-bound scoring offloaded via `asyncio.to_thread` to avoid blocking the event loop
- **Lazy reranker init** — Cross-encoder loaded on first use (not construction), with automatic fallback from FlagReranker to CrossEncoder
- **Structured legal output** — conclusions, risk matrix, incentives, and citations always enforced via Pydantic schema
- **Singleton embedding model** — BGE-M3 loaded once and shared across QdrantStore and DenseRetriever
- **SSE streaming** — progressive event emission (retrieval → LLM stages → complete) instead of batch
- **Query caching** — Redis-backed SHA256 keyed cache with 1h TTL
- **Agentic refinement** — optional LangGraph agent rephrases queries up to 3 iterations when results are insufficient
- **Graceful degradation** — Redis cache, BM25 index, and reranker all have fallback paths if unavailable

---

## ⚠️ Legal Risk Categories

- Constitutional Conflict
- Nationalization Risk
- Regulatory Instability
- Legal Ambiguity
- Arbitration Protection Level
- Renewable Incentive Detection
- Private Investment Exposure

---

## 📜 License

MIT


# Crear entorno virtual
python3 -m venv venv

# Activar entorno virtual
source venv/bin/activate

# Verificar que está activo
which python
# → Debe mostrar: /home/daniel/repo_lab/EnergyMind/venv/bin/python