# LexEnergy Bolivia — Refactoring Blueprint

## 1. 🔴 Critical Problems

### 1.1 SSE es batch-after-complete, no streaming real

**Archivo:** `app/api/routes.py:119-131`

El endpoint `query_legal_stream` ejecuta `await service.process_query(request)` que **bloquea hasta que todo el pipeline RAG + LLM termina**. Solo después de ese bloqueo emite los eventos SSE. El "streaming" es en realidad batch-con-fan-out: el frontend recibe todos los eventos en milisegundos al final del request.

**Consecuencia:** El usuario ve un spinner de carga por 10-30s sin feedback incremental. Esto invalida el propósito completo del SSE.

### 1.2 Sin orden de eventos — frontend no puede detectar eventos obsoletos

Los eventos SSE no tienen `sequence_number` ni `timestamp`. Si ocurre una retransmisión TCP o reconexión, el frontend no puede determinar si un evento es actual o está desactualizado. En un sistema legal con consecuencias reales, esto es inaceptable.

### 1.3 Frontend nunca aborta al desmontar

**Archivo:** `chat-interface.tsx:60`

`abortRef.current` se almacena pero ningún `useEffect` cleanup llama a `abortRef.current?.abort()`. Si el usuario navega a otra página mientras hay un stream activo, el fetch continúa ejecutándose, `updateLastMessage` se dispara en un componente desmontado, y el `AbortController` nunca se utiliza.

### 1.4 BM25 construido por cada request desde resultados de Qdrant, no desde el corpus completo

**Archivo:** `app/retrieval/engine.py:46-48`

BM25 se construye desde `qdrant_results` — los MEJORES resultados de búsqueda semántica para la query actual. BM25 se usa para re-scorar estos mismos resultados. Esto significa que BM25 opera sobre un subconjunto sesgado (documentos ya relevantes semánticamente), haciendo que la fusión híbrida no tenga sentido.

**Diseño correcto:** BM25 debería indexar el CORPUS COMPLETO y ser consultado independientemente, luego fusionado con los resultados densos.

### 1.5 Cancelación de request nunca se propaga al LLM

Cuando la conexión SSE se pierde, FastAPI `StreamingResponse` detecta la desconexión y detiene la iteración del generador. Sin embargo, la llamada `service.process_query()` dentro del generador NO se cancela. El LLM continúa ejecutándose hasta completar, desperdiciando recursos.

### 1.6 Redis es infraestructura muerta

**Archivo:** `docker-compose.yml`

Redis está declarado en docker-compose y se referencian `REDIS_HOST` y `REDIS_PORT` en settings, pero ningún código en Python se conecta a Redis. Está corriendo pero sin uso.

### 1.7 Modelo de embeddings cargado dos veces (riesgo de OOM)

- `QdrantStore` crea `SentenceTransformer(...)` en `vectorstore/qdrant_client.py:42`
- `DenseRetriever` crea otro `SentenceTransformer(...)` en `app/retrieval/dense.py:11`
- BGE-M3 (~1.8GB) se carga dos veces
- El reranker `BAAI/bge-reranker-large` (~2.2GB) es un tercer modelo
- Memoria total: ~5.5GB solo para modelos

---

## 2. 🟠 Arquitectura Target

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NEXT.JS 16 (App Router)                       │
│  ┌─────────────┐  ┌──────────────────────────────────────────────┐  │
│  │ useReducer  │  │  SSE Client (refactored)                     │  │
│  │ (Messages)  │◄─│  · sequence check                            │  │
│  │             │  │  · deduplication                             │  │
│  │             │  │  · reconnection con Last-Event-Id            │  │
│  │             │  │  · abort on unmount                          │  │
│  └─────────────┘  └──────────────────────────┬───────────────────┘  │
└──────────────────────────────────────────────┼──────────────────────┘
                                               │ POST /api/v1/query/stream
                                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       FASTAPI (uvicorn workers=1)                     │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  SSEStreamManager (NUEVO)                                   │  │
