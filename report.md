# EnergyMind — Informe de Análisis del Proyecto

## 1. Resumen del Proyecto

**EnergyMind** (también llamado **LexEnergy Bolivia**) es un sistema de **RAG (Retrieval-Augmented Generation) de dominio específico** para la regulación energética boliviana. Combina recuperación semántica con Qdrant y recuperación léxica con BM25, procesa documentos legales a nivel de artículos, y utiliza una arquitectura LLM multi-proveedor para generación resiliente. El sistema retorna fuentes rastreables y, importantemente, puede **abstenerse** cuando la evidencia recuperada no soporta una respuesta.

> **El desafío principal** fue hacer que documentos legales heterogéneos fueran recuperables de forma confiable a nivel de artículos, preservando la procedencia y evitando alucinaciones. Esto se resolvió combinando recuperación densa y léxica, metadatos legales estructurados, y una capa LLM restringida por la evidencia recuperada.

### Propósito
Reducir el tiempo de investigación legal de horas a segundos, entregando respuestas estructuradas con citas legales verificadas, matriz de riesgos y detección de incentivos renovables.

---

## 2. Contexto de Negocio

| Aspecto | Detalle |
|---------|---------|
| **Segmento** | Abogados, consultores energéticos, inversionistas |
| **Monetización** | Freemium: $0 / $29 / $99 por mes |
| **Propuesta de valor** | Reducción del 90% en tiempo de investigación |
| **Métricas objetivo** | >95% precisión de fuentes, <2% alucinaciones, <3s respuesta |

El código cubre la base funcional del pitch (RAG, streaming, citaciones, riesgo) pero **no implementa** muchas promesas premium: exportación PDF/Word, score de confianza, multi-tenant, auditoría, rate limiting.

---

## 3. Stack Tecnológico (estado actual del código)

| Categoría | Tecnología | Notas |
|-----------|-----------|-------|
| **Runtime** | Python 3.11.9 | `runtime.txt`, `pyproject.toml` |
| **API** | FastAPI 0.115 + uvicorn | Con lifespan, CORS, correlation ID |
| **RAG / Agente** | LangChain / LangGraph 0.2 | Agente parcialmente implementado |
| **Vector Store** | Qdrant 1.13 | Colección `energymind`, distancia COSINE |
| **Embeddings** | `all-MiniLM-L6-v2` (384-d) | Se abandonó BGE-M3 por memoria en Render Free |
| **Reranker** | Cross-encoder (config) | **Desactivado** en `reranker.py` (memoria) |
| **Sparse** | BM25Okapi (`rank-bm25`) | Tokenizador español propio (reemplazó jieba) |
| **LLM** | Router custom: **Groq** (Llama 3.3 70B) → **Gemini** 2.5 Flash | Fallback automático |
| **Cache** | Redis 7 (async) | TTL 1h, doble hash de clave |
| **Frontend** | Next.js 16 + React 19 + shadcn/ui + Tailwind v4 | SSE robusto con retries |
| **Infra** | Docker Compose, multi-stage Dockerfile, render.yaml | Objetivo: Render Free (512MB) |
| **Tests / Eval** | pytest + pytest-asyncio, RAGAS | Varios tests desactualizados |

---

## 4. Estructura del Código

```
app/
├── api/routes.py          # Endpoints REST + SSE (query, query/stream, ingest, stats, health)
├── rag/
│   ├── pipeline.py        # RAGPipeline: retrieve → context → LLM generate
│   ├── chain.py           # LegalChain: wrapper del LLMRouter + detección de idioma
│   └── context_builder.py # Contexto LLM con metadatos + extracción de citas
├── retrieval/
│   ├── engine.py          # Orquestador multi-etapa (BM25 + dense + fusion + rerank)
│   ├── bm25.py            # BM25Okapi + tokenizador español legal + persistencia
│   ├── dense.py           # DenseRetriever (embeddings + numpy local)
│   ├── hybrid.py          # Fusión con alpha adaptativo + normalización min-max
│   ├── reranker.py        # DESACTIVADO (no-op)
│   └── metadata_filter.py # Inferencia de filtros desde keywords de la query
├── agents/graph.py        # LegalAgentGraph (LangGraph) — INCOMPLETO
├── llm/                   # providers.py (Groq, Cloudflare, Gemini, Ollama) + router.py (fallback)
├── models/                # schemas.py, legal_unit.py (Pydantic)
├── services/              # query_service.py, cache.py, sse_manager.py
├── prompts/               # Plantillas de prompts legales (español)
├── config.py              # Pydantic Settings (.env)
└── main.py                # FastAPI app, lifespan, warmup en background

core/                      # embeddings.py (singleton), runtime/resource_manager.py
ingestion/                 # parsing, normalization, metadata, scrapers (LexiVox, AETN)
vectorstore/               # qdrant_client.py (wrapper sincrónico)
corpus/                    # raw/, normalized/all_units.json
frontend/                  # Next.js 16 (chat, stats, componentes shadcn/ui)
tests/                     # unit + golden regression
evaluation/                # run_ragas_eval.py
docker/                    # Dockerfile + docker-compose.yml
```

