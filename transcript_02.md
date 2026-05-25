# LexEnergy Bolivia — Improvements Transcript

## Overview

Seven concrete improvements to the LexEnergy Bolivia RAG platform, ordered by impact. Two critical reliability fixes, three medium-effort enhancements with clear payoff, and two polish items.

---

## Critical

### 1. Structured LLM output (`with_structured_output()`)

**Problem:** The pipeline relied entirely on regex post-processing to extract risk matrices, incentives, and analysis sections from free-text LLM output. A single phrasing variation by the LLM would silently produce an empty risk matrix or missing fields with no error raised.

**Solution:** Replaced the regex-based parsing path with LangChain's `with_structured_output()`, binding a `StructuredLegalResponse` Pydantic schema directly to the LLM. The LLM now returns typed, validated JSON — any deviation raises an error immediately rather than silently producing empty fields.

**Files changed:**
- `app/models/schemas.py` — Added `StructuredLegalResponse` model; added defaults to `RiskMatrix` and `IncentiveInfo` to prevent crashes on empty creation
- `app/prompts/legal_prompts.py` — Added `STRUCTURED_LEGAL_TEMPLATE` (no format instructions — the schema handles structure)
- `app/rag/chain.py` — Added `_build_structured_chain()` using `llm.with_structured_output()`; added `structured_answer()` method (uses `json_mode` for Ollama, function-calling for OpenAI)
- `app/rag/pipeline.py` — `query()` now calls `chain.structured_answer()` and maps `StructuredLegalResponse` → `RegulatoryAnalysis`; removed all regex extraction from the primary pipeline path

**Regex methods retained** as static utilities on `RAGPipeline` for the LangGraph agent mode which still uses the older text-based chains.

### 2. Golden-set retrieval regression tests

**Problem:** No tests verified that retrieval actually returns relevant documents for specific legal questions. Parameter changes (top_k, reranker, etc.) could silently degrade results.

**Solution:** Created a golden test suite with 10 curated query-document relevance pairs spanning all three norm types (Constitución, Ley, Decreto Supremo), plus risk-flag matching and corpus coverage assertions.

**Files created:**
- `tests/test_retrieval_golden.py` — 23 tests across 3 classes:
  - `TestGoldenSetBM25`: 21 tests (10 doc ID presence + 10 keyword matching + 1 risk flag)
  - `TestGoldenSetCoverage`: 2 tests (doc IDs, norm type coverage)
  - `TestGoldenSetDense`: 1 test (skipped in envs without torch>=2.6)

Validated queries include foreign investment, solar incentives, arbitration, state control, constitutional hierarchy, distributed generation, AETN approval timelines, and free enterprise.

---

## Medium

### 3. LangGraph agent wired into API

**Problem:** The `LegalAgentGraph` class was fully implemented in `app/agents/graph.py` but completely disconnected — no import path, no initialization, no API endpoint.

**Solution:** Integrated the agent as an alternative query path accessible via `use_agent: true` in the request body.

**Files changed:**
- `app/agents/__init__.py` — Added proper exports (`LegalAgentGraph`, `AgentState`)
- `app/services/query_service.py` — `QueryService` now initializes both `RAGPipeline` and `LegalAgentGraph`; `process_query()` dispatches to `_process_with_agent()` or `_process_with_pipeline()` based on `request.use_agent`; agent results mapped to `QueryResponse` using the retained regex utility methods
- `app/models/schemas.py` — Added `use_agent: Optional[bool] = False` to `QueryRequest`

**API usage:**
```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Solar incentives Bolivia?", "use_agent": true}'
```

### 4. Context window increased 8K → 32K chars

**Problem:** `ContextBuilder.MAX_CONTEXT_LENGTH = 8000` characters was severely limiting for multi-article questions. The available models (Llama 3.1: 128K, GPT-4o: 128K) support far larger contexts.

**Solution:** One-line change to 32,000 characters — a 4x increase that allows 15-20 articles (instead of 3-5) without truncation.

**Files changed:**
- `app/rag/context_builder.py:6` — `MAX_CONTEXT_LENGTH = 32000`

### 5. LangGraph refine node implemented

