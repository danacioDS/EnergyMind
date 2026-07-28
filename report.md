# LexEnergy Bolivia — Failure Analysis Report

## Executive Summary

The project is a Legal RAG platform for Bolivian renewable energy legislation. It has **multiple critical runtime bugs** that prevent it from functioning. The two most severe issues are:

1. **`QueryService` is missing the methods that `routes.py` calls** — the API will crash with `AttributeError` on any query.
2. **Sync methods are called with `await`** — `QdrantStore.search()`, `QdrantStore.close()`, `QdrantStore.initialize()`, and `run_ingestion()` are all synchronous but are awaited in async contexts, causing `TypeError`.

---

## Critical Bugs (will crash the application)

### 1. `QueryService` has no `process_query` or `process_query_streaming` methods

**Files:** `app/api/routes.py:33`, `app/api/routes.py:129`, `app/services/query_service.py`

```python
# routes.py:33 — calls this:
response = await service.process_query(request)

# routes.py:129 — calls this:
async for event in service.process_query_streaming(request, stream):
```

But `QueryService` (query_service.py) only has:
- `initialize()`
- `close()`
- `_init_pipeline()`, `_init_agent()`, `_init_redis()`

**Result:** Every query to `/api/v1/query` and `/api/v1/query/stream` crashes with `AttributeError: 'QueryService' object has no attribute 'process_query'`.

### 2. `QdrantStore.search()` and `scroll_all()` are sync, but called with `await`

**Files:** `app/retrieval/engine.py:64`, `app/retrieval/engine.py:32`, `vectorstore/qdrant_client.py`

```python
# engine.py:64 — awaited:
qdrant_results = await self.qdrant.search(query=query, ...)

# engine.py:32 — awaited:
all_docs = await self.qdrant.scroll_all()
```

`QdrantStore.search()` at `qdrant_client.py:221` is a regular `def`, not `async def`. The `qdrant-client` library uses a synchronous `QdrantClient`.

**Result:** `TypeError: object ... can't be used in 'await' expression`. The retrieval engine will never return results.

### 3. `QdrantStore.initialize()` is sync, but called with `await`

**File:** `core/runtime/resource_manager.py:72`

```python
await store.initialize()  # store.initialize() is sync
```

Same `TypeError` as above. The application will fail during startup warmup.

### 4. `QdrantStore.close()` is sync, but called with `await`

**File:** `core/runtime/resource_manager.py:60`

```python
await self._qdrant.close()  # close() is sync
```

### 5. `run_ingestion()` is sync, but called with `await`

**File:** `app/api/routes.py:68`

```python
count = await run_ingestion()  # run_ingestion() is sync
```

`ingestion/pipeline.py:134` defines `run_ingestion()` as a plain `def`.

---

## Severe Bugs (wrong behavior)

### 6. `MetadataFilter.infer_from_query` always injects `vigente=True`

**File:** `app/retrieval/metadata_filter.py:44`

```python
metadata_filter["vigente"] = True  # always set
```

This means queries for historical/obsolete laws will never find documents. Additionally, the corpus data in `corpus/normalized/all_units.json` and `CORPUS_DEFINITIONS` (ingestion/pipeline.py) does not always set `vigente` — only `ley_1604_1994` has `"vigente": True`. Most documents may not have this field, so the filter silently excludes them from Qdrant results.

### 7. Missing `settings` import in `routes.py`

**File:** `app/api/routes.py:86`

```python
corpus_path = settings.corpus_normalized_path / "all_units.json"
#          ^^^ settings is never imported in routes.py
```

The `/corpus/stats` endpoint will crash with `NameError: name 'settings' is not defined`.

### 8. `LegalAgentGraph` creates its own `RetrievalEngine` with no Qdrant connection

**File:** `app/agents/graph.py:36`

```python
self.retrieval = RetrievalEngine()  # no qdrant argument
```

This creates a new `QdrantStore` independently, without sharing the connection from `ResourceManager`. Two separate Qdrant connections, two separate BM25 indices, and potentially duplicate heavy model loading.

### 9. BM25 uses jieba (Chinese tokenizer) for Spanish legal text

**File:** `app/retrieval/bm25.py:6,20`

```python
import jieba
def _tokenize(self, text: str) -> List[str]:
    try:
        return list(jieba.cut(text))
```