---

## 5. Análisis del Corpus

- **Total de unidades legales:** 45
  - Constitución: 9 | Ley: 26 | Decreto Supremo: 10
  - Subsector: **100% "General"** (el override de metadatos en `CORPUS_DEFINITIONS` sobrescribe lo extraído por keywords)
  - Unidades con `renewable_incentive`: 12
  - Unidades con `risk_flags`: 37

> Nota: `corpus/raw/aetn_resoluciones_muestra.txt` existe pero **no está en `CORPUS_DEFINITIONS`**, por lo que las resoluciones AETN no se indexan.

---

## 6. Fortalezas

**Arquitectura y diseño**
- Separación clara de capas: API → Servicios → RAG/Agente → Retrieval → Infraestructura.
- Pipeline de retrieval bien definido con fallbacks en cada etapa.
- Singleton de embeddings (`core/embeddings.py`) con lock de hilos — evita recarga de modelo.
- Router LLM multi-provider con fallback automático y blacklist de proveedores fallidos (Groq → Cloudflare → Gemini → Ollama).
- Filtro de metadatos inferido del texto (ej. "solar" → `subsector: Solar`).
- **Abstención**: el sistema puede declarar `insufficient_context` cuando la evidencia es débil, en vez de alucinar.

**Rendimiento / asincronía**
- BM25 CPU-bound ejecutado fuera del event loop (thread pool via `asyncio.to_thread()`).
- Warmup paralelo de embedder y Qdrant al arranque (`asyncio.gather`).
- Gating de readiness (503) mientras se calientan recursos.
- Caché Redis para queries repetidas.

**Calidad de retrieval**
- Fusión híbrida con **alpha adaptativo**: 0.7 para queries de código legal, 0.3 para conceptos.
- Tokenizador español legal específico (stopwords jurídicas) en BM25.
- Índice BM25 persistido (`cache/bm25_index.pkl`) con rebuild automático.
- Índices de payload en Qdrant para filtros (tipo_norma, subsector, etc.).

**Testing / Evaluación**
- Golden set de 10 queries legales con IDs de documento esperados y assertions de keywords.
- Script RAGAS para faithfulness / answer relevancy / context precision / recall.

**Developer Experience**
- `docker-compose` completo (Qdrant, Redis, API, Frontend).
- Dockerfile multi-stage (build con torch CPU → imagen runtime ligera).
- Logging estructurado con `loguru` + correlation IDs.
- Config centralizada con Pydantic Settings.

---

## 7. Problemas Críticos (bugs reales en el código actual)

### 7.1 `app.state.ready` y `app.state.query_service` nunca se asignan
En `app/main.py`, el lifespan lanza `_background_init(rm)` que llama `rm.warmup()`, pero **nunca** se asigna `app.state.ready = True` ni `app.state.query_service`. Sin embargo:
- `app/api/routes.py:15` en `get_query_service()` exige `app.state.ready` → **toda query devuelve 503**.
- `app/api/routes.py:83` readiness devuelve **503 siempre**.
- Además hay una **ruta duplicada** `/api/v1/health/ready`: definida en `routes.py` (vía router) y en `main.py` a nivel de app. Se registra primero la del router, que siempre da 503.

### 7.2 Agente LangGraph incompleto (crash en runtime)
`app/agents/graph.py` invoca métodos que **no existen** en `LegalChain`:
- `graph.py:96` → `chain.structured_answer(...)`
- `graph.py:104` → `chain.analyze_risk(...)`
- `graph.py:112` → `chain.llm.ainvoke(...)`
- `query_service.py:101` llama `self.agent.run(request)` pasando un `QueryRequest`, pero `run()` espera `(question, subsector, tipo_norma)`.

