
#### DEMO ################################################
#### #### ################################################
#### #### ################################################

---

# Demo Walkthrough

## Running a Live Demo

Start the API:

```bash
uvicorn app.main:app --reload
```

Open the interactive API documentation:

```text
http://localhost:8000/docs
```

The Swagger UI allows testing the complete RAG pipeline interactively without requiring a frontend application.

---

## Suggested Demo Flow

### 1. Health Check

Verify infrastructure status:

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:

```json
{
  "status": "ok"
}
```

Explain during interview:

> “This verifies the API, vector database connectivity, and retrieval services are operational.”

---

### 2. Legal Query Demo

Execute a legal investment question:

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can a foreign company build a solar plant in Bolivia?",
    "subsector": "Solar"
  }'
```

Explain during interview:

> “The query passes through metadata filtering, hybrid retrieval, reranking, context assembly, and finally LLM generation.”

---

### 3. Explain the Retrieval Pipeline

Describe the execution flow step-by-step:

#### Metadata Filtering

* Restricts search space by:

  * subsector
  * norm type
  * legal validity

Explain:

> “Filtering before vector search improves retrieval precision and reduces irrelevant context.”

---

#### Hybrid Retrieval

The system combines:

* BM25 sparse retrieval
* Dense semantic retrieval using BGE embeddings

Explain:

> “BM25 captures exact legal terminology while dense retrieval captures semantic similarity.”

---

#### Reranking

The top retrieved chunks are reranked using:

```text
BAAI/bge-reranker-large
```

Explain:

> “Reranking improves contextual relevance before sending documents to the LLM.”

---

#### Context Assembly

Retrieved legal fragments are transformed into structured context:

* legal hierarchy
* article references
* regulatory metadata
* risk indicators

Explain:

> “The context builder structures legal evidence before generation to reduce hallucinations.”

---

### 4. Show Structured Output

Highlight that the response is not plain text.

The system returns:

* direct conclusion
* legal analysis
* legal citations
* regulatory risk matrix
* incentives detection

Explain:

> “The goal was to generate grounded legal analysis rather than generic chatbot responses.”

---

## Suggested Interview Questions for Demo

### Query 1 — Renewable Investment

```text
Can a foreign company build a solar plant in Bolivia?
```

Demonstrates:

* investment analysis
* constitutional/legal reasoning
* incentives detection

---

### Query 2 — Regulatory Risk

```text
What are the regulatory risks for wind energy projects in Bolivia?
```

Demonstrates:

* risk matrix generation
* semantic retrieval
* multi-document reasoning

---

### Query 3 — Incentives

```text
Are there tax incentives for renewable energy investments?
```

Demonstrates:

* legal citation extraction
* incentive detection
* structured response generation

---

## Demo Talking Points

During the interview, emphasize:

### RAG Architecture

> “The project focuses on retrieval quality and grounded generation rather than generic chat responses.”

### Legal Semantic Chunking

> “Chunks are based on legal articles and normative units instead of naive fixed-size chunking.”

### Hallucination Reduction

> “The architecture minimizes hallucinations using metadata filtering, reranking, and grounded citations.”

### Production-Oriented Design

> “The system was designed modularly to support future industrialization and conversational interfaces.”

### Hybrid Retrieval

> “Combining sparse and dense retrieval improved precision for legal terminology and semantic understanding.”

---

## Optional Improvements (Roadmap)

* Conversational UI with Streamlit or LibreChat
* Automated evaluation using Ragas
* Agentic workflows with LangGraph
* Multi-turn conversation memory
* Citation highlighting in responses
* AWS deployment (Bedrock + ECS + Qdrant Cloud)

---

## Interview Positioning

This project demonstrates:

* Applied GenAI engineering
* RAG architecture design
* LLM orchestration
* Retrieval optimization
* Legal-domain semantic search
* API-first AI systems
* Production-oriented backend design

It is intentionally focused on backend AI infrastructure and experimentation workflows rather than frontend development.
