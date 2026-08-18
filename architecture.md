# EnergyMind — Arquitectura

## Descripción General

**EnergyMind** es una plataforma **Legal RAG** especializada en legislación boliviana de energías renovables. Ingiere documentos legales (Constitución, leyes, decretos, resoluciones), los indexa en **Qdrant** y expone un pipeline de recuperación multi-etapa con razonamiento legal vía LLM, servido por **FastAPI** y consumido por un frontend **Next.js 16**.

Este documento describe la arquitectura **tal como está implementada** en el código actual.

---

## Arquitectura de Alto Nivel

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            CLIENTE                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Frontend Next.js 16 (React 19, shadcn/ui, Tailwind v4)         │  │
│  │  Puerto 3000 — rewrites /api/* → backend                         │  │
│  └────────────────────────────┬─────────────────────────────────────┘  │
│                               │ HTTP + SSE                              │
├───────────────────────────────┼─────────────────────────────────────────┤
│                        CAPA API (FastAPI :8000)                         │
│  ┌───────────────────────────┴───────────────────────────────────────┐  │
│  │  app/api/routes.py   (prefijo /api/v1)                           │  │
│  │   POST /query        POST /query/stream                          │  │
│  │   POST /ingest       GET  /corpus/stats                          │  │
│  │   GET  /health       GET  /health/ready                          │  │
│  │  Middlewares: CORS (abierto) + CorrelationID (X-Correlation-ID)  │  │
│  └───────────────────────────┬───────────────────────────────────────┘  │
│                               │                                         │
├───────────────────────────────┼─────────────────────────────────────────┤
│                        CAPA DE SERVICIOS                                │
│  ┌───────────────────────────┴───────────────────────────────────────┐  │
│  │  QueryService        — orquesta: caché → pipeline/agente → caché  │  │
│  │  SSEStreamManager    — envuelve eventos en protocolo text/event-stream │
│  │  Redis cache         — caché de respuestas (TTL 1h)               │  │
│  └───────────────────────────┬───────────────────────────────────────┘  │
│                               │                                         │
├───────────────────────────────┼─────────────────────────────────────────┤
│                     CAPA RAG / AGENTE                                   │
│  ┌───────────────────────────┴───────────────────────────────────────┐  │
│  │  RAGPipeline (sin agente)   │   LegalAgentGraph (LangGraph)        │  │
│  │   retrieve → context → LLM  │   retrieve → analyze → refine (x3)   │  │
│  │   con soporte streaming     │   → risk_assess → finalize           │  │
│  │                             │   ⚠ INCOMPLETO (métodos inexistentes)│  │
│  └───────────────────────────┬───────────────────────────────────────┘  │
│                               │                                         │
├───────────────────────────────┼─────────────────────────────────────────┤
│                    PIPELINE DE RECUPERACIÓN                             │
│  ┌───────────────────────────┴───────────────────────────────────────┐  │
│  │  RetrievalEngine                                                  │  │
│  │                                                                   │  │
│  │  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌─────────┐  │  │
│  │  │Metadata    │   │  BM25      │   │  Dense     │   │ Hybrid  │  │  │
│  │  │Filter      │   │ (sparse)   │   │ (Qdrant)   │   │ Fusion  │  │  │
│  │  │(keywords)  │   │ (español)  │   │ cosine     │   │ (alpha) │  │  │
│  │  └────────────┘   └────────────┘   └────────────┘   └─────────┘  │  │
│  │                        (en paralelo via gather / threadpool)      │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │  Reranker (cross-encoder) — DESACTIVADO en producción       │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────┬───────────────────────────────────────┘  │
│                               │                                         │
├───────────────────────────────┼─────────────────────────────────────────┤
│                       CAPA DE INFRAESTRUCTURA                           │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌─────────┐ │
│  │ Qdrant        │  │ Redis         │  │ Embeddings    │  │ LLMs    │ │
│  │ (vector store)│  │ (cache)       │  │ MiniLM-L6 384d│  │ Groq →  │ │
│  │ :6333 REST    │  │ :6379         │  │ (local, CPU)  │  │ Gemini  │ │
│  │ :6334 gRPC    │  │               │  │               │  │ (API)   │ │
│  └───────────────┘  └───────────────┘  └───────────────┘  └─────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Desglose de Componentes

### 1. Capa API (`app/api/routes.py`)

| Endpoint | Método | Descripción | Estado |
|----------|--------|-------------|--------|
| `/api/v1/query` | POST | Query RAG bloqueante | ⚠ 503 (state.ready nunca se asigna) |
| `/api/v1/query/stream` | POST | Query streaming SSE | ⚠ 503 |
| `/api/v1/ingest` | POST | Dispara la ingesta | ❌ 500 (`await` sobre función sync) |
| `/api/v1/corpus/stats` | GET | Estadísticas del corpus | ⚠ Parcial (solo total_units) |
| `/api/v1/health` | GET | Liveness | ✅ Devuelve `{"status":"alive"}` |
| `/api/v1/health/ready` | GET | Readiness | ❌ Duplicada (routes.py + main.py), 503 siempre |

**Middlewares** (`app/main.py`):
- **CORS**: `allow_origins=["*"]`, con `allow_credentials=True` (configuración por defecto, no lee `FRONTEND_ORIGINS`).
- **CorrelationIDMiddleware**: inyecta `X-Correlation-ID` y lo usa en logs de loguru.

### 2. Capa de Servicios (`app/services/`)

- **`QueryService`** — orquesta el flujo: genera cache key → lee Redis → enruta a `RAGPipeline` (o `LegalAgentGraph` si `use_agent=true`) → cachea la respuesta → añade `processing_time_ms`.
- **`SSEStreamManager`** — convierte el generador async de eventos en frames SSE (`event: <tipo>\n data: {...}\n\n`), con evento `error` ante excepciones.
- **`cache.py`** — wrapper async de Redis (`init_redis`, `get_cached`, `set_cached`). Nota: el servicio llama con una clave ya hasheada y el módulo la re-hashea (doble hash, consistente pero redundante).

### 3. Capa RAG / Agente

#### RAGPipeline (`app/rag/pipeline.py`)
1. `retrieve()` → `RetrievalEngine`
2. Si no hay documentos → respuesta de "contexto insuficiente" (detecta idioma es/ing/pt).
3. `_build_context()` — formatea los documentos en bloques `[N] <id>:\n<texto>` (max 5).
4. Genera un **prompt inline** (no usa `app/prompts/`).
5. `LegalChain.generate()` → `LLMRouter`.
6. Ensambla `QueryResponse` con **risk_matrix e incentivos hardcodeados**.

#### LegalAgentGraph (`app/agents/graph.py`) — ⚠ INCOMPLETO
Grafo LangGraph con 5 nodos:
```
retrieve → analyze ──(needs_refinement && iter<3)──→ refine → retrieve
                  └──(else)──→ risk_assess → finalize → END
```
Problemas que rompen el modo agente:
- `_analyze_node` llama `chain.structured_answer(...)` — **no existe** en `LegalChain`.
- `_risk_assess_node` llama `chain.analyze_risk(...)` — **no existe**.
- `_refine_node` usa `chain.llm.ainvoke(...)` — `LegalChain` no tiene atributo `llm`.
- `QueryService.process_query` pasa `request` (QueryRequest) pero `run()` espera `(question, subsector, tipo_norma)`.

### 4. Pipeline de Recuperación (`app/retrieval/`)

Flujo por query (`RetrievalEngine.retrieve`):

```
Query
  │
  ├─ 1. BM25 (sparse) ──────────────── asyncio: hybrid.bm25.search()
  │     • Tokenizador español legal (stopwords jurídicas)
  │     • Índice construido al inicio desde Qdrant (scroll_all) y
  │       persistido en cache/bm25_index.pkl
  │
  ├─ 2. Dense (vectorial) ──────────── run_in_executor: qdrant.search()
  │     • Embeddings MiniLM-L6-v2 (384-d) → Qdrant búsqueda COSINE
  │     • Filtros Qdrant (payload index) si los hubiera
  │
  ├─ 3. Fusión híbrida ─────────────── HybridRetriever._fusion()
  │     • Normalización min-max por lista
  │     • score = α·bm25_norm + (1-α)·dense_norm
  │     • α adaptativo: 0.7 (código legal) / 0.3 (concepto) / 0.5 default
  │
  ├─ 4. Reranking ──────────────────── Reranker (cross-encoder)
  │     • DESACTIVADO (no-op) para Render Free
  │     • ⚠ await sobre método síncrono → excepción silenciosa → fallback
  │
  └─ 5. Top-K final ────────────────── reranked[:top_k] (default 10, final 5)
```

**MetadataFilter** — mapa keyword→filtro (solar→subsector Solar, ley 1604→norma_id, inversión→enfoque, etc.). Siempre fuerza `vigente: True`. ⚠ Los filtros del `QueryRequest` no se propagan aquí (ver report.md §7.4).

### 5. Capa LLM (`app/llm/`)

- **`LLMRouter`** — lista de proveedores con fallback:
  1. **Groq** (primario): `llama-3.3-70b-versatile` vía `groq` SDK, `temperature=0.1`.
  2. **Gemini** (fallback): `gemini-2.0-flash` vía `google-generativeai`.
- Ante fallo de un proveedor lo añade a `failed_providers` y lo salta en la siguiente llamada; resetea la lista al tener éxito.
- `generate()` es **síncrono** → bloquea el event loop.
- Los clientes SDK se crean en cada llamada (no hay pool).

### 6. Pipeline de Ingestión (`ingestion/`)

```
corpus/raw/*.txt
  │
  ├─ LegalTextNormalizer ── quita headers/footers, normaliza "Art."→"Artículo",
  │                          normaliza IDs de norma (Ley N°, DS)
  ├─ LegalDocumentParser ── patrón por tipo de norma para dividir artículos,
  │                          extrae número de artículo, detecta tipo si falta
  ├─ Metadata Extractor ── risk_flags, subsector, enfoque, tipo_norma, incentivo
  │                          (basado en keywords) + override por CORPUS_DEFINITIONS
  ├─ all_units.json ────── exporta a corpus/normalized/all_units.json
  └─ QdrantStore.upsert ── embeddings en batch → upsert de 32 en 32
                            IDs UUID5(unit.id) → idempotente
```

**CORPUS_DEFINITIONS** (`ingestion/pipeline.py`):

| Archivo | Tipo | ID | Metadata override |
|---------|------|----|-------------------|
| `constitucion_bolivia_articulos_seleccionados.txt` | Constitucion | CPE | subsector General, enfoque Regulacion, risk [Constitutional Hierarchy] |
| `ley_1604_1994.txt` | Ley | 1604 | risk [Market Framework] |
| `ley_943_modificaciones.txt` | Ley | 943 | — |
| `ds_5503_2025.txt` | Decreto Supremo | 5503 | enfoque Inversion, risk [Regulatory Instability, Nationalization Risk] |

> ⚠ `aetn_resoluciones_muestra.txt` existe pero no está en las definiciones.

**Scrapers** (`ingestion/lexivox/`, `ingestion/aetn/`) — clientes httpx async para LexiVox y AETN; implementados pero **no conectados** al pipeline.

### 7. Core / Recursos (`core/`)

- **`embeddings.py`** — singleton thread-safe (`get_embedder()`) con lazy-load del modelo `all-MiniLM-L6-v2` en CPU.
- **`resource_manager.py`** — `ResourceManager.warmup()` carga embedder y Qdrant en paralelo; `embedder()`/`qdrant()` lanzan error si no hubo warmup.

### 8. Vector Store (`vectorstore/qdrant_client.py`)

- `QdrantStore` — wrapper **síncrono** alrededor de `qdrant-client`.
- Colección `energymind`, vectores de 384-d, métrica COSINE.
- Índices de payload: `tipo_norma`, `norma_id`, `subsector`, `enfoque`, `sector` (keyword) + `vigente`, `renewable_incentive` (bool).
- `search()` con `build_filter()` (condiciones MUST) y `scroll_all()` para bootstrap del BM25.

### 9. Modelos de Datos (`app/models/`)

- **`LegalUnit`** — unidad legal (artículo) con metadatos ricos: `id`, `tipo_norma`, `norma_id`, `articulo`, `tema`, `vigente`, `sector`, `subsector`, `enfoque`, `risk_flags`, `renewable_incentive`, `texto`.
- **`QueryRequest`** — `question`, `subsector`, `tipo_norma`, `vigente`, `top_k`, `use_agent`.
- **`QueryResponse`** — `question`, `answer: RegulatoryAnalysis` (direct_conclusion, regulatory_analysis, legal_citations, risk_matrix, incentives_detected, insufficient_context), `sources`, `processing_time_ms`, `cached`.
- **`StructuredLegalResponse`** — schema del agente (sin uso efectivo).

### 10. Frontend (`frontend/`)

- **Next.js 16** con App Router, React 19, TypeScript, Tailwind v4.
- **`lib/api.ts`** — cliente SSE robusto: retries con backoff exponencial (máx. 3), timeout de inactividad (60s), guardas de secuencia `seq`, `Last-Event-Id`, soporte `AbortSignal`.
- **`lib/types.ts`** — contratos TS alineados con el schema del backend (StreamEvent: start, retrieval, analysis, risk, incentives, heartbeat, insufficient_context, complete, error).
- **`chat-interface.tsx`** — vista de chat: modo bloqueante (`use_agent`) o streaming (SSE); render de análisis estructurado.
- **`stats/page.tsx`** — dashboard con métricas y gráficos recharts.
- **`next.config.ts`** — rewrites `/api/:path*` → `${API_URL}` (default localhost:8000).

---

## Flujo de Datos: Ciclo de Vida de una Query

```
1.  Frontend → POST /api/v1/query {question, subsector, tipo_norma, use_agent}
2.  FastAPI (CORS + CorrelationID) → routes.py
3.  get_query_service() → exige app.state.ready ⚠ (nunca se asigna → 503)
4.  QueryService.process_query(request)
5.    → _get_cache_key() (sha256 de question + filtros)
6.    → Redis get_cached (si hit → respuesta cacheada)
7.    → RAGPipeline.query(request)  [o agent.run() — roto]
8.      → RetrievalEngine.retrieve(query, metadata_filter=None ⚠)
9.        → BM25 (async) ‖ Dense vía Qdrant (threadpool)
10.       → HybridRetriever._fusion(alpha adaptativo)
11.       → Reranker (no-op) → top_k
12.     → _build_context(documents[:5])
13.     → LegalChain.generate(prompt) → LLMRouter → Groq → Gemini
14.     → QueryResponse con risk_matrix/incentives hardcodeados
15.  QueryService → Redis set_cached (TTL 3600s)
16.  → JSON al cliente
```

### Flujo SSE (`/query/stream`)

`start` → `retrieval_start` → `retrieval_complete` → `generation_start` → `chunk` (simulado, troceando el texto) → `sources` → `complete`.

> Nota: los tipos de evento documentados en el frontend (`analysis`, `risk`, `incentives`, `heartbeat`, `insufficient_context`) **no son emitidos** por el backend actual; el stream real solo emite `start/retrieval_start/retrieval_complete/generation_start/chunk/sources/complete`.

---

## Arranque y Ciclo de Vida

```
1. uvicorn app.main:app → FastAPI lifespan
2. setup_logging() → loguru con correlation_id
3. lifespan: _warmup_started=True → asyncio.create_task(_background_init)
4. _background_init → ResourceManager.warmup()
      ├─ _load_embedder (threadpool)  — MiniLM-L6-v2
      └─ _load_qdrant                 — QdrantClient + ensure collection
   → _warmup_complete=True (global)
5. ⚠ app.state.ready NUNCA se asigna → todos los endpoints de query dan 503
6. Readiness expuesto por 2 rutas con la misma URL (inconsistente)
```

> El diseño previsto era: warmup en background + gating de readiness (503 → 200) y `QueryService` iniciado en paralelo (`_init_pipeline`, `_init_agent`, `_init_redis`). Esos métodos existen en `QueryService` pero **nunca se invocan** desde el lifespan.

---

## Stack Tecnológico

| Categoría | Tecnología |
|-----------|-----------|
| **Runtime** | Python 3.11.9 |
| **API** | FastAPI 0.115 + uvicorn |
| **RAG** | LangChain 0.2 / LangGraph 0.2 (agente incompleto) |
| **Vector Store** | Qdrant 1.13 (colección `energymind`, COSINE, 384-d) |
| **Embeddings** | sentence-transformers `all-MiniLM-L6-v2` (CPU) |
| **Reranker** | cross-encoder (config) — desactivado |
| **Sparse** | rank-bm25 (BM25Okapi) + tokenizador español |
| **LLM** | Groq `llama-3.3-70b-versatile` → Gemini `gemini-2.0-flash` |
| **Cache** | Redis 7 (async redis-py) |
| **Validation** | Pydantic v2 / pydantic-settings |
| **Logging** | loguru con correlation IDs |
| **Frontend** | Next.js 16, React 19, shadcn/ui, Tailwind v4, recharts |
| **Infra** | Docker Compose, multi-stage Dockerfile, render.yaml |
| **Tests** | pytest + pytest-asyncio |
| **Eval** | RAGAS (script) |

---

## Despliegue

`docker/docker-compose.yml`:

| Servicio | Imagen | Puerto | Volumen |
|----------|--------|--------|---------|
| `qdrant` | qdrant/qdrant:v1.13.2 | 6333 (REST) / 6334 (gRPC) | `qdrant_storage` |
| `redis` | redis:7-alpine | 6379 | `redis_data` |
| `lexenergy-api` | build multi-stage | 8000 | corpus/, logs/ |
| `lexenergy-frontend` | build frontend | 3000 | — |

Notas:
- `lexenergy-api` monta `corpus/` y `logs/`, lee `../.env`, y conecta `host.docker.internal` para Ollama (base de datos LLM local opcional).
- Dockerfile multi-stage: build instala torch CPU y descarga el modelo de embeddings durante el build; la imagen final copia site-packages, caché HF y código.
- ⚠ `Dockerfile` contiene un `HF_TOKEN` hardcodeado (líneas 27 y 56).
- `render.yaml` despliega el API en el plan free de Render.

---

## Estructura del Proyecto

```
energymind/
├── app/                    # Backend FastAPI
│   ├── api/routes.py       # Endpoints REST + SSE
│   ├── rag/                # RAGPipeline, LegalChain, ContextBuilder
│   ├── retrieval/          # BM25, dense, hybrid, reranker, metadata filter
│   ├── agents/graph.py     # Grafo LangGraph (incompleto)
│   ├── llm/                # Proveedores + router con fallback
│   ├── models/             # Schemas Pydantic
│   ├── services/           # QueryService, SSE, Redis cache
│   ├── prompts/            # Plantillas de prompts legales
│   ├── config.py           # Configuración (pydantic-settings)
│   └── main.py             # App FastAPI + lifespan
├── core/                   # Embeddings singleton + ResourceManager
├── ingestion/              # Parsing, normalización, metadata, scrapers
├── vectorstore/            # Wrapper Qdrant
├── corpus/                 # raw / processed / normalized
├── cache/                  # Índice BM25 persistido
├── frontend/               # Next.js 16 (chat + stats)
├── tests/                  # Unit + golden regression
├── evaluation/             # Script RAGAS
└── docker/                 # Dockerfile + docker-compose.yml
```

---

## Divergencias Documentación vs. Implementación

| Documentado (README/arch previos) | Realidad actual |
|-----------------------------------|-----------------|
| BGE-M3 embeddings (1024-d) | `all-MiniLM-L6-v2` (384-d) |
| Tokenización BM25 con jieba | Tokenizador español legal propio |
| Reranker BGE-reranker-large activo | Reranker **desactivado** (no-op) |
| Eventos SSE: analysis/risk/incentives/heartbeat | Solo start/retrieval/generation/chunk/sources/complete |
| Readiness 200 tras warmup | 503 permanente (`app.state.ready` nunca setea) |
| Modo agente funcional | Métodos inexistentes → crash |
| Ingesta vía API | `await` sobre función sync → 500 |
| Risk matrix derivada del contenido | Valores hardcodeados |
| Scrapers LexiVox/AETN conectados | Implementados, no usados |
| RAGAS funcional | Script con API desactualizada |

---

## Diagrama de Secuencia (Ingesta)

```
CLI/API                          IngestionPipeline                    Qdrant
  │  ingest                            │                                │
  ├─► run() ──────────────────────────►│                                │
  │     process_raw_files()            │                                │
  │       para cada CORPUS_DEFINITION  │                                │
  │         parse_file()               │                                │
  │           normalize() → split_articles() → LegalUnit[]             │
  │         aplicar metadata override  │                                │
  │       to_json() → all_units.json   │                                │
  │     index_to_qdrant(units)         │                                │
  │       QdrantStore.initialize() ────┼──────────────────────────────►│
  │       upsert_units(units)          │  embed → upsert batch 32      │
  │                                    │◄──────────────────────────────│
  │◄─ count total ─────────────────────│                                │
```

---

## Referencia Rápida de Archivos Clave

| Archivo | Responsabilidad |
|---------|-----------------|
| `app/main.py` | App FastAPI, lifespan, warmup background, readiness global |
| `app/api/routes.py` | Endpoints, dependency injection del QueryService |
| `app/services/query_service.py` | Orquestación de queries + caché |
| `app/rag/pipeline.py` | Pipeline RAG (retrieve → context → generate) |
| `app/retrieval/engine.py` | Motor de recuperación multi-etapa |
| `app/retrieval/hybrid.py` | Fusión híbrida con alpha adaptativo |
| `app/retrieval/bm25.py` | Índice BM25 español + persistencia |
| `vectorstore/qdrant_client.py` | Wrapper Qdrant (search, upsert, filtros) |
| `ingestion/pipeline.py` | Definición del corpus + flujo de ingesta |
| `core/runtime/resource_manager.py` | Warmup de embedder y Qdrant |
| `frontend/src/lib/api.ts` | Cliente SSE con retries |
| `docker/docker-compose.yml` | Orquestación de servicios |
