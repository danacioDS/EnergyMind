"use client"

import { useState, useRef, useEffect } from "react"
import { Send, Loader2 } from "lucide-react"
import { queryLegal } from "@/lib/api"
import type { QueryRequest } from "@/lib/types"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: string[]
  timestamp: Date
  loading?: boolean
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const handleSubmit = async () => {
    const question = input.trim()
    if (!question || isLoading) return

    setIsLoading(true)

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: question,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMessage])
    setInput("")

    const assistantId = (Date.now() + 1).toString()
    const assistantMessage: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      loading: true,
    }
    setMessages((prev) => [...prev, assistantMessage])

    try {
      const request: QueryRequest = {
        question: question,
        top_k: 5,
        use_agent: false,
      }

      const response = await queryLegal(request)

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                content: response.answer?.direct_conclusion || "No se encontró respuesta.",
                sources: response.sources || [],
                loading: false,
                timestamp: new Date(),
              }
            : msg
        )
      )

    } catch (error) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                content: `❌ Error: ${error instanceof Error ? error.message : "Error procesando la consulta"}`,
                loading: false,
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

  return (
    <div className="flex flex-col h-[80vh] max-w-3xl mx-auto">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-[#94A3B8]">
            <p className="text-lg font-medium text-white">EnergyMind</p>
            <p className="text-sm max-w-md mt-2">
              Pregunta sobre legislación de energías renovables en Bolivia.
              <br />
              Ejemplo: "¿Qué dice la Ley 1604 sobre energías renovables?"
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  msg.role === "user"
                    ? "bg-[#00D4AA] text-[#0B0F14]"
                    : "bg-[#1A222A] text-white"
                }`}
              >
                {msg.loading ? (
                  <div className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Pensando...</span>
                  </div>
                ) : (
                  <>
                    <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2 text-xs text-[#94A3B8]">
                        Fuentes: {msg.sources.join(", ")}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={scrollRef} />
      </div>

      <div className="border-t border-[#2A3340] p-4">
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Pregunta sobre energías renovables en Bolivia..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            className="flex-1 bg-[#1A222A] text-white rounded-lg px-4 py-2 border border-[#2A3340] focus:outline-none focus:border-[#00D4AA]"
          />
          <button
            onClick={handleSubmit}
            disabled={!input.trim() || isLoading}
            className="bg-[#00D4AA] text-[#0B0F14] rounded-lg px-4 py-2 disabled:opacity-50 hover:bg-[#00E6B8] transition-colors"
          >
            {isLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
          </button>
        </div>
      </div>
    </div>
  )
}