│  │  · emit(event_type, payload) → formatted SSE line            │  │
│  │  · sequence numbers automáticos                              │  │
│  │  · heartbeat cada 15s                                        │  │
│  │  · detecta disconnect del cliente → propaga cancelación      │  │
│  └──────────────────────┬───────────────────────────────────────┘  │
│                         │ asyncio.create_task()                     │
│                         ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  QueryOrchestrator (NUEVO — reemplaza QueryService)          │  │
│  │                                                              │  │
│  │  1. RETRIEVE (paralelo)                                      │  │
│  │     ├── BM25 (índice completo, independiente)                │  │
│  │     ├── Dense (Qdrant, independiente)                        │  │
│  │     └── → emit("retrieval_complete", docs)                   │  │
│  │                                                              │  │
│  │  2. RERANK (Cross-encoder)                                   │  │
│  │     └── → emit("rerank_complete", ranked_docs)               │  │
│  │                                                              │  │
│  │  3. REASON (LangGraph o LLM directo)                         │  │
│  │     ├── Si streaming LLM: emite eventos de token             │  │
│  │     ├── → emit("direct_conclusion", text)                    │  │
│  │     └── → emit("regulatory_analysis", text)                  │  │
│  │                                                              │  │
│  │  4. STRUCTURE (parsear + validar)                             │  │
│  │     ├── → emit("risk_matrix", matrix)                        │  │
│  │     ├── → emit("incentives", info)                           │  │
│  │     └── → emit("citations", list)                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  AsyncTaskQueue (Redis, NUEVO)                               │  │
│  │  · Encola queries largas (modo agente)                       │  │
│  │  · Desacopla HTTP worker de ejecución LLM                    │  │
│  │  · Permite polling de estado                                 │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
     ┌──────────┐  ┌──────────┐  ┌──────────┐
     │ Qdrant   │  │  Ollama  │  │  Redis   │
     │ (vector) │  │  (LLM)   │  │ (queue)  │
     └──────────┘  └──────────┘  └──────────┘
```

### Cambios arquitectónicos clave

1. **SSEStreamManager** — Nueva abstracción que posee el generador async, trackea sequence numbers, detecta desconexión del cliente, y propaga cancelación upstream via `asyncio.Event` o `anyio.CancelScope`.

2. **QueryOrchestrator** — Reemplaza `QueryService`. Desacopla el pipeline en fases awaitable independientes. Cada fase emite eventos tipados a través del `SSEStreamManager`. La llamada LLM se envuelve en `asyncio.create_task()` para que el HTTP handler pueda cancelarla al desconectarse.

3. **AsyncTaskQueue** — Cola Redis-backed para queries largas (modo agente LangGraph). Permite que la API retorne inmediatamente con un `task_id`, y el frontend hace polling o recibe eventos via un endpoint SSE separado. Previene hambre de workers HTTP bajo carga.

4. **EmbeddingService** — Singleton que carga `SentenceTransformer` una sola vez. Tanto `QdrantStore` como `DenseRetriever` lo referencian.

---

## 3. 🟡 Frontend Refactor Plan

### 3.1 `src/lib/types.ts` — Agregar campos de protocolo SSE

```typescript
// Cada variante StreamEvent ahora extiende:
export interface StreamEventBase {
  seq: number
  ts: string  // ISO-8601
  correlation_id: string
}

export interface StreamEventAnalysis extends StreamEventBase {
  event: "analysis"
  payload: { direct_conclusion: string }
}

export interface StreamEventRisk extends StreamEventBase {
  event: "risk"
  payload: { matrix: RiskMatrix }
}

export interface StreamEventIncentives extends StreamEventBase {
  event: "incentives"
  payload: { detected: IncentiveInfo }
}

export interface StreamEventCitations extends StreamEventBase {
  event: "citations"
  payload: { citations: Citation[] }
}

// SSEEvent obsoleto — eliminar
// StreamEvent ahora SIEMPRE lleva seq + ts + correlation_id
```

### 3.2 `src/lib/api.ts` — Refactorizar cliente SSE

**Problemas a resolver:**
1. Sin lógica de reconexión
2. Sin tracking de sequence numbers
3. API basada en callbacks difícil de testear
4. Sin soporte de `Last-Event-Id`
5. Sin timeout por inactividad

**Código target:**

```typescript
export interface SSEStreamOptions {
  onEvent: (event: ValidatedSSEEvent) => void
  onError: (error: SSEError) => void
  onComplete: (final: StreamEventComplete) => void
  signal?: AbortSignal
  maxRetries?: number
  timeoutMs?: number  // default 60000
}

