# LexEnergy Bolivia

A specialized Legal RAG (Retrieval-Augmented Generation) platform for analyzing Bolivian legislation related to renewable energy investments. Built with FastAPI, LangChain, Qdrant, and LLM orchestration.

## Architecture

```
                    ┌─────────────┐
                    │  FastAPI     │
                    │  (API Layer) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ QueryService │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ RAGPipeline  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼─────┐ ┌───▼────┐ ┌────▼─────┐
       │  Retrieval │ │Prompt  │ │  LangGraph│
       │  Engine    │ │Engine  │ │  Agent    │
       └──────┬─────┘ └────────┘ └──────────┘
              │
    ┌─────────┼─────────┐
    │         │         │
┌───▼───┐ ┌──▼───┐ ┌───▼───┐
│BM25   │ │Dense │ │Reranker│
│Retriever│ │Retr. │ │(BGE)  │
└───────┘ └──────┘ └───────┘
    │         │         │
    └─────────┼─────────┘
              │
       ┌──────▼──────┐
       │   Qdrant    │
       │  (Vector DB)│
       └─────────────┘
```

## Retrieval Pipeline

1. **Metadata Filtering** - Filter by subsector, norm type, validity BEFORE vector search
2. **BM25 Retrieval** - Sparse keyword matching
3. **Dense Retrieval** - BAAI/bge-m3 embeddings
4. **Hybrid Fusion** - Score normalization and fusion
5. **Reranking** - BAAI/bge-reranker-large
6. **Context Builder** - Build structured legal context
7. **LLM Response** - Llama 3.1 or Mistral Nemo with legal prompts

## Legal Corpus Scope

- Constitution of Bolivia (2009) - selected articles
- Ley de Electricidad N° 1604 (1994)
- Ley N° 943 modifications
- DS N° 5503 (2025) - Extraordinary Investment Regime
- AETN administrative resolutions (scraped)

## Setup

### Prerequisites

- Python 3.11+
- Qdrant (docker)
- Ollama (for local LLM) or OpenAI API key

### Quick Start

```bash
# Clone and enter directory
cd lexenergy

# Install dependencies
pip install -r requirements.txt

# Start infrastructure
docker compose -f docker/docker-compose.yml up -d qdrant ollama

# Pull LLM model
ollama pull llama3.1

# Configure environment
cp .env.example .env

# Ingest legal corpus
python -c "import asyncio; from ingestion.pipeline import run_ingestion; asyncio.run(run_ingestion())"

# Start API
uvicorn app.main:app --reload
```

### Docker (Full Stack)

```bash
docker compose -f docker/docker-compose.yml up -d
```

## API Usage

### Query Endpoint

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can a foreign company build a solar plant in Bolivia?",
    "subsector": "Solar"
  }'
```

### Response Structure

```json
{
  "question": "Can a foreign company build a solar plant in Bolivia?",
  "answer": {
    "direct_conclusion": "...",
    "regulatory_analysis": "...",
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
      "type": "Aranceles e Impuestos",
      "description": "Exención arancelaria y depreciación acelerada",
      "articles": ["DS 5503 Art. 3"]
    }
  },
  "sources": ["Ley_1604_art_2_0", "DS_5503_art_3_0"],
  "processing_time_ms": 1234
}
```

### Health Check

```bash
curl http://localhost:8000/api/v1/health
```

## Project Structure

```
lexenergy/
├── app/
│   ├── api/           # FastAPI routes
│   ├── rag/           # RAG pipeline, chain, context builder
│   ├── retrieval/     # BM25, dense, reranker, hybrid
│   ├── prompts/       # Legal prompt templates
│   ├── agents/        # LangGraph agent workflow
│   ├── models/        # Pydantic schemas
│   ├── services/      # Business logic
│   ├── config.py      # Settings
│   └── main.py        # FastAPI entry point
├── ingestion/
│   ├── lexivox/       # Lexivox.org scraper
│   ├── aetn/          # AETN scraper
│   ├── parsing/       # Legal document parsers
│   ├── normalization/ # Text normalizers
│   ├── metadata/      # Metadata extraction
│   └── pipeline.py    # Ingestion orchestration
├── corpus/            # Legal text corpus
├── vectorstore/       # Qdrant client
├── tests/             # Test suite
└── docker/            # Container setup
```

## Key Design Decisions

1. **Legal Semantic Chunking**: Each chunk represents one article, section, or normative unit (no naive character chunking)
2. **Metadata-First Retrieval**: Filtering by subsector, norm type, and validity precedes semantic search
3. **Constitutional Hierarchy**: CPE Article 410 is enforced as supreme norm
4. **Hybrid Retrieval**: BM25 + Dense + Reranker for maximum precision
5. **Structured Output**: Every response includes conclusion, analysis, citations, risk matrix, and incentives

## Legal Risk Flags

- Constitutional Conflict
- Nationalization Risk
- Regulatory Instability
- Legal Ambiguity
- Renewable Incentive
- Arbitration Protection
- Private Investment

## License

MIT