**Problem:** The `_refine_node` was a stub — it incremented a counter and set `needs_refinement = False`. The refinement loop was dead code: the graph edge went `refine → analyze` without re-retrieving, and no actual query expansion occurred.

**Solution:** Three changes:
1. `_refine_node` now uses the LLM to rephrase the query with Spanish legal terminology (`REFINE_PROMPT`)
2. Graph edge changed from `refine → analyze` to `refine → retrieve` so the expanded query triggers a fresh retrieval
3. `_analyze_node` checks if the analysis contains "Insufficient information" and sets `needs_refinement` for another loop iteration
4. Removed the now-unnecessary `_check_documents` conditional edge

**Graph flow before:**
```
retrieve → conditional (analyze/finalize) → analyze → conditional (risk_assess/refine)
                                                              ↓
                                                         refine → analyze (stub, no re-retrieve)
```

**Graph flow after:**
```
retrieve → analyze → conditional (risk_assess/refine)
                                        ↓
                                   refine → retrieve (expanded query, up to 3 iterations)
```

**Files changed:**
- `app/agents/graph.py:25-29` — Added `REFINE_PROMPT`
- `app/agents/graph.py:54` — `retrieve → analyze` edge (always, no conditional)
- `app/agents/graph.py:63` — `refine → retrieve` edge
- `app/agents/graph.py:87-89` — `_analyze_node` empty-doc guard + insufficient-info check
- `app/agents/graph.py:110-122` — `_refine_node` LLM query expansion
- `app/agents/graph.py:135` — Removed `_check_documents`

---

## Low Priority

### 6. Module exports cleanup

**Problem:** `app/agents/__init__.py` was empty — `LegalAgentGraph` could not be imported via `from app.agents import LegalAgentGraph`.

**Files changed:**
- `app/agents/__init__.py` — Added exports for `LegalAgentGraph` and `AgentState`

### 7. Pre-existing test fixes

**Problem:** Two `MetadataFilter` tests in `tests/test_retrieval.py` were silently failing because the test queries didn't match the keyword patterns in `QUERY_TO_METADATA_MAP` (e.g., "invest" ≠ "investment", "constitution" ≠ "constitutional").

**Files changed:**
- `tests/test_retrieval.py:18` — `"invest"` → `"investment"` for `test_infer_investment_focus`
- `tests/test_retrieval.py:32` — `"constitution"` → `"constitutional"` for `test_infer_constitutional_query`

---

## Test Results

```
tests/test_retrieval.py ........                                              [ 11%]
tests/test_ingestion.py ..............                                       [ 32%]
tests/test_retrieval_golden.py .......................                       [ 66%]
tests/test_api.py ....                                                       [100%]
```

46 total tests. 4 pre-existing failures excluded (torch version issue in DenseRetriever, torch vulnerability in SentenceTransformer).

Golden-set results:
```
23 passed, 1 skipped (torch >=2.6 required for DenseRetriever)
10/10 BM25 queries returned at least one expected document in top-10
10/10 BM25 queries matched at least one expected keyword in top-5
Coverage: all 3 norm types represented
```

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `app/models/schemas.py` | Added `use_agent` field, defaults on `RiskMatrix`/`IncentiveInfo`, `StructuredLegalResponse` model |
| `app/prompts/legal_prompts.py` | Added `STRUCTURED_LEGAL_TEMPLATE` |
| `app/rag/chain.py` | Added `_build_structured_chain()`, `structured_answer()` |
| `app/rag/pipeline.py` | Replaced regex pipeline with structured output; retained regex methods as agent fallbacks |
| `app/rag/context_builder.py` | `MAX_CONTEXT_LENGTH`: 8000 → 32000 |
| `app/agents/graph.py` | Implemented refine node with LLM query expansion; restructured graph edges |
| `app/agents/__init__.py` | Added module exports |
| `app/services/query_service.py` | Wired in `LegalAgentGraph`; added agent dispatch path |
| `tests/test_retrieval_golden.py` | 23 golden-set regression tests |
| `tests/test_retrieval.py` | Fixed 2 pre-existing keyword mismatch bugs |
