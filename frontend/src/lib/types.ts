export interface QueryRequest {
  question: string
  subsector?: string | null
  tipo_norma?: string | null
  vigente?: boolean | null
  top_k?: number
  use_agent?: boolean
}

export interface RiskMatrix {
  ideological_framework: string
  constitutional_conflict_risk: string
  nationalization_risk: string
  regulatory_instability: string
  legal_ambiguity: string
  arbitration_protection: string
}

export interface IncentiveInfo {
  detected: boolean
  type?: string | null
  articles: string[]
  description?: string | null
}

export interface LegalCitation {
  norma: string
  articulo: string
  texto: string
  tipo_norma: string
  risk_flags: string[]
}

export interface RegulatoryAnalysis {
  direct_conclusion: string
  regulatory_analysis: string
  legal_citations: LegalCitation[]
  risk_matrix: RiskMatrix
  incentives_detected: IncentiveInfo
  insufficient_context: boolean
}

export interface QueryResponse {
  question: string
  answer: RegulatoryAnalysis
  sources: string[]
  processing_time_ms?: number | null
}

// ── Raw backend events (as received over SSE) ──────────────

export interface StreamEventStart {
  event: "start"
  correlation_id: string | null
}

export interface StreamEventRetrieval {
  event: "retrieval"
  status: string
}

export interface StreamEventAnalysis {
  event: "analysis"
  direct_conclusion: string
}

export interface StreamEventRisk {
  event: "risk"
  matrix: RiskMatrix
}

export interface StreamEventIncentives {
  event: "incentives"
  detected: IncentiveInfo
}

export interface StreamEventComplete {
  event: "complete"
  processing_time_ms: number
  sources: string[]
}

export interface StreamEventError {
  event: "error"
  detail: string
}

export interface StreamEventHeartbeat {
  event: "heartbeat"
}

export interface StreamEventInsufficientContext {
  event: "insufficient_context"
}

export type StreamEvent =
  | StreamEventStart
  | StreamEventRetrieval
  | StreamEventAnalysis
  | StreamEventRisk
  | StreamEventIncentives
  | StreamEventComplete
  | StreamEventError
  | StreamEventHeartbeat
  | StreamEventInsufficientContext

// ── Validated event (after frontend seq/timestamp stamping) ─

export interface ValidatedSSEEvent {
  seq: number
  ts: string
  correlation_id: string
  raw: StreamEvent
}

// ── Error contract for SSE failures ────────────────────────

export interface SSEError {
  code: "NETWORK" | "TIMEOUT" | "PARSE" | "SERVER_ERROR"
  detail: string
  recoverable: boolean
}

export interface CorpusStats {
  status: string
  total_documents?: number
  by_norm_type?: Record<string, number>
  by_subsector?: Record<string, number>
  renewable_incentive_docs?: number
  risk_flags?: Record<string, number>
  sources_configured?: number
}
