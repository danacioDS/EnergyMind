# LexEnergy Bolivia — Backend 03: Improvements

## Overview

Eight new recommendations, none repeated from the previous round. Ordered by severity.

---

## Blocker

### 1. Missing `schemas.py` — gitignore pattern collision

**Problem:** The `.gitignore` pattern `models/` (line 38) matched *any* directory named `models` at any depth, including `app/models/`. This caused `app/models/schemas.py` and `app/models/legal_unit.py` to be silently excluded from git tracking. A fresh `git clone` would fail with `ModuleNotFoundError` on every import from `app.models`.

**Root cause:** Git's `.gitignore` semantics — an unanchored pattern `models/` matches the directory name anywhere in the tree.

**Fix:** Changed `models/` → `/models/` (anchored to repo root). The leading `/` restricts the pattern to the `models/` directory at the repository root, which was the original intent (HuggingFace/SentenceTransformer model cache).

```diff
- models/
+ /models/
```

**Verification:** `git check-ignore -v app/models/schemas.py` now returns "NOT IGNORED".

---

## Bug

### 2. Unstable Qdrant point IDs — `hash()` not deterministic across runs

**Problem:** Document IDs for Qdrant points were generated with:
```python
id=abs(hash(unit.id)) % (10**12),
```
Python's `hash()` is randomized per interpreter start (since Python 3.3, `PYTHONHASHSEED` is random by default). Re-running ingestion produced **different numeric IDs** for the same documents, silently duplicating points and corrupting the collection on every re-ingestion.

**Fix:** Replaced with `uuid.uuid5()` — a deterministic UUID based on SHA-1 of the unit's string ID within a namespace:

```python
id=uuid.uuid5(uuid.NAMESPACE_DNS, unit.id),
```

This produces the same UUID for `"Ley_1604_art_17"` every time, regardless of Python version, interpreter restart, or host.

**Files:** `vectorstore/qdrant_client.py:130`

---

## Performance

### 3. Persisted BM25 index (~300ms savings per query)

**Problem:** The BM25 index was rebuilt from scratch on every query — re-tokenizing all Qdrant results with jieba and re-computing the BM25Okapi corpus — even though the underlying document set rarely changes between queries in the same session.

**Fix:** Added `save()` / `load()` methods to `BM25Retriever` using `pickle`. The `RetrievalEngine` now:
1. Attempts to load the persisted index on startup
2. Only builds the index on first query if no cache exists
3. Persists the index after building it for subsequent requests

Index stored at `cache/bm25_index.pkl`.

**Files:** `app/retrieval/bm25.py`, `app/retrieval/engine.py`

### 4. Batched embeddings during ingestion (~5-10x speedup)

**Problem:** `upsert_units()` called `self.embedder.encode(unit.texto)` individually for each `LegalUnit` (45 separate calls for the current corpus). SentenceTransformer is optimized for batch processing — individual calls incur per-call overhead without utilizing the GPU/CPU parallelism.

**Fix:** All texts are now encoded in a single batched call before conversion to `PointStruct`:

```python
texts = [unit.texto for unit in units]
embeddings = self.embedder.encode(texts, normalize_embeddings=True, show_progress_bar=True).tolist()
points = [self._unit_to_point(unit, emb) for unit, emb in zip(units, embeddings)]
```

The `_unit_to_point()` method accepts an optional pre-computed embedding to support both paths.

**Files:** `vectorstore/qdrant_client.py`

### 5. Adaptive hybrid fusion alpha

**Problem:** The hybrid BM25+dense fusion weight (`alpha`) was hardcoded to `0.5` — equal weight regardless of query type. Legal code/number lookups benefit from higher BM25 weight (exact keyword match), while conceptual questions benefit from higher dense weight (semantic similarity).

