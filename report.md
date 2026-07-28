# EnergyMind (LexEnergy Bolivia) — Repository Analysis Report

**Date**: July 2026
**Author**: Automated analysis
**Version**: 1.0.0

---

## 1. Overview

EnergyMind (LexEnergy Bolivia) is a specialized **Legal RAG (Retrieval-Augmented Generation) platform** that answers legal questions about renewable energy investments in Bolivia. It combines a FastAPI async backend, hybrid retrieval (BM25 + dense embeddings + cross-encoder reranking), LLM orchestration via LangChain/LangGraph, and a Next.js 16 chat frontend.

**Target users**: Lawyers, consultants, and investors analyzing Bolivian energy regulation.

**Languages supported**: Spanish (primary), English, Portuguese.

---

## 2. Tech Stack

| Layer | Technology |
|-------|-----------|
| **API Framework** | FastAPI (Python 3.11+, async) |
| **LLM Orchestration** | LangChain + LangGraph |
| **Vector Database** | Qdrant (self-hosted or cloud) |
| **Cache** | Redis (async) |
| **Frontend** | Next.js 16 / React 19 / shadcn-ui / Tailwind CSS v4 |
| **LLM Providers** | Groq (Llama 3.3 70B), Gemini 2.0 Flash |
| **Embeddings** | BGE-M3 (SentenceTransformers) |
| **Reranker** | BAAI/bge-reranker-large |
| **Sparse Retrieval** | BM25Okapi via rank-bm25 |
| **Containerization** | Docker + Docker Compose |
| **Evaluation** | RAGAS |
| **Testing** | pytest + pytest-asyncio |
| **Linting** | ruff, mypy |

---

## 3. Repository Structure

```
EnergyMind/
├── app/                    # FastAPI backend
│   ├── api/                # REST routes (blocking + SSE)
│   ├── rag/                # RAG pipeline, context builder, LLM chain
│   ├── retrieval/          # BM25, dense, hybrid fusion, reranker
│   ├── agents/             # LangGraph refinement loop
│   ├── prompts/            # Legal system prompts (Spanish)
│   ├── models/             # Pydantic schemas
│   ├── services/           # QueryService, SSE, cache, embeddings
│   ├── llm/                # LLM provider router + implementations
│   ├── config.py           # Pydantic Settings
│   └── main.py             # App entry point
├── core/                   # Singleton embeddings + resource manager
├── ingestion/              # Scrapers + parsing + normalization
│   ├── parsing/            # Legal & regex parsers
│   ├── normalization/      # Text normalizer
│   ├── metadata/           # Metadata extraction
│   ├── aetn/               # AETN regulator scraper
│   └── lexivox/            # LexiVox legal database scraper
├── vectorstore/            # Qdrant client wrapper
├── corpus/                 # Raw + normalized legal texts
├── cache/                  # BM25 index persistence
├── tests/                  # Unit + integration + golden tests
├── evaluation/             # RAGAS evaluation scripts
├── frontend/               # Next.js 16 chat UI
│   └── src/
│       ├── app/            # Next.js pages
│       ├── lib/            # API client, types, utils
│       └── components/     # Chat, analysis, layout, UI primitives
└── docker/                 # Dockerfile + docker-compose
```

---

## 4. Key Components

### 4.1 Retrieval System (`app/retrieval/`)

Multi-stage hybrid retrieval pipeline:

1. **MetadataFilter** — infers Qdrant `must` filters from query keywords (subsector, enfoque, tipo_norma, renewable_incentive, vigente)
2. **BM25Retriever** — sparse keyword search over full corpus via `BM25Okapi`, persisted to disk via pickle, CPU-bound work offloaded to thread pool
3. **DenseRetriever** — semantic search via Qdrant using BGE-M3 embeddings (1024-dim vectors)
4. **HybridRetriever** — score normalization + weighted fusion with adaptive alpha (0.7 for code queries, 0.3 for conceptual, 0.5 default)
5. **Reranker** — lazy-loaded cross-encoder (FlagReranker → CrossEncoder fallback)

### 4.2 RAG Pipeline (`app/rag/`)

- **RAGPipeline** — orchestrates retrieval → context building → LLM generation
- **LegalChain** — wraps LLMRouter, includes language detection heuristic
- **ContextBuilder** — formats retrieved docs with metadata headers, extracts citations

### 4.3 Agent System (`app/agents/`)

- **LegalAgentGraph** — LangGraph `StateGraph` with 5 nodes: retrieve → analyze → risk_assess → finalize, with conditional refinement loop (up to 3 iterations)

### 4.4 LLM Router (`app/llm/`)

- **LLMRouter** — multi-provider fallback: Groq → Gemini, tracks failures, auto-retry
- **GroqLLM** — Llama 3.3 70B via Groq API
- **GeminiLLM** — Gemini 2.0 Flash via Google AI API

### 4.5 Ingestion (`ingestion/`)