**Cualquier consulta con `use_agent=true` fallará.**

### 7.3 Ingestion endpoint rompe por `await` sobre función síncrona
`app/api/routes.py:98`: `count = await run_ingestion()`. `ingestion/pipeline.py:run_ingestion()` es **síncrono** y retorna `int`. `await` sobre un `int` lanza `TypeError` → `/api/v1/ingest` siempre responde 500.

### 7.4 Filtros del request ignorados
`QueryRequest` expone `subsector`, `tipo_norma`, `vigente`, pero el pipeline usa `getattr(request, 'metadata_filter', None)` (campo inexistente → siempre `None`). Los filtros elegidos por el usuario **nunca llegan** al retrieval.

### 7.5 Reranker desactivado + `await` sobre método síncrono
- `reranker.py` tiene `disabled = True` (no-op por memoria en Render).
- Aun así `engine.py:121` y `hybrid.py` hacen `await self.hybrid.reranker.rerank(...)` sobre un método **síncrono**; el `TypeError` resultante se captura y cae al fallback silenciosamente.

### 7.6 Token HF hardcodeado en Dockerfile
`Dockerfile:27,56` expone un `HF_TOKEN` real en el código. **Fuga de credencial** — debe rotarse y moverse a secretos.

### 7.7 Readiness duplicado e inconsistente
`main.py` define `/api/v1/health/ready` con globals `_warmup_complete`; `routes.py` lo redefine con `app.state.ready`. Resultado: comportamiento contradictorio y 503 permanente.

### 7.8 Suite de tests desactualizada
- `tests/test_api.py` espera `{"status":"healthy","service":"LexEnergy Bolivia"}` pero la ruta devuelve `{"status":"alive"}`.
- `tests/test_startup.py` usa `rm.is_ready` y `rm.wait_ready()`, atributos/métodos que **no existen** en `ResourceManager`.
- `tests/test_retrieval_golden.py` omite el test denso (CVE de torch) y asume IDs del corpus que no coinciden con la estructura real de IDs generada (ej. `Ley_18_art_18_bis` vs `Ley_1604_art_18`).

---

## 8. Áreas de Mejora

**Integración LLM**
- `LegalChain.generate()` es síncrono → bloquea el event loop durante llamadas al LLM (2-10s).
- El streaming de `query_stream()` trocea texto ya generado; no hay streaming real de tokens del proveedor.
- Los clientes de Groq/Gemini se re-crean en cada `generate()` (sin reutilización).

**Prompt / Salida estructurada**
- `pipeline.py` construye su propio prompt inline e ignora `app/prompts/legal_prompts.py`.
- La **matriz de riesgos y los incentivos están hardcodeados** con valores por defecto (`pipeline.py:94-107`); nunca se derivan del contenido recuperado. El contrato del schema (`legal_citations`, risk_matrix, incentives) no se llena correctamente.

**Retrieval**
- `dense.py` hace búsqueda vectorial local con numpy sobre los documentos recibidos (camino legacy de `hybrid.retrieve_with_results`), aunque `engine.py` sí usa la búsqueda real de Qdrant.
- El reranker no está operativo a pesar de documentarse BGE-reranker-large.
- `metadata_filter.py` siempre inyecta `vigente: True` y la inferencia es un mapa de keywords simple.

**Operaciones / Observabilidad**
- `corpus/stats` devuelve `{"total_units": N, "documents": {}}` — el frontend de stats espera `by_norm_type`, `by_subsector`, `risk_flags`, etc.
- No hay health checks de dependencias (Qdrant/Redis) tras el arranque.
- `prometheus-client` figura en dependencias del README pero no se usa.
- Script RAGAS roto: llama `pipeline.query(question=...)` con firma `query(request)`, usa `c.texto` sobre citas que el pipeline nunca puebla, y la API de `ragas_evaluate` difiere.

**Ingestion**
- `aetn_resoluciones_muestra.txt` no se procesa.
- Los scrapers LexiVox/AETN existen pero no están conectados al pipeline.

---

## 9. Recomendaciones Priorizadas

