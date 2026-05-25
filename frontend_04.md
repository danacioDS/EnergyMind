# LexEnergy Bolivia — Frontend 04: Production Hardening & SSE Resilience

## 1. Audit Against Specification

Comparación del estado actual del frontend contra la especificación `frontend_03.md`:

| Requisito | Estado | Acción |
|---|---|---|
| `seq`-based ordering (monotonic) | ❌ Ausente | Implementado en `api.ts` |
| `correlation_id` tracking | ❌ Ausente | Tipos agregados en `types.ts` |
| `Last-Event-Id` reconnection header | ❌ Ausente | Implementado en `api.ts` |
| Event deduplication | ❌ Ausente | Sequence gate en `api.ts` |
| Timeout detection (60s inactivity) | ❌ Ausente | Implementado en `api.ts` |
| Retry with exponential backoff (max 3) | ❌ Ausente | Implementado en `api.ts` |
| Abort on unmount | ❌ Ausente | Implementado en `chat-interface.tsx` |
| No shared mutable state across SSE callbacks | ❌ `analysis` mutable compartido | Mitigado con `queryIdRef` guard |
| No stale closure bugs | ❌ Callbacks capturan `analysis` | Mitigado con guard pattern |
| No cross-query contamination | ❌ `isLoading` booleano global | `queryIdRef` aisla queries |
| Query isolation via `currentQueryId` | ❌ Ausente | `queryIdRef.current` + guard |
| Handle all SSE event types | ⚠️ Parcial (4/7) | Agregados `error` + `insufficient_context` |
| TypeScript errors/warnings | ⚠️ 1 warning | Limpiado a 0 |

---

## 2. Files Modified

### 2.1 `src/lib/types.ts` — Protocol types

**Agregado:**
- `ValidatedSSEEvent` — interfaz para eventos después del stamping de seq/ts
- `SSEError` — contrato de error tipado con `code`, `detail`, `recoverable`
- `StreamEventHeartbeat` — tipo para heartbeats del backend
- `StreamEventInsufficientContext` — tipo para contexto insuficiente

**Eliminado:**
- `SSEEvent` — dead code, no referenciado

### 2.2 `src/lib/api.ts` — SSE client resilience (rewrite)

**Agregado:**

| Feature | Implementación |
|---|---|
| Sequence tracking | `localSeq` + `parsed.seq ?? ++localSeq` para ordenamiento local |
| Sequence gate | `if (seq <= localSeq) continue` — descarta eventos duplicados/obsoletos |
| `Last-Event-Id` | Se envía en header de reconexión; se actualiza con `id:` del SSE o seq |
| Timeout | `INACTIVITY_TIMEOUT_MS = 60000` — emite `SSEError.code = "TIMEOUT"` si no hay datos por 60s |
| Retry backoff | `MAX_RETRIES = 3`, backoff exponencial `1s → 2s → 4s` (cap `10s`) |
| External signal | `AbortSignal.any` combina controller interno + externo |
| Full SSE parsing | Lee `id:`, `data:`, `event:` lines según RFC 8895 |
| Structured callbacks | `SSEStreamCallbacks` reemplaza 3 parámetros sueltos |

**Retirado:**
- `AbortController` como return value → reemplazado por función cancel `() => void`
- Parámetros callback sueltos → reemplazados por objeto `SSEStreamCallbacks`

### 2.3 `src/components/chat/chat-interface.tsx` — State safety + lifecycle

**Agregado:**

| Feature | Implementación |
|---|---|
| Abort on unmount | `useEffect(() => cancelRef.current(), [])` cleanup |
| Query isolation | `queryIdRef` se incrementa en cada submit; callbacks solo se ejecutan si el ref coincide |
| Cancel previous on new submit | `cancelRef.current()` al inicio de `handleSubmit` aborta stream anterior |
| Guard pattern | Objeto `guard` con `wrap<T>` y `wrapVoid` para descartar callbacks de queries obsoletas |
| Error event handling | `case "error"` muestra `Error: ${raw.detail}` |
| Insufficient context event | `case "insufficient_context"` marca `insufficient_context: true` |

**Retirado:**
- `abortRef: AbortController | null` → reemplazado por `cancelRef: () => void`
- Llamada a `streamQuery` con callback params → reemplazado por objeto `SSEStreamCallbacks`

---

## 3. SSE Client Architecture

### 3.1 Connection Lifecycle

```
submit query
    │
    ▼
connect()
    │
    ├── fetch POST /api/v1/query/stream
    │     headers:
    │       Content-Type: application/json
    │       Last-Event-Id: <lastSeq>   (si es reconexión)
    │
    ├── response.ok? ─── NO ──→ onError(NETWORK) ──→ retry?
    │     │
    │     ▼ YES
    │   reader = response.body.getReader()
    │
    ├── read loop
    │     │
    │     ├── data chunk arrives → resetTimeout()
    │     ├── parse SSE lines
    │     │     ├── "id: "  → currentId
    │     │     ├── "data: " → currentData
    │     │     ├── ""       → end of event → JSON.parse + onEvent
    │     │     └── seq gate → drop if <= localSeq
    │     │
    │     └── on complete → onComplete()
    │
    └── catch
          ├── AbortError → silent exit
          └── other → onError(NETWORK) → retry?
```

### 3.2 Retry State Machine

