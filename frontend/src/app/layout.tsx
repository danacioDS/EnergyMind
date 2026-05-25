import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "LexEnergy Bolivia | Legal RAG Platform",
  description:
    "Legal RAG Platform for Renewable Energy Investments in Bolivia. Ask legal questions about renewable energy regulations.",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="es" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  )
}
