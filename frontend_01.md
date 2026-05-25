# Frontend — LexEnergy Bolivia

## Decisión Técnica

Se eligió **Next.js 16 (App Router) + Tailwind CSS v4 + shadcn/ui** sobre Streamlit por las siguientes razones:

- Streamlit es adecuado para prototipos y demos rápidas, pero carece de:
  - SSR/SSG para SEO y rendimiento
  - Routing real (todo es una sola página con reruns)
  - Sistema de componentes moderno y tipado
  - Control fino sobre CSS y responsive design
  - Manejo nativo de SSE (Server-Sent Events)
- Next.js 16 ofrece App Router con Server Components, streaming SSR, y un ecosistema maduro para aplicaciones profesionales.

## Stack

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Framework | Next.js | 16.2.6 |
| UI | Tailwind CSS | 4 (PostCSS) |
| Componentes | shadcn/ui (Radix Primitives) | — |
| Lenguaje | TypeScript | 5 |
| Markdown | react-markdown + remark-gfm | 10.x |
| Icons | lucide-react | 1.16 |
| Utilidades | class-variance-authority, clsx, tailwind-merge | — |

## Estructura del Proyecto

```
frontend/
├── .env.local                        # NEXT_PUBLIC_API_URL=http://localhost:8000
├── next.config.ts                     # Rewrites: /api/* → backend
├── package.json                       # Dependencias
├── postcss.config.mjs                 # @tailwindcss/postcss
├── tsconfig.json                      # Path alias @/ → src/
│
└── src/
    ├── app/
    │   ├── globals.css               # Tailwind v4 + theme (claro/oscuro)
    │   ├── layout.tsx                # Root layout con metadata
    │   └── page.tsx                  # Server Component → ChatInterface
    │
    ├── lib/
    │   ├── utils.ts                  # cn() helper (clsx + tailwind-merge)
    │   ├── types.ts                  # Interfaces: QueryRequest, QueryResponse,
    │   │                             #   RiskMatrix, IncentiveInfo, LegalCitation,
    │   │                             #   RegulatoryAnalysis, StreamEvent (disc. union)
    │   └── api.ts                    # queryLegal(), streamQuery() con SSE via
    │                                 #   fetch + ReadableStream
    │
    └── components/
        ├── ui/                       # 10 componentes shadcn-style
        │   ├── badge.tsx             #   variants: default, secondary, destructive,
        │   │                         #     outline, success, warning
        │   ├── button.tsx            #   variants: default, destructive, outline,
        │   │                         #     secondary, ghost, link
        │   ├── card.tsx              #   Card, CardHeader, CardTitle, CardContent,
        │   │                         #     CardDescription, CardFooter
        │   ├── input.tsx             #   Input base
        │   ├── label.tsx             #   Label con peer-disabled
        │   ├── scroll-area.tsx       #   ScrollArea + ScrollBar (Radix)
        │   ├── select.tsx            #   Select completo con scroll, grupos
        │   ├── separator.tsx         #   Separator horizontal/vertical
        │   ├── skeleton.tsx          #   Skeleton loading
        │   └── switch.tsx            #   Switch toggle (Radix)
        │
        ├── layout/
        │   ├── header.tsx            # Header sticky con logo Scale + toggle filtros
        │   └── filter-panel.tsx      # Sidebar: subsector, tipo_norma, agent mode
        │
        ├── chat/
        │   ├── chat-interface.tsx    # Core: input, submit, SSE streaming, mensajes
        │   └── message-bubble.tsx    # Render de respuesta: conclusión, análisis
        │                             #   (markdown), risk matrix, citas, incentivos
        │
        └── analysis/
            ├── risk-matrix.tsx       # Grid 2×3 con Badge coloreado por nivel
            ├── legal-citations.tsx   # Lista de citas con norma, artículo, texto,
            │                         #   tipo_norma y risk_flags
            └── incentives-panel.tsx  # Panel verde con icono Zap + badges
```

## Arquitectura de Comunicación

### API Proxy

```
Browser → Next.js Rewrite (/api/*) → FastAPI Backend (:8000)
```

Configurado en `next.config.ts`:

```typescript
async rewrites() {
  return [{
    source: "/api/:path*",
    destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*",
  }]
}
```

Esto elimina problemas de CORS en desarrollo y producción.

### Endpoints Utilizados

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/api/v1/query` | Query normal (JSON response) |
| POST | `/api/v1/query/stream` | Query con SSE (progressive update) |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/corpus/stats` | Estadísticas del corpus |

### SSE Streaming

El flujo de SSE para `/query/stream` maneja eventos progresivos:

1. **start** — correlation_id
2. **retrieval** — status "querying"
3. **analysis** — direct_conclusion (primeros 500 chars)
4. **risk** — risk_matrix completo
5. **incentives** — incentives_detected
6. **complete** — processing_time_ms + sources

Implementación en `api.ts`:

```typescript
// Lectura del stream con fetch + ReadableStream
const reader = response.body?.getReader()
const decoder = new TextDecoder()
let buffer = ""

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  buffer += decoder.decode(value, { stream: true })
  // Parsear líneas "data: {...}"
}
```