```
onError(NETWORK, recoverable=true)
    │
    ├── retries < MAX_RETRIES (3)?
    │     YES → setTimeout(connect, backoff)
    │            backoff = min(1000 * 2^retries, 10000)
    │            retries++
    │
    └── NO → give up, emit onError(recoverable=false)
```

### 3.3 Timeout Detection

```
resetTimeout() se llama en cada:
- inicio del stream
- cada evento SSE parseado exitosamente

Si pasan 60s sin llamar resetTimeout():
→ onError(TIMEOUT, recoverable=true)
→ si retries < MAX_RETRIES: reconnect()
→ si no: give up
```

---

## 4. State Safety Pattern

### 4.1 Problem

El código original mutaba un objeto `analysis` compartido dentro de callbacks SSE:

```typescript
// ANTES: mutable shared state
const analysis = buildEmptyAnalysis()

abortRef.current = streamQuery(request,
  (raw) => {
    analysis.direct_conclusion = raw.direct_conclusion  // mutación
    updateLastMessage((msg) => ({
      ...msg,
      analysis: { ...analysis },  // spread del mutable
    }))
  },
  // ...
)
```

Problemas:
- `analysis` se crea una vez en `handleSubmit` y se captura en el closure
- React batch puede juntar múltiples `setState` en un solo render
- Si el usuario hace submit dos veces rápido, ambos closures compiten por `updateLastMessage`
- No hay forma de saber si un callback pertenece a la query actual

### 4.2 Solution: queryId guard

```typescript
// DESPUÉS: query isolation via ref
const queryIdRef = useRef(0)

const handleSubmit = () => {
  const queryId = ++queryIdRef.current

  cancelRef.current()  // abortar query anterior

  const guard = {
    id: queryId,
    wrap<T>(fn: (arg: T) => void): (arg: T) => void {
      return (arg) => {
        if (queryIdRef.current === this.id) fn(arg)
      }
    },
    wrapVoid(fn: () => void): () => void {
      return () => {
        if (queryIdRef.current === this.id) fn()
      }
    },
  }

  streamQuery(request, {
    onEvent: guard.wrap((raw) => { /* ... */ }),
    onError: guard.wrap((error) => { /* ... */ }),
    onComplete: guard.wrapVoid(() => { setIsLoading(false) }),
  })
}
```

**Cómo funciona:**
- Cada submit incrementa `queryIdRef.current`
- `guard.wrap(fn)` retorna una función que verifica `queryIdRef.current === queryId` antes de ejecutar `fn`
- Si otra query ya empezó, el callback de la query anterior se descarta silenciosamente
- `cancelRef.current()` al inicio aborta el fetch del stream anterior

### 4.3 Abort on unmount

```typescript
useEffect(() => {
  return () => {
    cancelRef.current()  // aborta cualquier stream activo al desmontar
  }
}, [])
```

Esto previene:
- Memory leaks (fetch continúa después de desmontar)
- "React state update on unmounted component" warnings
- Procesamiento innecesario en el backend (el fetch se aborta → backend detecta disconnect)

---

## 5. Event Type Coverage

### 5.1 Antes: 4 de 7 tipos

```typescript
switch (raw.event) {
  case "analysis":     // ✓
  case "risk":         // ✓
  case "incentives":   // ✓
  case "complete":     // ✓
  // FALTAN:
  // case "start"              → correlation_id (ignorado)
  // case "retrieval"          → estado de búsqueda (ignorado)
  // case "error"              → errores del backend (ignorado!)
  // case "insufficient_context" → sin documentos (ignorado)
  // case "heartbeat"          → latido (ignorado)
}
```

### 5.2 Después: 6 de 9 tipos

```typescript
switch (raw.event) {
  case "analysis":              // ✓
  case "risk":                  // ✓
  case "incentives":            // ✓
  case "complete":              // ✓
  case "insufficient_context":  // ✓ nuevo
  case "error":                 // ✓ nuevo
  // Pendientes (bajo impacto):
  // "start"        → mostrar correlation_id en debug
  // "retrieval"    → mostrar "Searching..." status
  // "heartbeat"    → mantener conexión viva (ya manejado por timeout)
}
```

Los eventos `start`, `retrieval`, y `heartbeat` son informativos y no afectan la corrección del análisis legal. Se pueden agregar en una iteración futura de UI polish.

---

## 6. Build Verification

```
npm run lint    → 0 errors, 0 warnings
npm run build   → ✓ Compiled successfully
                → ✓ TypeScript passed
                → ✓ Static pages generated
```

---

## 7. Summary of Changes

| File | Líneas tocadas | Impacto |
|---|---|---|
| `src/lib/types.ts` | ~20 líneas | Tipos de protocolo SSE + error contract |
| `src/lib/api.ts` | ~90 líneas (rewrite) | SSE resilience completa (retry, timeout, dedup, seq, Last-Event-Id) |
| `src/components/chat/chat-interface.tsx` | ~50 líneas | Query isolation, abort lifecycle, más eventos |

**No modificados** (10 archivos): `message-bubble.tsx`, `filter-panel.tsx`, `header.tsx`, `next.config.ts`, `page.tsx`, `layout.tsx`, `globals.css`, `utils.ts`, `risk-matrix.tsx`, `legal-citations.tsx`, `incentives-panel.tsx`, todos los UI primitives (`button`, `card`, `badge`, `input`, `label`, `separator`, `select`, `switch`, `scroll-area`, `skeleton`).
