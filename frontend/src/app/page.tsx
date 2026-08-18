"use client"

import dynamic from "next/dynamic"

// Cargar ChatInterface dinámicamente para evitar errores de SSR
const ChatInterface = dynamic(
  () => import("@/components/chat/chat-interface").then((mod) => mod.default || mod.ChatInterface),
  { ssr: false }
)

export default function Home() {
  return (
    <div className="max-w-4xl mx-auto">
      <ChatInterface />
    </div>
  )
}