### Críticas (para que la API funcione)
1. Asignar `app.state.ready` y `app.state.query_service` en el lifespan y eliminar la ruta duplicada de readiness.
2. Corregir `/ingest`: hacer `run_ingestion` async o quitar el `await`.
3. Completar o deshabilitar el modo agente (implementar `structured_answer`/`analyze_risk` o devolver 501).
4. Rotar y quitar el `HF_TOKEN` del Dockerfile; usar secretos/`ARG`.
5. Propagar `subsector/tipo_norma/vigente` del request al filtro de metadata.
6. Hacer async la generación del LLM (`AsyncClient`/`agenerate`) para no bloquear el event loop.

### Alta
7. Derivar la risk matrix e incentivos del contenido recuperado (no defaults).
8. Unificar la estrategia de prompts usando `app/prompts/` + `ContextBuilder`.
9. Eliminar el `await` sobre el reranker síncrono o activarlo con modelo ligero.
10. Actualizar la suite de tests a los contratos reales (health, ResourceManager, IDs del corpus).
11. Completar `corpus/stats` para alimentar la página de stats del frontend.

### Media
12. Streaming real de tokens desde el proveedor LLM.
13. Reutilizar clientes LLM (pooling) en vez de instanciar por llamada.
14. Indexar resoluciones AETN y conectar scrapers al pipeline.
15. Añadir health checks de dependencias y métricas Prometheus.

### Baja
16. Export PDF/Word, score de confianza, multi-tenant, rate limiting (promesas del business pitch).

---

## 10. Diagrama de Arquitectura

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                                  │
│   Next.js 16 + React 19 + shadcn/ui (SSE con retries)               │
├──────────────────────────────────────────────────────────────────────┤
│                       API LAYER · FastAPI :8000                       │
│   query · query/stream · ingest · stats · health                     │
├──────────────────────────────────────────────────────────────────────┤
│                      SERVICE LAYER                                    │
│   QueryService → Redis Cache → SSE Manager                           │
├──────────────────────────────────────────────────────────────────────┤
│                       RAG LAYER                                       │
│   RAGPipeline: retrieve → context → generate (abstains if weak)     │
│   LegalAgentGraph: retrieve → analyze → refine → risk → finalize    │
├──────────────────────────────────────────────────────────────────────┤
│                    RETRIEVAL ENGINE                                    │
│   BM25 (sparse/español) ‖ Dense (Qdrant/MiniLM-L6)  → Fusion (α)   │
│   → Reranker (disabled) → Top-K (10→5)                              │
├──────────────────────────────────────────────────────────────────────┤
│                       LLM LAYER                                       │
│   Groq (Llama 3.3 70B) → Cloudflare → Gemini → Ollama               │
├──────────────────────────────────────────────────────────────────────┤
│                    INFRASTRUCTURE                                      │
│   Qdrant (vector) · Redis (cache) · Embeddings (CPU) · Corpus (45)  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 11. Conclusión

EnergyMind es un proyecto con **buena arquitectura conceptual**: pipeline de retrieval multi-etapa con fallbacks, router LLM con failover, warmup asíncrono, caché y un frontend moderno con SSE robusto. El diseño de capas es limpio y el tokenizador español propio de BM25 es un acierto.

El sistema aborda el **desafío central** de la regulación energética boliviana — hacer documentos legales heterogéneos recuperables de forma confiable a nivel de artículos — mediante una combinación de recuperación densa y léxica, metadatos legales estructurados, y una capa LLM restringida por evidencia. La capacidad de **abstención** (campo `insufficient_context`) es una característica clave que previene alucinaciones.

Sin embargo, el estado actual del código presenta **divergencias importantes entre la documentación y la implementación**, y varios defectos que impiden su operación real:
1. La **API responde 503 en todas las consultas** (`app.state.ready` nunca se setea).
2. El **modo agente no funciona** (métodos inexistentes).
3. El endpoint de **ingest está roto**.
4. La **matriz de riesgos e incentivos son placeholders** hardcodeados.
5. Hay una **fuga de credencial** en el Dockerfile.

Estos son problemas de integración y pulido, no de diseño: el esqueleto es sólido y los defectos son corregibles con esfuerzo moderado. Priorizando los puntos 9.1–9.6 se puede llevar el sistema a un estado funcional end-to-end.

---

*Fecha del análisis: 2026-08-18. Basado en el estado actual del repositorio.*
