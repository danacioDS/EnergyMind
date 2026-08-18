<<<<<<< HEAD
# EnergyMind Bolivia
=======
# EnergyMind
>>>>>>> 5a946e2 (feat: EnergyMind v1.0 demo-ready)

A specialized **Legal RAG (Retrieval-Augmented Generation) platform** for analyzing Bolivian legislation related to renewable energy investment. Combines **FastAPI**, **LangChain/LangGraph**, **Qdrant**, and **hybrid retrieval (BM25 + dense embeddings + cross-encoder reranking)** to deliver structured legal reasoning over national regulatory frameworks.

---

## Architecture

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

See [architecture.md](architecture.md) for full details.

---

## Retrieval Pipeline

Multi-stage retrieval executed per query:

1. **Metadata Filtering** — filters by subsector, norm type, validity before search
2. **BM25 + Dense (parallel)** — sparse keyword search over the full corpus runs concurrently with Qdrant vector search via `asyncio.gather()`. BM25 index is pre-built from all Qdrant documents at startup.
3. **Hybrid Fusion** — score normalization + weighted fusion with adaptive alpha (0.7 for code vs 0.3 for concept queries)
4. **Cross-Encoder Reranking** — BAAI/bge-reranker-large refines the top candidates
5. **Context Building** — retrieved articles formatted into LLM-ready context with metadata headers

All CPU-bound BM25 operations are offloaded to a thread pool via `asyncio.to_thread()` to avoid blocking the event loop.

---

## Legal Corpus

| Document | Type |
|----------|------|
| Constitution of Bolivia (2009) — selected articles | CPE |
| Ley de Electricidad N° 1604 (1994) | Law |
| Ley N° 943 (amendments) | Law |
| DS N° 5503 (2025) — Investment Regime | Decree |
| AETN administrative resolutions | Resolutions |

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for local development)
- Ollama (local LLM) or API keys for Groq/Gemini

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

### Agent mode

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Compare solar vs wind investment risks", "use_agent": true}'
```

### Other endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ingest` | Trigger ingestion |
| GET | `/api/v1/corpus/stats` | Corpus statistics |
| GET | `/api/v1/health` | Liveness |
| GET | `/api/v1/health/ready` | Readiness |

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

---

## Project Structure

```
energymind/
├── app/                    # FastAPI backend
│   ├── api/                # REST routes (blocking + SSE)
│   ├── rag/                # RAG pipeline, context builder, LLM chain
│   ├── retrieval/          # BM25, dense, hybrid fusion, reranker
│   ├── agents/             # LangGraph agent with refinement loop
│   ├── prompts/            # Legal prompt templates (Spanish)
│   ├── models/             # Pydantic request/response schemas
│   ├── services/           # QueryService, SSE manager, Redis cache
│   ├── llm/                # LLM provider router (Groq → Gemini)
│   ├── config.py           # Pydantic Settings (env-based)
│   └── main.py             # FastAPI app, CORS, lifespan
├── core/                   # Singleton embeddings (BGE-M3) + ResourceManager
├── ingestion/              # Scrapers (LexiVox, AETN) + parsing + normalization
├── vectorstore/            # Qdrant client wrapper
├── corpus/                 # Raw + normalized legal dataset
├── cache/                  # BM25 index persistence
├── frontend/               # Next.js 16 + shadcn/ui chat UI
├── tests/                  # Unit, integration, golden regression tests
├── evaluation/             # RAGAS evaluation
└── docker/                 # Dockerfile + docker-compose.yml
```

---

## Tests

```bash
pytest                    # All tests
pytest -v                 # Verbose
pytest tests/test_retrieval_golden.py  # Golden regression
```

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
