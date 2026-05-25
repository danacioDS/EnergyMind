"use client"

import type { RegulatoryAnalysis } from "@/lib/types"
import RiskMatrix from "@/components/analysis/risk-matrix"
import LegalCitations from "@/components/analysis/legal-citations"
import IncentivesPanel from "@/components/analysis/incentives-panel"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

interface MessageBubbleProps {
  role: "user" | "assistant"
  content?: string
  analysis?: RegulatoryAnalysis | null
  isLoading?: boolean
}

export default function MessageBubble({
  role,
  content,
  analysis,
  isLoading,
}: MessageBubbleProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {content}
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 animate-bounce rounded-full bg-primary" style={{ animationDelay: "0ms" }} />
          <div className="h-2 w-2 animate-bounce rounded-full bg-primary" style={{ animationDelay: "150ms" }} />
          <div className="h-2 w-2 animate-bounce rounded-full bg-primary" style={{ animationDelay: "300ms" }} />
        </div>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-20 w-full" />
      </div>
    )
  }

  if (!analysis) return null

  return (
    <div className="space-y-4">
      {analysis.insufficient_context && (
        <div className="rounded-md border border-warning/20 bg-warning/5 p-3 text-sm text-warning">
          Insufficient information in the specialized renewable energy legal corpus.
        </div>
      )}

      {analysis.direct_conclusion && (
        <div>
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-1">
            Direct Conclusion
          </h3>
          <p className="text-sm leading-relaxed">{analysis.direct_conclusion}</p>
        </div>
      )}

      {analysis.regulatory_analysis && (
        <div>
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-1">
            Regulatory Analysis
          </h3>
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {analysis.regulatory_analysis}
            </ReactMarkdown>
          </div>
        </div>
      )}

      <Separator />

      <RiskMatrix matrix={analysis.risk_matrix} />

      <IncentivesPanel incentives={analysis.incentives_detected} />

      <LegalCitations citations={analysis.legal_citations} />
    </div>
  )
}
