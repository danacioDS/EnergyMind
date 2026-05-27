"use client"

import { useState, useRef, useEffect } from "react"
import type {
  RegulatoryAnalysis,
  StreamEvent,
  SSEError,
} from "@/lib/types"
import { queryLegal, streamQuery } from "@/lib/api"
import Header from "@/components/layout/header"
import FilterPanel, { type FilterValues } from "@/components/layout/filter-panel"
import MessageBubble from "@/components/chat/message-bubble"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Send, PanelRightOpen, SlidersHorizontal } from "lucide-react"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"

interface Message {
  id: string
  role: "user" | "assistant"
  content?: string
  analysis?: RegulatoryAnalysis | null
  isLoading?: boolean
}

function buildEmptyAnalysis(): RegulatoryAnalysis {
  return {
    direct_conclusion: "",
    regulatory_analysis: "",
    legal_citations: [],
    risk_matrix: {
      ideological_framework: "",
      constitutional_conflict_risk: "",
      nationalization_risk: "",
      regulatory_instability: "",
      legal_ambiguity: "",
      arbitration_protection: "",
    },
    incentives_detected: {
      detected: false,
      type: null,
      articles: [],
      description: null,
    },
    insufficient_context: false,
  }
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [filtersVisible, setFiltersVisible] = useState(true)
  const [filters, setFilters] = useState<FilterValues>({
    subsector: "",
    tipo_norma: "",
    use_agent: false,
  })
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const cancelRef = useRef<() => void>(() => {})
  const queryIdRef = useRef(0)

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    return () => {
      cancelRef.current()
    }
  }, [])

  const addMessage = (msg: Message) => {
    setMessages((prev) => [...prev, msg])
  }

  const updateLastMessage = (updater: (msg: Message) => Message) => {
    setMessages((prev) => {
      const updated = [...prev]
      if (updated.length > 0) {
        updated[updated.length - 1] = updater(updated[updated.length - 1])
      }
      return updated
    })
  }

  const handleSubmit = async () => {
    const question = input.trim()
    if (!question || isLoading) return

    const queryId = ++queryIdRef.current

    cancelRef.current()

    setInput("")
    setIsLoading(true)

    const userMsg: Message = {
      id: `user-${queryId}`,
      role: "user",
      content: question,
    }
    addMessage(userMsg)

    const assistantId = `assistant-${queryId}`
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      isLoading: true,
    }
    addMessage(assistantMsg)

    const guard = {
      id: queryId,
      wrap<T>(fn: (arg: T) => void): (arg: T) => void {
        return (arg: T) => {
          if (queryIdRef.current === this.id) fn(arg)
        }
      },
      wrapVoid(fn: () => void): () => void {
        return () => {
          if (queryIdRef.current === this.id) fn()
        }
      },
    }

    try {
      const request = {
        question,
        subsector: filters.subsector || null,
        tipo_norma: filters.tipo_norma || null,
        use_agent: filters.use_agent,
      }

      if (filters.use_agent) {
        const response = await queryLegal(request)
        guard.wrap(updateLastMessage)((msg) => ({
          ...msg,
          isLoading: false,
          analysis: response.answer,
        }))
        setIsLoading(false)
      } else {
        const cancel = streamQuery(
          request,
          {
            onEvent: guard.wrap((raw: StreamEvent) => {
              switch (raw.event) {
                case "analysis":
                  updateLastMessage((msg) => ({
                    ...msg,
                    isLoading: false,
                    analysis: {
                      ...(msg.analysis || buildEmptyAnalysis()),
                      direct_conclusion: raw.direct_conclusion,
                    },
                  }))
                  break
                case "risk":
                  updateLastMessage((msg) => ({
                    ...msg,
                    analysis: {
                      ...(msg.analysis || buildEmptyAnalysis()),
                      risk_matrix: raw.matrix,
                    },
                  }))
                  break
                case "incentives":
                  updateLastMessage((msg) => ({
                    ...msg,
                    analysis: {
                      ...(msg.analysis || buildEmptyAnalysis()),
                      incentives_detected: raw.detected,
                    },
                  }))
                  break
                case "complete":
                  updateLastMessage((msg) => ({
                    ...msg,
                    analysis: msg.analysis ? { ...msg.analysis } : buildEmptyAnalysis(),
                  }))
                  break
                case "insufficient_context":
                  updateLastMessage((msg) => ({
                    ...msg,
                    isLoading: false,
                    analysis: {
                      ...(msg.analysis || buildEmptyAnalysis()),
                      insufficient_context: true,
                    },
                  }))
                  break
                case "error":
                  updateLastMessage((msg) => ({
                    ...msg,
                    isLoading: false,
                    analysis: {
                      ...buildEmptyAnalysis(),
                      direct_conclusion: `Error: ${raw.detail}`,
                      insufficient_context: true,
                    },
                  }))
                  break
              }
            }),
            onError: guard.wrap((error: SSEError) => {
              updateLastMessage((msg) => ({
                ...msg,
                isLoading: false,
                analysis: {
                  ...buildEmptyAnalysis(),
                  direct_conclusion: `Error [${error.code}]: ${error.detail}`,
                  insufficient_context: true,
                },
              }))
            }),
            onComplete: guard.wrapVoid(() => {
              setIsLoading(false)
            }),
          },
        )

        cancelRef.current = cancel
      }
    } catch (err) {
      guard.wrap(updateLastMessage)((msg) => ({
        ...msg,
        isLoading: false,
        analysis: {
          ...buildEmptyAnalysis(),
          direct_conclusion: `Error: ${(err as Error).message}`,
          insufficient_context: true,
        },
      }))
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex flex-col h-screen">
      <Header
        onToggleFilters={() => setFiltersVisible(!filtersVisible)}
        filtersVisible={filtersVisible}
      />

      <div className="flex flex-1 overflow-hidden">
        {filtersVisible && (
          <aside className="w-60 border-r bg-sidebar p-4 hidden md:block overflow-y-auto">
            <FilterPanel filters={filters} onChange={setFilters} />
          </aside>
        )}

        <div className="md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon" className="fixed bottom-4 right-4 z-50 h-12 w-12 rounded-full shadow-lg">
                <SlidersHorizontal className="h-5 w-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left">
              <h2 className="text-lg font-semibold mb-4">Filters</h2>
              <FilterPanel filters={filters} onChange={setFilters} />
            </SheetContent>
          </Sheet>
        </div>

        <main className="flex-1 flex flex-col min-w-0">
          <ScrollArea className="flex-1">
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center pt-20 text-center">
                  <div className="rounded-full bg-primary/10 p-4 mb-4">
                    <PanelRightOpen className="h-8 w-8 text-primary" />
                  </div>
                  <h2 className="text-xl font-semibold mb-2">
                    LexEnergy Bolivia
                  </h2>
                  <p className="text-sm text-muted-foreground max-w-md">
                    Ask legal questions about renewable energy investments in
                    Bolivia. The system retrieves relevant legal documents and
                    provides structured regulatory analysis.
                  </p>
                  <div className="mt-6 grid gap-2 text-left text-sm text-muted-foreground">
                    <div className="rounded-md border p-3">
                      <span className="font-medium text-foreground">
                        Example:{" "}
                      </span>
                      &ldquo;What are the requirements for foreign investment in
                      solar energy projects in Bolivia?&rdquo;
                    </div>
                    <div className="rounded-md border p-3">
                      <span className="font-medium text-foreground">
                        Example:{" "}
                      </span>
                      &ldquo;What incentives exist for renewable energy under DS
                      5503?&rdquo;
                    </div>
                  </div>
                </div>
              )}

              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  role={msg.role}
                  content={msg.content}
                  analysis={msg.analysis}
                  isLoading={msg.isLoading}
                />
              ))}

              <div ref={scrollRef} />
            </div>
          </ScrollArea>

          <div className="border-t bg-background">
            <div className="max-w-3xl mx-auto px-4 py-3">
              <div className="flex items-center gap-2">
                <Input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a legal question about renewable energy in Bolivia..."
                  disabled={isLoading}
                  className="flex-1"
                />
                <Button
                  onClick={handleSubmit}
                  disabled={isLoading || !input.trim()}
                  size="icon"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