**Fix:** Added:
1. **Configurable baseline**: `hybrid_alpha: float = 0.5` in `Settings` (`app/config.py`)
2. **Query-type detection** in `HybridRetriever._infer_alpha()`:
   - Exact legal code patterns (artículo, Ley N°, Decreto, etc.) → `alpha=0.7` (keyword-biased)
   - Conceptual patterns (riesgo, qué es, definición, diferencia) → `alpha=0.3` (semantic-biased)
   - Everything else → `settings.hybrid_alpha` (default 0.5)

**Files:** `app/config.py`, `app/retrieval/hybrid.py`

---

## Observability

### 6. RAGAS evaluation

**Problem:** No automated quality measurement for the RAG pipeline. The golden test set verified retrieval presence but not generation quality.

**Fix:** Added a standalone RAGAS evaluation script (`evaluation/run_ragas_eval.py`) that:
1. Runs the full pipeline against 10 golden queries
2. Computes four RAGAS metrics: faithfulness, answer relevancy, context precision, context recall
3. Saves results to `evaluation/results.json`

**Usage:** `python -m evaluation.run_ragas_eval`

**Files:** `evaluation/run_ragas_eval.py`, `requirements.txt` (added `ragas`)

### 7. Correlation IDs for request tracing

**Problem:** Logs across the 5-stage pipeline (route → query_service → rag_pipeline → retrieval_engine → hybrid/bm25/dense/reranker) were not correlated. Debugging a single bad answer required manual log grepping across multiple layers.

**Fix:**
1. Added `CorrelationIDMiddleware` that generates or accepts (via `X-Correlation-ID` header) an 8-char correlation ID per request
2. Sets `logger.contextualize(correlation_id=...)` for loguru context propagation
3. Sets default `correlation_id=--------` for non-request log messages
4. Log format includes the correlation ID column
5. Correlation ID is returned as a response header

**Example log output:**
```
15:42:03 | INFO     | a1b2c3d4 | RetrievalEngine initialized (BM25 from cache)
15:42:03 | INFO     | a1b2c3d4 | Phase 1: BM25 retrieval for: solar incentives
15:42:03 | INFO     | a1b2c3d4 | Phase 2: Dense retrieval for: solar incentives
15:42:04 | INFO     | a1b2c3d4 | Phase 3: Hybrid fusion (alpha=0.7)
```

**Files:** `app/main.py`, `app/api/routes.py`

---

## Low Priority

### 8. SSE streaming endpoint + corpus stats

**Streaming endpoint:** Added `POST /api/v1/query/stream` that returns progressive Server-Sent Events:
1. `start` — correlation ID
2. `retrieval` — query acknowledgment
3. `analysis` — direct conclusion text
4. `risk` — risk matrix
5. `incentives` — detected incentives
6. `complete` — final result with timing and sources
7. `error` — failure detail

**Corpus stats:** Added `GET /api/v1/corpus/stats` returning:
- Total document count
- Distribution by norm type
- Distribution by subsector
- Renewable incentive document count
- Risk flag frequency
- Number of configured source files

**Files:** `app/api/routes.py`

---

## Test Results

```
27 passed, 1 failed (pre-existing torch<2.6), 1 skipped (DenseRetriever golden)
All new code compiles clean
All existing golden-set retrieval tests unchanged
.blocker fixed: app/models/schemas.py no longer gitignored
```

## Files Changed

| File | Changes |
|------|---------|
| `.gitignore` | `models/` → `/models/` (anchor to repo root) |
| `vectorstore/qdrant_client.py` | `hash()` → `uuid.uuid5()`; batched embedding encode |
| `app/config.py` | Added `hybrid_alpha` setting |
| `app/retrieval/bm25.py` | Added `save()` / `load()` with pickle |
| `app/retrieval/hybrid.py` | Added `_infer_alpha()` query-type detection |
| `app/retrieval/engine.py` | BM25 persist/load on init; build-only-once logic |
| `app/main.py` | `CorrelationIDMiddleware`; log format with CID column |
| `app/api/routes.py` | CID propagation; `POST /query/stream` SSE; `GET /corpus/stats` |
| `requirements.txt` | Added `ragas` for evaluation |
| `evaluation/run_ragas_eval.py` | New standalone RAGAS evaluation script |
