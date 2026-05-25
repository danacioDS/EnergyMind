# LexEnergy Bolivia — Frontend 03: Production Deployment & Operations

## Build & Deploy

### Development

```bash
cd frontend
npm install
npm run dev          # → http://localhost:3000
```

Requiere backend corriendo en `http://localhost:8000` (FastAPI + Qdrant + Ollama).

### Production Build

```bash
npm run build        # Compila + type-checks
npm start            # Next.js server :3000
```

### Docker

```dockerfile
# docker/frontend.Dockerfile
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

### Docker Compose (full stack)

```bash
docker compose -f docker/docker-compose.yml up -d
# Frontend: http://localhost:3000
# API:      http://localhost:8000
# Qdrant:   http://localhost:6333
# Redis:    localhost:6379
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API base URL |

En Next.js, las variables `NEXT_PUBLIC_*` se inyectan en build-time. Para cambiar el backend URL sin rebuild, usar las rewrites de `next.config.ts` o un proxy inverso.

---

## Proxy & Routing

`next.config.ts` rewrites todo `/api/*` al backend:

```typescript
async rewrites() {
  return [{
    source: "/api/:path*",
    destination: `${process.env.NEXT_PUBLIC_API_URL}/api/:path*`,
  }]
}
```

En producción detrás de nginx:

```nginx
server {
    listen 443 ssl;
    server_name lexenergy.example.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;

        # Required for SSE
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header X-Accel-Buffering no;
        chunked_transfer_encoding on;
    }
}
```

### SSE y Proxies

El endpoint `/api/v1/query/stream` usa Server-Sent Events. Los proxies intermedios (nginx, Cloudflare, AWS ALB) pueden bufferear o timeout las conexiones largas.

**Requisitos:**
- `proxy_buffering off` en nginx
- `proxy_read_timeout` ≥ 120s (o lo que dure la query más larga)
- `X-Accel-Buffering: no` header desde el backend
- No pasar por Cloudflare en free tier (timeout 100s)
- AWS ALB: configurar `idle_timeout` ≥ 300s

---

## Logging & Monitoring

### Frontend Logs

Next.js 16 logs a stdout/stderr. En Docker, capturar via `docker logs`.

```bash
docker compose logs -f lexenergy-ui
```

### Errores del Cliente

El frontend no tiene captura de errores del lado del cliente. Agregar:

```typescript
// src/lib/error-tracker.ts (futuro)
export function initErrorTracking() {
  window.addEventListener("unhandledrejection", (event) => {
    fetch("/api/v1/log-error", {
      method: "POST",
      body: JSON.stringify({
        error: event.reason?.message ?? String(event.reason),
        stack: event.reason?.stack,
        url: window.location.href,
        correlation_id: getCorrelationId(),
      }),
    }).catch(() => {})  // fire-and-forget
  })
}
```

### Métricas Clave

| Métrica | Dónde | Alerta si |
|---|---|---|
| SSE connection duration | API logs | > 60s average |
| SSE events per query | API logs | < 3 events (incomplete) |
| LLM response time | API logs | > 30s |
| BM25 index age | API /health | > 24h since last rebuild |
| Memory usage | Docker stats | > 6GB |

---

## Health Checks

### Endpoint

```
GET /api/v1/health
→ { "status": "healthy", "service": "LexEnergy Bolivia", "version": "1.0.0" }
```

### Docker Healthcheck

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

### End-to-End Health (frontend)

```bash
# Verificar que el frontend sirve páginas
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# → 200

# Verificar que el proxy funciona
curl -s http://localhost:3000/api/v1/health
# → {"status":"healthy",...}
```

---

## Backup & Recovery

### Qué respaldar

| Dato | Ubicación | Frecuencia |
|---|---|---|
| Qdrant vectors | `qdrant_storage/` volume | Diario |
| Redis data | `redis_data/` volume | Diario |
| BM25 index | `cache/bm25_index.pkl` | Después de cada ingesta |
| Corpus raw | `corpus/raw/` | Control de versiones (git) |
| Corpus normalized | `corpus/normalized/` | Control de versiones (git) |

### Restore

```bash
# 1. Detener servicios
docker compose down

# 2. Restaurar volúmenes desde backup
./restore.sh /path/to/backup/2025-05-25

# 3. Reconstruir BM25 index si es necesario
docker compose run --rm lexenergy-api python -c "
from app.retrieval.engine import RetrievalEngine
import asyncio
async def rebuild():
    e = RetrievalEngine()
    await e.initialize()
    # rebuild BM25 from scroll_all
asyncio.run(rebuild())
"

# 4. Reiniciar
docker compose up -d
```

---

## Troubleshooting

### El frontend carga pero no responde queries

```
Síntoma:   200 OK en /api/v1/health desde el frontend
           500 o timeout en POST /api/v1/query
Causa:     Backend no conecta a Qdrant u Ollama
Fix:       docker compose logs lexenergy-api
           Verificar QDRANT_HOST y OLLAMA_BASE_URL
```

### SSE se corta antes de "complete"

```
Síntoma:   Último evento recibido es "analysis" o "risk", nunca "complete"
Causa:     Timeout de proxy, crash de Ollama, OOM
Fix:       1. Verificar logs del API: "Stream cancelled" o "LLM_TIMEOUT"
           2. Aumentar proxy_read_timeout
           3. Verificar OLLAMA no esté overloaded
```

### Errores CORS

```
Síntoma:   Browser bloquea fetch por CORS
Causa:     Frontend y backend en distintos origins sin proxy
Fix:       Usar next.config.ts rewrites (recomendado)
            O configurar CORS en FastAPI para origins específicos
```

### TypeScript build errors after pull

```bash
# Limpiar caché y reconstruir
rm -rf .next node_modules
npm ci
npm run build
```

### Next.js 16: middleware → proxy

En Next.js 16, `middleware.ts` se renombró a `proxy.ts`. Si existe un archivo `middleware.ts`, migrar:

```bash
npx @next/codemod@canary middleware-to-proxy .
```

---

## Performance Budget

| Recurso | Límite |
|---|---|
| Build size (gzip) | < 200KB JS |
| First Load JS | < 150KB |
| SSE time-to-first-event | < 2s |
| SSE time-to-complete | < 30s |
| Memory (browser) | < 100MB |
| API response (non-stream) | < 5s |

---

## Security Checklist

- [ ] `allow_origins` en CORS no es `["*"]` en producción
- [ ] API detrás de VPN o auth en producción
- [ ] SSE no expone datos sensibles en eventos de error
- [ ] No hay secretos en el bundle del frontend
- [ ] `X-Content-Type-Options: nosniff` en headers
- [ ] Rate limiting en endpoints `/api/v1/query*`
- [ ] Input validation: `question` max length 2000 chars
- [ ] `QP` (query parameter) injection prevenido por Pydantic/Next.js

---

## Próximos Pasos (después del refactoring de frontend_02.md)

1. **Implementar SSE sequence numbers** en `api.ts`
2. **Reemplazar useState con useReducer** en `chat-interface.tsx`
3. **Agregar abort on unmount**
4. **Implementar reconexión automática** con backoff exponencial
5. **Agregar error boundary** React para SSE failures
6. **Desplegar con Docker compose** multi-servicio
7. **Configurar monitoreo** de conexiones SSE activas