Jieba is a Chinese text segmentation library. For Spanish legal text, it will over-segment and produce poor tokens. The fallback `text.lower().split()` would actually be better.

---

## Moderate Bugs

### 10. `corpus_stats` endpoint blocks the event loop

**File:** `app/api/routes.py:90-91`

```python
with open(corpus_path) as f:  # sync file I/O in async handler
    units = json.load(f)
```

This blocks the asyncio event loop for the duration of the file read.

### 11. Tests assert wrong expected values

**File:** `tests/test_api.py`

- Asserts `data["status"] == "healthy"` but the endpoint returns `"alive"`
- Asserts `data["service"] == "LexEnergy Bolivia"` but the endpoint returns `{"status": "alive"}`
- Asserts `top_k is None` but the default is `5`
- Asserts `422` for empty `question: ""` but empty string is valid for `str` field

### 12. Golden test expected doc IDs are fabricated

**File:** `tests/test_retrieval_golden.py`

IDs like `Constitucion_320_art_320` don't match the actual `CORPUS_DEFINITIONS` which would produce IDs based on `tipo_norma` + `norma_id` + article numbers (e.g., `Constitucion_CPE_art_1`).

### 13. `DenseRetriever.search` is async but does CPU-bound work without `to_thread`

**File:** `app/retrieval/dense.py:17-31`

The dense search encodes all document texts and computes cosine similarity inline in an async function, blocking the event loop.

---

## Non-Bug Issues

| Issue | Location | Impact |
|-------|----------|--------|
| Duplicate embedding service | `app/services/embedding_service.py` vs `core/embeddings.py` | Dead code, confusion |
| `.env` committed to git | `.env` | Security risk (currently no secrets) |
| `test_search.py` not a pytest test | `tests/test_search.py` | Fails under `pytest` |
| Unused `MetadataFilter.build_qdrant_filter` | `metadata_filter.py:57` | Dead code |
| Inconsistent sync/async throughout | Multiple files | Architectural confusion |
| `RAGPipeline.query()` calls `retrieve()` without `await` | `app/rag/pipeline.py:61` | Another `TypeError` since `engine.py` defines `retrieve()` as `async def` |

---

## Infrastructure Issues

| Issue | Impact |
|-------|--------|
| Qdrant not running locally | No vector search possible |
| Redis not running locally | Cache unavailable (graceful degradation works) |
| Ollama not running locally | LLM calls fail (unless OpenAI key is set) |
| `BAAI/bge-m3` model not downloaded | First startup takes very long, may fail on low memory |
| `BAAI/bge-reranker-large` model not downloaded | Reranker falls back to `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Docker Compose exists but frontend config may not resolve | Network issues between containers |

---

## Root Cause Analysis

The project appears to have been developed incrementally with an **async/sync boundary that was never properly reconciled**. The pattern suggests:

1. `QdrantStore` was originally written as synchronous (wrapping `qdrant-client` sync API)
2. The retrieval and API layers were written assuming async interfaces
3. The `QueryService` was left incomplete — `process_query` and `process_query_streaming` were never implemented
4. The `await` calls on sync methods "work" in some code paths because Python will sometimes not evaluate the await until the coroutine is actually awaited — but when they are awaited, they crash

---

## Recommended Fix Priority

| Priority | Fix |
|----------|-----|
| **P0** | Add `process_query()` and `process_query_streaming()` to `QueryService` |
| **P0** | Make `QdrantStore` methods async (wrap sync calls in `asyncio.to_thread`) or remove `await` callers |
| **P0** | Add missing `settings` import in `routes.py` |
| **P0** | Fix `RAGPipeline.query()` to `await self.retrieval.retrieve(...)` |
| **P1** | Remove `vigente=True` default from `MetadataFilter.infer_from_query` or ensure all corpus docs have `vigente` |
| **P1** | Replace jieba tokenizer with Spanish-aware tokenizer |
| **P1** | Pass shared `QdrantStore` instance to `LegalAgentGraph` |
| **P2** | Fix all test assertions to match actual endpoint responses |
| **P2** | Use `asyncio.to_thread` for sync file I/O in `corpus_stats` |
| **P3** | Remove dead code (`embedding_service.py`, `MetadataFilter.build_qdrant_filter`) |
| **P3** | Remove `.env` from git, add to `.gitignore` |