export function streamQuery(
  request: QueryRequest,
  options: SSEStreamOptions
): { cancel: () => void } {
  let retries = 0
  let lastEventId = ""
  let timeoutId: ReturnType<typeof setTimeout>
  const maxRetries = options.maxRetries ?? 3

  const connect = () => {
    const controller = new AbortController()
    const combinedSignal = options.signal
      ? combineAbortSignals(options.signal, controller.signal)
      : controller.signal

    fetch(`${API_BASE}/query/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(lastEventId ? { "Last-Event-Id": lastEventId } : {}),
      },
      body: JSON.stringify(request),
      signal: combinedSignal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(`Stream failed: ${response.status}`)

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      let lastSeq = 0

      const resetTimeout = () => {
        clearTimeout(timeoutId)
        timeoutId = setTimeout(() => {
          controller.abort()
          options.onError({
            code: "TIMEOUT",
            detail: "No SSE event received for 60s",
            recoverable: true,
          })
          if (retries < maxRetries) {
            retries++
            connect()
          }
        }, options.timeoutMs ?? 60000)
      }

      resetTimeout()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() || ""

        let currentId = lastEventId
        let currentData = ""
        let currentEvent = ""

        for (const line of lines) {
          if (line.startsWith("id: ")) {
            currentId = line.slice(4)
          } else if (line.startsWith("event: ")) {
            currentEvent = line.slice(7)
          } else if (line.startsWith("data: ")) {
            currentData = line.slice(6)
          } else if (line === "") {
            // Empty line = end of event
            if (currentData) {
              try {
                const parsed = JSON.parse(currentData)
                const seq = parseInt(currentId, 10)

                // Sequence gate: drop stale events
                if (seq <= lastSeq) continue
                lastSeq = seq
                lastEventId = currentId

                resetTimeout()
                options.onEvent({
                  event: currentEvent || parsed.event,
                  seq,
                  ts: parsed.ts,
                  correlation_id: parsed.correlation_id,
                  payload: parsed.payload,
                })
              } catch {
                // ignore parse errors
              }
            }
            currentData = ""
            currentEvent = ""
          }
        }
      }

      options.onComplete()
    }).catch((err) => {
      if (err.name === "AbortError") return
      options.onError({ code: "NETWORK", detail: err.message, recoverable: true })
      if (retries < maxRetries) {
        retries++
        setTimeout(connect, Math.min(1000 * Math.pow(2, retries), 10000))
      }
    })

    return controller
  }

  const controller = connect()
  return {
    cancel: () => {
      controller.abort()
      clearTimeout(timeoutId)
    },
  }
}
```

### 3.3 `src/components/chat/chat-interface.tsx` — Reemplazar useState con useReducer

**Problema actual:** Tres `useState` separados + objeto `analysis` mutable. Las mutaciones dentro del callback de `streamQuery` capturan closures con valores obsoletos de `filters`. React puede batchear múltiples eventos en un solo render, perdiendo estados intermedios.

**Solución: `useReducer` con acciones atómicas:**

```typescript
// Estado centralizado
interface ChatState {
  messages: Message[]
  isLoading: boolean
  currentQueryId: number | null  // para deduplicación
  filters: FilterValues
}

type ChatAction =
  | { type: "SUBMIT_QUERY"; queryId: number; question: string }
  | { type: "STREAM_EVENT"; event: ValidatedSSEEvent; queryId: number }
  | { type: "STREAM_ERROR"; error: SSEError; queryId: number }
  | { type: "STREAM_COMPLETE"; queryId: number }
  | { type: "SET_FILTERS"; filters: FilterValues }

function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "SUBMIT_QUERY": {
      const userMsg: Message = {
        id: `user-${action.queryId}`,
        role: "user",
        content: action.question,
      }
      const assistantMsg: Message = {
        id: `assistant-${action.queryId}`,
        role: "assistant",
        isLoading: true,
      }
      return {
        ...state,
        messages: [...state.messages, userMsg, assistantMsg],
        isLoading: true,
        currentQueryId: action.queryId,
      }
    }

    case "STREAM_EVENT": {
      // Ignorar eventos de queries anteriores (deduplicación)
      if (action.queryId !== state.currentQueryId) return state

      const messages = [...state.messages]
      const last = { ...messages[messages.length - 1] }

      // Cada evento produce un nuevo estado completo
      // Sin mutación — determinístico
      switch (action.event.event) {
        case "retrieval_complete":
          last.status = { phase: "retrieval", sources: action.event.payload.sources }
          break
        case "direct_conclusion":
          last.analysis = {
            ...(last.analysis || buildEmptyAnalysis()),
            direct_conclusion: action.event.payload.text,
          }
          last.isLoading = false
          break
        case "risk_matrix":
          last.analysis = {
            ...(last.analysis || buildEmptyAnalysis()),
            risk_matrix: action.event.payload.matrix,
          }
          break
        case "citations":
          last.analysis = {
            ...(last.analysis || buildEmptyAnalysis()),
            legal_citations: action.event.payload.citations,
          }
          break
      }

      messages[messages.length - 1] = last
      return { ...state, messages }
    }

    case "STREAM_COMPLETE":
      if (action.queryId !== state.currentQueryId) return state
      return { ...state, isLoading: false, currentQueryId: null }

    case "STREAM_ERROR":
      if (action.queryId !== state.currentQueryId) return state
      // ... set error state

    case "SET_FILTERS":
      return { ...state, filters: action.filters }

    default:
      return state
  }
}
```

**Beneficios:**
- Cada evento SSE produce una transición de estado atómica
- `currentQueryId` previene que eventos de queries anteriores afecten el estado actual (solución al race condition de clicks rápidos)
- Sin objetos mutables compartidos entre closures
- Fácil de testear: `chatReducer(initialState, action) → expectedState`

### 3.4 Agregar abort en unmount

```typescript
export default function ChatInterface() {
  const [state, dispatch] = useReducer(chatReducer, initialState)
  const abortRef = useRef<() => void>(() => {})

  useEffect(() => {
    return () => {
      abortRef.current()  // aborta cualquier stream activo al desmontar
    }
  }, [])

  const handleSubmit = () => {
    const queryId = Date.now()

    dispatch({ type: "SUBMIT_QUERY", queryId, question })

    const { cancel } = streamQuery(request, {
      onEvent: (event) => dispatch({ type: "STREAM_EVENT", event, queryId }),
      onError: (error) => dispatch({ type: "STREAM_ERROR", error, queryId }),
      onComplete: () => dispatch({ type: "STREAM_COMPLETE", queryId }),
      signal, // AbortSignal del componente
    })

    abortRef.current = cancel
  }

  // ...
}
```

### 3.5 Manejar todos los tipos de eventos SSE

El switch actual maneja 4 de 7 tipos de eventos. Agregar handlers para:
- `start` — establecer `correlation_id` (útil para debugging)
- `retrieval_complete` — actualizar indicador de estado ("Searching corpus...", "Found 5 documents")
- `status` — mostrar fase actual al usuario
- `error` — mostrar error con código y opción de reintentar
- `heartbeat` — resetear timeout interno (ignorar visualmente)

---

## 4. 🟡 Backend Refactor Plan

### 4.1 `app/api/routes.py` — Rediseñar endpoint SSE

**Actual (batch):**
```python
async def query_legal_stream(request, fastapi_request, service):
    async def event_stream():
        yield f"data: {json.dumps({'event': 'start', ...})}\n\n"
        yield f"data: {json.dumps({'event': 'retrieval', ...})}\n\n"
        response = await service.process_query(request)  # BLOQUEA AQUÍ
        yield f"data: {json.dumps({'event': 'analysis', ...})}\n\n"
        yield f"data: {json.dumps({'event': 'risk', ...})}\n\n"
        yield f"data: {json.dumps({'event': 'incentives', ...})}\n\n"
        yield f"data: {json.dumps({'event': 'complete', ...})}\n\n"
```

**Target (streaming real):**
```python
@router.post("/query/stream")
async def query_legal_stream(
    request: QueryRequest,
    fastapi_request: Request,
    service: QueryService = Depends(get_query_service),
):
    cid = getattr(fastapi_request.state, "correlation_id", None)
    stream = SSEStreamManager(correlation_id=cid)

    async def event_stream():
        try:
            yield stream.emit("start", {"correlation_id": cid})

            async for sse_event in service.process_query_streaming(request, stream):
                yield sse_event

        except asyncio.CancelledError:
            logger.warning(f"Stream cancelled by client disconnect: {cid}")
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield stream.emit("error", {
                "code": "INTERNAL_ERROR",
                "detail": str(e),
                "recoverable": False,
            })
        finally:
            yield stream.emit("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "X-Correlation-ID": cid or "",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx compat
        },
    )
```

### 4.2 Nuevo módulo: `app/services/sse_manager.py`

```python
import json
import time
import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator


@dataclass
class SSEStreamManager:
    correlation_id: str
    _seq: int = 0
    _cancelled: bool = False
    _disconnect_event: asyncio.Event = field(default_factory=asyncio.Event)
    _heartbeat_task: asyncio.Task | None = None

    async def __aenter__(self):
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return self

    async def __aexit__(self, *args):
        self._cancelled = True
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

    async def _heartbeat_loop(self):
        """Emit heartbeats every 15s to detect disconnect."""
        try:
            while not self._cancelled:
                await asyncio.sleep(15)
                # If the stream is still active, this will succeed
                # If client disconnected, next yield will raise CancelledError
        except asyncio.CancelledError:
            pass

    def emit(self, event_type: str, payload: dict) -> str:
        """Format a single SSE event with sequence number."""
        self._seq += 1
        data = json.dumps({
            "event": event_type,
            "seq": self._seq,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "correlation_id": self.correlation_id,
            "payload": payload,
        }, ensure_ascii=False)
        return (
            f"id: {self._seq}\n"
            f"event: {event_type}\n"
            f"data: {data}\n\n"
        )

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self):
        self._cancelled = True
```

### 4.3 `app/services/query_service.py` — Agregar variante streaming

```python
from typing import AsyncGenerator
from app.services.sse_manager import SSEStreamManager

class QueryService:
    # ... initialize() igual ...

    async def process_query_streaming(
        self,
        request: QueryRequest,
        stream: SSEStreamManager,
    ) -> AsyncGenerator[str, None]:
        """Non-blocking, event-emitting query processor."""

        # ── Phase 1: Retrieval ──────────────────────────────────
        yield stream.emit("status", {
            "phase": "retrieval",
            "message": "Searching legal corpus...",
        })

        metadata_filter = self._build_filter(request)
        retrieval_task = asyncio.create_task(
            self.pipeline.retrieval.retrieve(
                query=request.question,
                metadata_filter=metadata_filter,
                top_k=request.top_k or 5,
            )
        )

        documents, filter_used = await retrieval_task

        if stream.cancelled:
            return

        yield stream.emit("retrieval_complete", {
            "document_count": len(documents),
            "sources": [d.get("id", "") for d in documents],
        })

        if not documents:
            yield stream.emit("insufficient_context", {})
            yield stream.emit("complete", {"processing_time_ms": 0})
            return

        # ── Phase 2: Context + LLM ─────────────────────────────
        yield stream.emit("status", {
            "phase": "analysis",
            "message": "Analyzing legal context...",
        })

        context = self.pipeline.context_builder.build_context(documents)

        try:
            structured = await asyncio.wait_for(
                self.pipeline.chain.structured_answer(
                    request.question, context
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            yield stream.emit("error", {
                "code": "LLM_TIMEOUT",
                "detail": "Analysis timed out after 30s",
                "recoverable": False,
            })
            yield stream.emit("complete", {"processing_time_ms": None})
            return

        if stream.cancelled:
            return

        # ── Phase 3: Emit structured results progressively ─────
        yield stream.emit("direct_conclusion", {
            "text": structured.direct_conclusion,
        })
        yield stream.emit("regulatory_analysis", {
            "text": structured.regulatory_analysis,
        })

        citations = self.pipeline.context_builder.extract_citations(documents)
        yield stream.emit("citations", {"citations": citations})

        if structured.risk_matrix:
            yield stream.emit("risk_matrix", {
                "matrix": structured.risk_matrix.model_dump(),
            })

        if structured.incentives:
            yield stream.emit("incentives", {
                "detected": structured.incentives.model_dump(),
            })

        # ── Phase 4: Complete ──────────────────────────────────
        processing_time = int((time.time() - start_time) * 1000)

        yield stream.emit("complete", {
            "processing_time_ms": processing_time,
            "sources": [d.get("id", "") for d in documents],
        })
```

### 4.4 `app/rag/pipeline.py` — Eliminar métodos estáticos de extracción regex

Los métodos `_extract_section`, `_extract_risk_matrix`, `_extract_incentives` existen porque el modo agente retorna texto plano. Después del refactoring:
- El modo agente debe usar el mismo formato `StructuredLegalResponse` que el pipeline
- Eliminar la extracción regex completamente
- Eliminar los bloques duplicados de construcción de `LegalCitation` (líneas 74-86 y 92-105 son casi idénticas — unificar)

### 4.5 `app/models/schemas.py` — Unificar field names

**Problema:** `StructuredLegalResponse` tiene `incentives` (`IncentiveInfo`), mientras que `RegulatoryAnalysis` tiene `incentives_detected` (`IncentiveInfo`). El pipeline mapea `structured.incentives → analysis.incentives_detected`. Esta capa de mapeo no debería existir.

**Fix:**
```python
class StructuredLegalResponse(BaseModel):
    direct_conclusion: str
    regulatory_analysis: str
    risk_matrix: RiskMatrix
    incentives_detected: IncentiveInfo  # rename from 'incentives'
    insufficient_context: bool = False
```

### 4.6 Nueva singleton: `app/services/embedding_service.py`

```python
from sentence_transformers import SentenceTransformer
from app.config import settings

_embedder: SentenceTransformer | None = None
_embedder_model_name: str | None = None


def get_embedder() -> SentenceTransformer:
    global _embedder, _embedder_model_name

    if _embedder is None or _embedder_model_name != settings.embeddings_model:
        _embedder = SentenceTransformer(
            settings.embeddings_model,
            device=settings.embeddings_device,
            trust_remote_code=True,
        )
        _embedder_model_name = settings.embeddings_model

    return _embedder
```

**Cambios en otros archivos:**
- `vectorstore/qdrant_client.py:42` — reemplazar `SentenceTransformer(...)` por `get_embedder()`
- `app/retrieval/dense.py:11` — reemplazar `SentenceTransformer(...)` por `get_embedder()`

### 4.7 `app/retrieval/engine.py` — BM25 sobre corpus completo + paralelismo

```python
class RetrievalEngine:
    async def initialize(self):
        await self.qdrant.initialize()
        all_docs = await self.qdrant.scroll_all()  # NUEVO método
        self.hybrid.bm25.build_index(all_docs)
        self.hybrid.bm25.save(BM25_INDEX_PATH)
        logger.info(f"BM25 index built from {len(all_docs)} corpus documents")

    async def retrieve(self, query, metadata_filter=None, top_k=10):
        qdrant_filter = self.hybrid.metadata_filter.infer_from_query(
            query, metadata_filter
        )

        # BM25 y Dense en PARALELO
        bm25_task = asyncio.create_task(
            self.hybrid.bm25.search(query, top_k=settings.bm25_top_k)
        )
        dense_task = asyncio.create_task(
            self.qdrant.search(query, qdrant_filter, top_k=top_k * 2)
        )

        bm25_results, dense_results = await asyncio.gather(
            bm25_task, dense_task
        )

        # Fusion híbrida
        fused = self.hybrid.fusion(bm25_results, dense_results)

        # Si hay resultados, rerankear
        if fused:
            reranked = await self.hybrid.reranker.rerank(
                query, fused, top_k=settings.final_top_k
            )
            return reranked, qdrant_filter

        return fused[:settings.final_top_k], qdrant_filter
```

### 4.8 `vectorstore/qdrant_client.py` — Agregar `scroll_all()`

```python
async def scroll_all(self, batch_size: int = 100) -> List[Dict[str, Any]]:
    """Scroll through all points in the collection."""
    if not self.client:
        raise RuntimeError("QdrantStore not initialized")

    all_points = []
    next_offset = None

    while True:
        results = self.client.scroll(
            collection_name=self.collection_name,
            limit=batch_size,
            offset=next_offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = results

        for p in points:
            all_points.append({
                "id": p.payload.get("id", ""),
                "texto": p.payload.get("texto", ""),
                "payload": p.payload,
            })

        if next_offset is None:
            break

    logger.info(f"Scrolled {len(all_points)} points from Qdrant")
    return all_points
```

---

## 5. 🟡 Infraestructura (Docker)

### 5.1 `docker/docker-compose.yml` — Cambios

```yaml
services:
  qdrant:
    image: qdrant/qdrant:v1.13.2
    restart: unless-stopped
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 30s

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --save 60 1
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  lexenergy-api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ../corpus:/app/corpus
      - ../logs:/app/logs
      - ../cache:/app/cache
    env_file:
      - ../.env
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      QDRANT_HOST: qdrant
      QDRANT_PORT: 6333
      REDIS_HOST: redis
      REDIS_PORT: 6379
      OLLAMA_BASE_URL: http://host.docker.internal:11434
      # Workers=1 es obligatorio: embedding model + BM25 index
      # son singletons in-process. Con workers>1 se duplica memoria.
      API_WORKERS: 1
    depends_on:
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: "4"
    # NO usar --workers > 1 (ver arriba)
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

  lexenergy-ui:
    build:
      context: ../frontend
      dockerfile: docker/frontend.Dockerfile
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://lexenergy-api:8000
    depends_on:
      - lexenergy-api
    restart: unless-stopped

volumes:
  qdrant_storage:
  redis_data:
```

### 5.2 Nuevo `docker/frontend.Dockerfile`

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS production
WORKDIR /app
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/package*.json ./
RUN npm ci --only=production
EXPOSE 3000
CMD ["npm", "start"]
```

### 5.3 Redis — Primer uso como cola de tareas

Para queries en modo agente (LangGraph, puede tomar 30-60s):

```python
# app/services/task_queue.py
import json
import uuid
import redis.asyncio as aioredis
from app.config import settings


class QueryTaskQueue:
    def __init__(self):
        self.redis: aioredis.Redis | None = None

    async def initialize(self):
        self.redis = await aioredis.from_url(
            f"redis://{settings.redis_host}:{settings.redis_port}",
            decode_responses=True,
        )

    async def enqueue(self, request: dict) -> str:
        task_id = str(uuid.uuid4())[:8]
        await self.redis.lpush(
            "query:queue",
            json.dumps({"task_id": task_id, "request": request}),
        )
        return task_id

    async def get_result(self, task_id: str) -> dict | None:
        result = await self.redis.get(f"query:result:{task_id}")
        return json.loads(result) if result else None

    async def set_result(self, task_id: str, result: dict, ttl: int = 300):
        await self.redis.setex(f"query:result:{task_id}", ttl, json.dumps(result))
```

---

## 6. 🧠 Especificación del Protocolo SSE (Diseño Final)

### 6.1 Formato Wire

Cada evento SSE sigue el estándar RFC 8895:

```
id: <sequence_number>
event: <event_type>
data: <JSON payload>

```

El campo `id` permite reconexión con `Last-Event-Id`. El campo `event` permite que el EventSource API use listeners tipados.

### 6.2 Tipos de Evento y Payloads

| Event Type | Payload | Cuándo |
|---|---|---|
| `start` | `{ "correlation_id": str }` | Inmediatamente al conectar |
| `heartbeat` | `{}` | Cada 15s |
| `status` | `{ "phase": str, "message": str }` | Transiciones de fase |
| `retrieval_complete` | `{ "document_count": int, "sources": str[] }` | Después de retrieval |
| `direct_conclusion` | `{ "text": str }` | Después de LLM (conclusión) |
| `regulatory_analysis` | `{ "text": str }` | Después de LLM (análisis) |
| `risk_matrix` | `{ "matrix": RiskMatrix }` | Después de extracción de riesgos |
| `incentives` | `{ "detected": IncentiveInfo }` | Después de detección de incentivos |
| `citations` | `{ "citations": Citation[] }` | Lista final de citas |
| `insufficient_context` | `{}` | Cuando no hay documentos relevantes |
| `error` | `{ "code": str, "detail": str, "recoverable": bool }` | En fallo |
| `complete` | `{ "processing_time_ms": int, "sources": str[] }` | Éxito |
| `done` | `{}` | Fin de stream (siempre, incluso en error) |

### 6.3 Reglas de Sequence Number

- Comienza en 1 por conexión.
- Monotónicamente incremental. Sin gaps.
- Frontend descarta eventos con `seq <= lastReceivedSeq`.
- En reconexión, frontend envía header `Last-Event-Id: <lastSeq>`.
- Backend reenvía eventos desde `lastSeq + 1` si están bufferizados (Redis-backed, TTL 5 min).
- Si los eventos ya no están bufferizados, backend envía `error` con `recoverable: false` y el cliente debe re-consultar.

### 6.4 Máquina de Estados del Cliente

```
IDLE
  │
  ├── submit query
  │
  ▼
CONNECTING
  │
  ├── success
  │
  ▼
STREAMING ◄────────────────────┐
  │                            │
  ├── heartbeat ───────────────┘  (resetea timeout)
  │                            │
  ├── error recoverable ───────┘  (reconexión con backoff)
  │                            │
  ├── error fatal ────→ IDLE     (muestra error, no reconecta)
  │
  ├── complete ───────→ IDLE     (respuesta completa)
  │
  └── timeout 60s ────→ RECONNECTING ──→ STREAMING (si retry < max)
                                  │
                                  └──→ IDLE (si retry >= max)
```

---

## 7. 🔧 Plan de Migración por Fases

### Fase 1 — Fix SSE + Frontend State (2-3 días)

| Paso | Archivo | Cambio |
|---|---|---|
| 1 | `app/services/sse_manager.py` | Crear clase `SSEStreamManager` |
| 2 | `app/api/routes.py` | Reemplazar `event_stream()` inline con `SSEStreamManager` |
| 3 | `frontend/src/lib/types.ts` | Agregar `seq`, `ts`, `correlation_id` a todos los `StreamEvent` |
| 4 | `frontend/src/lib/api.ts` | Agregar validación de secuencia, reconexión, `Last-Event-Id`, timeout |
| 5 | `frontend/src/components/chat/chat-interface.tsx` | Agregar abort en unmount (`useEffect` cleanup) |
| 6 | `frontend/src/components/chat/chat-interface.tsx` | Reemplazar `useState` con `useReducer` (acciones atómicas) |
| 7 | `frontend/src/components/chat/chat-interface.tsx` | Manejar todos los tipos de eventos SSE (no solo 4) |

**Validación:** Eventos SSE llegan progresivamente (no en batch), frontend ignora eventos obsoletos, desmontar componente aborta fetch.

### Fase 2 — Desacoplar LangGraph + Streaming Real (3-4 días)

| Paso | Archivo | Cambio |
|---|---|---|
| 1 | `app/services/query_orchestrator.py` | Crear `QueryOrchestrator` — generador async por fase |
| 2 | `app/services/query_service.py` | Agregar `process_query_streaming()` |
| 3 | `app/api/routes.py` | Conectar `query_legal_stream` a `process_query_streaming` |
| 4 | `app/rag/pipeline.py` | Eliminar extracción regex, unificar bloques duplicados |
| 5 | `app/models/schemas.py` | Renombrar `incentives` → `incentives_detected` en `StructuredLegalResponse` |
| 6 | `app/agents/graph.py` | Opcional: método `stream()` que emite eventos por nodo LangGraph |
| 7 | `app/services/sse_manager.py` | Propagar disconnect → cancelar LLM via `asyncio.Task.cancel()` |

**Validación:** SSE endpoint emite eventos progresivamente por fase completa. Modo agente LangGraph también stremea. Desconexión del cliente detiene LLM en <15s.

### Fase 3 — Redis + Concurrencia (2-3 días)

| Paso | Archivo | Cambio |
|---|---|---|
| 1 | `app/services/task_queue.py` | Crear `QueryTaskQueue` (Redis-backed) |
| 2 | `app/config.py` | Agregar `redis_host`, `redis_port` |
| 3 | `docker/docker-compose.yml` | Conectar Redis a API, healthchecks, `deploy.resources` |
| 4 | `docker/frontend.Dockerfile` | Crear Dockerfile para frontend |
| 5 | `app/api/routes.py` | Agregar `POST /api/v1/query/async` → retorna `task_id` |
| 6 | `app/api/routes.py` | Agregar `GET /api/v1/query/async/{task_id}/stream` → SSE para tarea |
| 7 | `frontend/src/components/chat/chat-interface.tsx` | Soportar polling + SSE asíncrono para modo agente |

**Validación:** Queries de agente no bloquean workers HTTP. Múltiples queries concurrentes se encolan y procesan secuencialmente.

### Fase 4 — Optimización RAG (2-3 días)

| Paso | Archivo | Cambio |
|---|---|---|
| 1 | `app/services/embedding_service.py` | Crear singleton `get_embedder()` |
| 2 | `vectorstore/qdrant_client.py` | Usar `get_embedder()` en vez de instancia propia |
| 3 | `app/retrieval/dense.py` | Usar `get_embedder()` en vez de instancia propia |
| 4 | `vectorstore/qdrant_client.py` | Agregar `scroll_all()` |
| 5 | `app/retrieval/engine.py` | BM25 desde corpus completo al iniciar, no por request |
| 6 | `app/retrieval/engine.py` | BM25 + dense en paralelo con `asyncio.gather` |
| 7 | `docker/docker-compose.yml` | Cache volume para BM25 index persistente |

**Validación:** Memoria baja de ~5.5GB a ~3.5GB. BM25 indexa corpus completo. Latencia de retrieval baja por paralelismo.

---

## 8. ⚠️ Análisis de Riesgos en Producción

### Bajo Carga (10+ usuarios concurrentes)

| Riesgo | Impacto | Mitigación |
|---|---|---|
| **Ollama queue overflow** | Requests se encolan, timeouts en cascada | Redis task queue con max concurrency (ej. 2 LLM calls concurrentes). Retornar `429 Too Many Requests` cuando queue depth > 100. |
| **Qdrant connection pool exhaustion** | Fallos en queries | Configurar `qdrant_client` con max pool size (mínimo 10). Usar connection pooling. |
| **Embedding model contention** | Dense retrieval bloquea BM25 o viceversa | Ya resuelto en Fase 4 (paralelo con `asyncio.gather`). Sin contención de threads. |
| **SSE connection leak** | FD exhaustion, API no responde | Set `StreamingResponse` timeout. Cerrar conexiones después de 5min. Agregar métrica de conexiones activas. |

### Race Conditions

| Ubicación | Escenario | Fix |
|---|---|---|
| `updateLastMessage` + eventos SSE rápidos | React batchea dos state updates en un render, perdiendo estado intermedio | `useReducer` con acciones atómicas. Cada evento SSE produce un estado completo nuevo. |
| Reconexión SSE + eventos en vuelo | Frontend aplica evento obsoleto después de reconexión | Sequence number gate: descartar `seq <= lastSeq`. Backend reenvía desde último seq conocido vía Redis buffer. |
| Dos queries simultáneas | `isLoading` guard es un solo booleano — race con clicks rápidos | `currentQueryId` (contador incremental). Solo aceptar eventos para el `queryId` actual. Rechazar respuestas obsoletas. |
| Rebuild de índice BM25 durante ingesta | Índice en estado inconsistente | Patrón read-copy-update: construir nuevo índice, atomicamente swappear referencia. |

### Inconsistencia de Datos

| Riesgo | Escenario | Mitigación |
|---|---|---|
| **Corpus desactualizado** | Qdrant y BM25 index divergen después de ingesta | Después de ingesta completada, reindexar BM25. Agregar version hash al metadata del índice. Rechazar queries si hash no coincide. |
| **Entrega SSE parcial** | Cliente recibe "direct_conclusion" pero no "risk_matrix" | Frontend trata evento "complete" como señal de que todos los datos llegaron. Si faltan campos → re-consultar o mostrar warning. |
| **Colisión de Correlation ID** | 8-char hex UUID no es resistente a colisiones | Usar UUID4 completo de 36 caracteres. Solo truncar para display, no para correlación. |

### Escenarios de Falla SSE

| Falla | Comportamiento | Fix |
|---|---|---|
| **TCP disconnect mid-stream** | Backend detecta en próximo `write()` → `BrokenPipeError` | Catch en generador SSE → cancelar LLM via `asyncio.Task.cancel()`. |
| **Backend crash mid-stream** | Frontend ve SSE incompleto → se queda en estado STREAMING | Timeout en frontend: si no recibe evento por 60s, transicionar a ERROR y ofrecer re-consulta. |
| **Ollama timeout (30s)** | Generador SSE lanza `TimeoutError` → evento de error SSE | `error.recoverable = false`. Frontend muestra "LLM timed out" con resultados parciales de retrieval. |
| **SSE buffer overflow** | Respuesta grande (>1MB) causa OOM en reader del frontend | Limitar tamaño de respuesta a 100KB por sección de análisis. Si el LLM genera más, truncar. |
| **Proxy buffering (nginx)** | Eventos SSE son buffereados y entregados en batch | Set `X-Accel-Buffering: no` y `proxy_buffering off` en nginx. Usar chunked transfer encoding. |
