"use client"

import { useState, useRef, useEffect } from "react"
import { Send, Loader2, AlertCircle, FileText, Shield, Zap } from "lucide-react"
import { queryLegal } from "@/lib/api"
import type { QueryRequest, QueryResponse } from "@/lib/types"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: string[]
  riskMatrix?: any
  incentives?: any
  timestamp: Date
  processingTime?: number
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSubmit = async () => {
    const question = input.trim()
    if (!question || isLoading) return

    setIsLoading(true)
    setError(null)

    // Mensaje del usuario
    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: question,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMessage])
    setInput("")

    // Mensaje del asistente (loading)
    const assistantId = (Date.now() + 1).toString()
    const assistantMessage: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, assistantMessage])

    try {
      const request: QueryRequest = {
        question: question,
        subsector: "General",
        top_k: 5,
        use_agent: false,
      }

      const response = await queryLegal(request)

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                content: response.answer?.direct_conclusion || response.answer?.regulatory_analysis || "No se encontró respuesta.",
                sources: response.sources || [],
                riskMatrix: response.answer?.risk_matrix,
                incentives: response.answer?.incentives_detected,
                processingTime: response.processing_time_ms,
                timestamp: new Date(),
              }
            : msg
        )
      )

    } catch (err) {
      console.error("Error:", err)
      setError(err instanceof Error ? err.message : "Error procesando la consulta")
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                content: `❌ Error: ${err instanceof Error ? err.message : "Error procesando la consulta"}`,
                timestamp: new Date(),
              }
            : msg
        )
      )
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })
  }

  return (
    <div className="flex flex-col h-full w-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-yellow-500" />
          <h2 className="font-semibold">LexEnergy Bolivia</h2>
          <Badge variant="outline" className="ml-2 text-xs">
            Legal RAG
          </Badge>
        </div>
        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Procesando...
          </div>
        )}
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
            <FileText className="h-12 w-12 mb-4 opacity-20" />
            <p className="text-lg font-medium">LexEnergy Bolivia</p>
            <p className="text-sm max-w-md">
              Pregunta sobre legislación de energías renovables en Bolivia.
              <br />
              Ejemplo: "¿Qué dice la Ley 1604 sobre energías renovables?"
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex flex-col max-w-[85%]",
                  msg.role === "user" ? "ml-auto items-end" : "mr-auto items-start"
                )}
              >
                <div
                  className={cn(
                    "rounded-lg px-4 py-2",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  )}
                >
                  <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                </div>

                {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2 text-xs text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <FileText className="h-3 w-3" />
                      <span>Fuentes: {msg.sources.join(", ")}</span>
                    </div>
                    {msg.processingTime && (
                      <span className="ml-2">⏱ {msg.processingTime}ms</span>
                    )}
                  </div>
                )}

                {msg.role === "assistant" && msg.riskMatrix && (
                  <div className="mt-2 text-xs text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Shield className="h-3 w-3" />
                      <span>Riesgos: {
                        Object.entries(msg.riskMatrix)
                          .filter(([_, v]) => v !== "Low" && v !== "Bajo" && v !== "")
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(", ")
                      }</span>
                    </div>
                  </div>
                )}

                <span className="text-xs text-muted-foreground mt-1">
                  {formatTime(msg.timestamp)}
                </span>
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-3 mt-4 rounded-lg bg-destructive/10 text-destructive text-sm">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        )}
      </ScrollArea>

      {/* Input */}
      <div className="border-t p-4">
        <div className="flex gap-2">
          <Input
            ref={inputRef}
            placeholder="Pregunta sobre energías renovables en Bolivia..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            className="flex-1"
          />
          <Button
            onClick={handleSubmit}
            disabled={!input.trim() || isLoading}
            size="icon"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