## Flujo de Datos

### Modo Normal (con SSE)

```
Usuario → input → ChatInterface.handleSubmit()
  → streamQuery() → fetch POST /api/v1/query/stream
  → SSE events → updateLastMessage() muta análisis progresivamente
  → MessageBubble renderiza cada sección al llegar
```

### Modo Agente (LangGraph)

```
Usuario → input → ChatInterface.handleSubmit()
  → queryLegal() → fetch POST /api/v1/query
  → Backend procesa con LangGraph (hasta 3 iteraciones de refinamiento)
  → Response JSON completa → render inmediato
```

## Componente ChatInterface

### Estado

```typescript
interface Message {
  id: string
  role: "user" | "assistant"
  content?: string          // solo para mensajes del usuario
  analysis?: RegulatoryAnalysis | null  // respuesta estructurada
  isLoading?: boolean       // estado de carga
}

const [messages, setMessages] = useState<Message[]>([])
const [input, setInput] = useState("")
const [isLoading, setIsLoading] = useState(false)
const [filters, setFilters] = useState({ subsector, tipo_norma, use_agent })
```

### Ciclo de vida de una Query SSE

1. Se agrega mensaje del usuario + mensaje assistant con `isLoading: true`
2. Se crea un `RegulatoryAnalysis` vacío mutable
3. Se llama a `streamQuery()` que retorna un `AbortController`
4. Cada evento SSE muta el objeto `analysis` y dispara `updateLastMessage()`
5. `updateLastMessage()` crea un nuevo objeto con `{ ...analysis }` para forzar re-render
6. Al recibir "complete", se marca `isLoading: false`

### Manejo de Errores

- Si `streamQuery` lanza error: se muestra en `direct_conclusion` con `insufficient_context: true`
- Si el AbortController aborta: se ignora el error (no se muestra al usuario)
- Si agent mode falla: catch genérico con mismo tratamiento

## Componente MessageBubble

Renderiza 4 secciones condicionales:

1. **Insufficient Context Warning** — banner amarillo si `insufficient_context`
2. **Direct Conclusion** — texto plano en párrafo
3. **Regulatory Analysis** — Markdown renderizado con `react-markdown` + `remark-gfm`
4. **Separator** + Risk Matrix + Incentives + Citations

El estado de carga muestra un loader animado (3 bouncing dots) + skeletons.

## Tema Visual

### Colores (shadcn-ui inspired)

| Token | Light | Dark | Uso |
|-------|-------|------|-----|
| `--color-background` | `#ffffff` | `#09090b` | Fondo principal |
| `--color-primary` | `#1e40af` | `#3b82f6` | Acciones, links |
| `--color-success` | `#16a34a` | `#22c55e` | Incentivos, riesgo bajo |
| `--color-warning` | `#d97706` | `#f59e0b` | Riesgo medio |
| `--color-destructive` | `#ef4444` | `#ef4444` | Riesgo alto |
| `--color-risk-critical` | `#7c3aed` | `#a855f7` | Riesgo crítico |

### Tailwind v4

Se usa `@theme inline` en `globals.css` en lugar de `tailwind.config.js`. Esto permite:
- Definir colores como CSS custom properties directamente
- Usar `bg-background`, `text-primary`, etc. como utility classes
- Soporte nativo de `bg-background/80` para opacidad (vía `color-mix()`)

## Dependencias Clave

```json
{
  "next": "16.2.6",
  "react": "19.2.4",
  "tailwindcss": "^4",
  "@radix-ui/react-select": "^2.2.6",
  "@radix-ui/react-switch": "^1.2.6",
  "@radix-ui/react-scroll-area": "^1.2.10",
  "react-markdown": "^10.1.0",
  "remark-gfm": "^4.0.1",
  "class-variance-authority": "^0.7.1",
  "lucide-react": "^1.16.0"
}
```

Nota: Next.js 16 cambia `middleware.ts` por `proxy.ts`. El proyecto actual usa `rewrites` en `next.config.ts`, que es el approach recomendado para proxy simple.

## Build

```
npm run build   # ✓ Compiled successfully
npm run lint    # 0 errors, 0 warnings
```

## Para Correr

```bash
# 1. Iniciar backend (FastAPI + Qdrant + Ollama)
cd .. && docker compose -f docker/docker-compose.yml up -d

# 2. Iniciar frontend
cd frontend && npm run dev
# → http://localhost:3000

# 3. Producción
npm run build && npm start
```

## Próximas Mejoras Posibles

- [ ] Autenticación (NextAuth / Clerk)
- [ ] Exportar análisis a PDF
- [ ] Historial de queries (localStorage o DB)
- [ ] Comparación side-by-side de análisis
- [ ] Drawer de filtros en mobile
- [ ] i18n (español/inglés)
- [ ] Modo oscuro toggle (en lugar de depender de prefers-color-scheme)
- [ ] Rate limiting y feedback de corpus stats