- **IngestionPipeline** — processes 5 source documents into LegalUnits, indexes to Qdrant
- **LegalDocumentParser** — splits by article boundaries per norm type
- **RegexLegalParser** — regex patterns for Bolivian law references
- **LegalTextNormalizer** — text cleaning, whitespace/header/footer removal
- **Metadata Extractor** — risk flags (7 categories), subsector, enfoque, etc.
- **AETNScraper / LexivoxScraper** — async web scrapers

### 4.6 Frontend (`frontend/`)

- **ChatInterface** — main chat UI with streaming updates and filter sidebar
- **MessageBubble** — user/assistant message display with loading skeleton
- **FilterPanel** — subsector, norm type, agent mode toggles
- **RiskMatrix** — visual risk matrix (6 categories with color coding)
- **LegalCitations** — citations display panel
- **IncentivesPanel** — renewable incentive detection display
- **Corpus Stats Dashboard** — recharts bar charts (`/stats`)

---

## 5. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/query` | Blocking RAG query |
| POST | `/api/v1/query/stream` | Streaming SSE query |
| GET | `/api/v1/health` | Liveness check |
| GET | `/api/v1/health/ready` | Readiness check |
| POST | `/api/v1/ingest` | Trigger ingestion |
| GET | `/api/v1/corpus/stats` | Corpus statistics |

---

## 6. Data Flow

```
User Query → FastAPI → QueryService → [Cache hit? Return cached]
                                     → [Cache miss]
                                       → RAGPipeline or LegalAgentGraph
                                         → RetrievalEngine
                                           → MetadataFilter
                                           → BM25 (parallel) + Qdrant Dense (parallel)
                                           → Hybrid Fusion
                                           → Cross-Encoder Reranker
                                         → ContextBuilder
                                         → LLM (Groq → Gemini fallback)
                                       → StructuredLegalResponse
```

---

## 7. Legal Corpus

| Document | Type | Coverage |
|----------|------|----------|
| Constitution of Bolivia (2009) | CPE | Selected articles |
| Ley de Electricidad N° 1604 (1994) | Law | Full |
| Ley N° 943 (amendments) | Law | Full |
| DS N° 5503 (2025) — Investment Regime | Decree | Full |
| AETN administrative resolutions | Resolutions | Scraped samples |

---

## 8. Testing

- **Unit tests**: `tests/test_ingestion.py`, `tests/test_retrieval.py`
- **API tests**: `tests/test_api.py`
- **Startup tests**: `tests/test_startup.py` (warmup + 503 smoke)
- **Golden regression**: `tests/test_retrieval_golden.py` (10 Spanish queries)
- **Evaluation**: `evaluation/run_ragas_eval.py` (RAGAS metrics)
- **Manual scripts**: `test_qdrant.py`, `test_pipeline.py`, `test_search.py`
- **Config**: pytest with `asyncio_mode=auto`, testpaths=`tests/`

---

## 9. Key Architectural Decisions

1. **Legal-first chunking** — articles as atomic units, not naive text splitting
2. **Metadata-first retrieval** — filter before vector search reduces noise
3. **Hybrid retrieval** — BM25 (sparse) + dense embeddings in parallel, fused with adaptive alpha
4. **Thread-pooled BM25** — CPU-bound scoring offloaded via `asyncio.to_thread`
5. **Lazy reranker** — cross-encoder loaded on first use with automatic fallback
6. **Singleton embeddings** — BGE-M3 loaded once, shared across components
7. **SSE streaming** — progressive event emission (retrieval → analysis → risk → incentives → complete)
8. **Provider fallback** — LLMRouter tries Groq → Gemini on failure
9. **Graceful degradation** — Redis, BM25, reranker all have fallback paths
10. **Constitutional hierarchy** — CPE Art. 410 priority enforced in prompts

---

## 10. Dependencies

**Backend**: ~49 Python packages including fastapi, langchain, langgraph, qdrant-client, sentence-transformers, rank-bm25, unstructured, httpx, loguru, redis, celery, prometheus-client.

**Frontend**: 17 npm packages including next 16, react 19, @radix-ui primitives, recharts, tailwindcss v4, lucide-react.

---

## 11. Strengths

- Well-structured, modular async codebase with clear separation of concerns
- Comprehensive multi-stage retrieval with fallbacks at every level
- Legal-domain-aware chunking and metadata extraction
- SSO streaming with progressive disclosure of results
- Dual LLM provider support with automatic failover
- Optional LangGraph agent for iterative query refinement
- Full Docker Compose setup for one-command deployment
- Includes golden test suite and RAGAS evaluation

## 12. Areas for Improvement

- No CI/CD pipeline configured
- No Terraform or cloud deployment scripts
- Limited test coverage for the frontend
- No load testing or performance benchmarking
- Reranker may be slow on CPU; could benefit from ONNX quantization
- No authentication/authorization layer
- Monitoring via Prometheus metrics but no dashboards
- No migration system for Qdrant collection schema changes

---

## 13. Conclusion

EnergyMind is a production-ready Legal RAG platform with a sophisticated hybrid retrieval system, multi-LLM provider support, and a polished chat UI. The architecture is async-first, modular, and designed for graceful degradation. It is well-suited for deployment in legal-tech environments where structured analysis of regulatory frameworks is required.
