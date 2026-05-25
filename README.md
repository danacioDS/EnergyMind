Aquí tienes una versión **más profesional, más clara y lista para GitHub**, con mejor estructura, redacción consistente y enfoque más “product-grade”.

---

# 📘 LexEnergy Bolivia

LexEnergy Bolivia is a specialized **Legal RAG (Retrieval-Augmented Generation) platform** designed to analyze Bolivian legislation related to renewable energy investment.

It combines **FastAPI, LangChain/LangGraph, Qdrant, and hybrid retrieval (BM25 + dense embeddings + reranking)** to deliver structured legal reasoning over national regulatory frameworks.

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
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ RAGPipeline  │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼────────┐
│ Retrieval     │  │ Prompt       │  │ LangGraph      │
│ Engine        │  │ Engine       │  │ Agent          │
└───────┬──────┘  └──────────────┘  └────────────────┘
        │
┌───────┼──────────────┐
│       │              │
▼       ▼              ▼
BM25  Dense        Reranker
│     (BGE)        (Cross/BGE)
└───────┬──────────────┘
        │
   ┌────▼────┐
   │ Qdrant  │
   │ VectorDB│
   └─────────┘
```

---

## 🔎 Retrieval Pipeline

The system follows a **multi-stage legal retrieval process**:

1. **Metadata Filtering**
   Filters by subsector, norm type, and validity before semantic search.

2. **BM25 Retrieval**
   Sparse keyword-based retrieval for legal precision.

3. **Dense Retrieval**
   Embedding-based semantic search using **BAAI/bge-m3**.

4. **Hybrid Fusion**
   Combines BM25 + dense scores with normalization.

5. **Reranking**
   Cross-encoder reranking (BAAI reranker or fallback).

6. **Context Builder**
   Structures retrieved legal articles into LLM-ready context.

7. **LLM Generation**
   Uses Llama 3.1 / Mistral Nemo with legal-specific prompts.

---

## ⚖️ Legal Corpus Coverage

* 🇧🇴 Constitution of Bolivia (2009) — selected articles
* ⚡ Ley de Electricidad N° 1604 (1994)
* 📜 Ley N° 943 (amendments)
* 🏗️ DS N° 5503 (2025) — Investment Regime
* 🏛️ AETN administrative resolutions (scraped)

---

## 🚀 Setup

### Prerequisites

* Python 3.11+
* Docker (Qdrant + Redis)
* Ollama (local LLM) or OpenAI API key

---

### ⚡ Quick Start (Local)

```bash
# Clone repository
cd lexenergy

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start Qdrant
docker compose -f docker/docker-compose.yml up -d qdrant

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

### 🐳 Full Stack (Docker)

```bash
docker compose -f docker/docker-compose.yml up -d
```

Services included:

* Qdrant (vector database)
* Redis (cache / queue)
* LexEnergy API (FastAPI)

---

## 📡 API Usage

### 🔍 Query Endpoint

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can a foreign company build a solar plant in Bolivia?",
    "subsector": "Solar"
  }'
```

---

### 📤 Response Format

```json
{
  "question": "...",
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
      "constitutional_conflict_risk": "Medium",
      "nationalization_risk": "Medium-High",
      "regulatory_instability": "High"
    },
    "incentives_detected": {
      "detected": true,
      "type": "Tax Incentives",
      "description": "Custom duty exemptions and accelerated depreciation"
    }
  },
  "sources": ["Ley_1604_art_2_0", "DS_5503_art_3_0"],
  "processing_time_ms": 1234
}
```

---

## 📁 Project Structure

```
lexenergy/
├── app/
│   ├── api/            # FastAPI routes
│   ├── rag/            # RAG pipeline + context builder
│   ├── retrieval/      # BM25, dense, hybrid, reranker
│   ├── prompts/        # Legal prompt templates
│   ├── agents/         # LangGraph workflows
│   ├── models/         # Pydantic schemas
│   ├── services/       # Business logic layer
│   ├── config.py
│   └── main.py
│
├── ingestion/          # Scrapers + normalization
│   ├── lexivox/
│   ├── aetn/
│   ├── parsing/
│   └── pipeline.py
│
├── corpus/             # Legal dataset
├── vectorstore/        # Qdrant integration
├── tests/
└── docker/
```

---

## 🧩 Key Design Decisions

* **Legal-first chunking** → articles as atomic units (no naive splitting)
* **Metadata-first retrieval** → filtering before vector search
* **Constitutional hierarchy enforcement** → CPE Art. 410 priority layer
* **Hybrid retrieval system** → BM25 + dense + reranker fusion
* **Structured legal output** → conclusions + risks + citations always enforced

---

## ⚠️ Legal Risk Model

Detected risk categories:

* Constitutional Conflict
* Nationalization Risk
* Regulatory Instability
* Legal Ambiguity
* Renewable Incentive Detection
* Arbitration Protection Level
* Private Investment Exposure

---

## 📜 License

MIT


