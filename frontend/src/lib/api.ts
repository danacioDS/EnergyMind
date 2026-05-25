"use client"

import type { QueryRequest, QueryResponse, CorpusStats, StreamEvent, SSEError } from "./types"

const API_BASE = "/api/v1"

export async function queryLegal(request: QueryRequest): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || "Query failed")
  }
  return res.json()
}

export async function fetchCorpusStats(): Promise<CorpusStats> {
  const res = await fetch(`${API_BASE}/corpus/stats`)
  if (!res.ok) return { status: "error" }
  return res.json()
}

const MAX_RETRIES = 3
const INITIAL_BACKOFF_MS = 1000
const MAX_BACKOFF_MS = 10000
const INACTIVITY_TIMEOUT_MS = 60000

export interface SSEStreamCallbacks {
  onEvent: (event: StreamEvent) => void
  onError: (error: SSEError) => void
  onComplete: () => void
}

export function streamQuery(
  request: QueryRequest,
  callbacks: SSEStreamCallbacks,
  externalSignal?: AbortSignal,
): () => void {
  let cancel = false
  let retries = 0
  let lastEventId = ""
  let localSeq = 0
  let timeoutId: ReturnType<typeof setTimeout> | undefined

  function resetTimeout() {
    clearTimeout(timeoutId)
    timeoutId = setTimeout(() => {
      if (!cancel) {
        callbacks.onError({
          code: "TIMEOUT",
          detail: "No SSE event received for 60s",
          recoverable: true,
        })
        if (retries < MAX_RETRIES) {
          retries++
          connect()
        }
      }
    }, INACTIVITY_TIMEOUT_MS)
  }

  function connect() {
    if (cancel) return

    const controller = new AbortController()
    const combinedSignal = externalSignal
      ? AbortSignal.any?.([controller.signal, externalSignal]) ?? controller.signal
      : controller.signal

    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (lastEventId) {
      headers["Last-Event-Id"] = lastEventId
    }

    fetch(`${API_BASE}/query/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(request),
      signal: combinedSignal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Stream failed: ${response.status} ${response.statusText}`)
        }

        const reader = response.body?.getReader()
        if (!reader) throw new Error("No response body")

        const decoder = new TextDecoder()
        let buffer = ""
        let currentId = lastEventId
        let currentData = ""

        resetTimeout()

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split("\n")
          buffer = lines.pop() || ""

          for (const line of lines) {
            if (line.startsWith("id: ")) {
              currentId = line.slice(4).trim()
            } else if (line.startsWith("data: ")) {
              currentData = line.slice(6)
            } else if (line === "" && currentData) {
              try {
                const parsed = JSON.parse(currentData) as StreamEvent & { seq?: number }

                const seq = parsed.seq ?? ++localSeq
                if (seq <= localSeq) continue
                localSeq = seq
                lastEventId = currentId || String(seq)

                resetTimeout()
                callbacks.onEvent(parsed)
              } catch {
                callbacks.onError({
                  code: "PARSE",
                  detail: "Failed to parse SSE data chunk",
                  recoverable: true,
                })
              }
              currentData = ""
            }
          }
        }

        callbacks.onComplete()
      })
      .catch((err) => {
        if (err.name === "AbortError") return
        callbacks.onError({
          code: "NETWORK",
          detail: err.message,
          recoverable: retries < MAX_RETRIES,
        })
        if (retries < MAX_RETRIES) {
          retries++
          const delay = Math.min(INITIAL_BACKOFF_MS * Math.pow(2, retries - 1), MAX_BACKOFF_MS)
          setTimeout(connect, delay)
        }
      })
  }

  connect()

  return () => {
    cancel = true
    clearTimeout(timeoutId)
  }
}
