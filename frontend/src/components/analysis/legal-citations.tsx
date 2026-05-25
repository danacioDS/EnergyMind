"use client"

import type { LegalCitation as Citation } from "@/lib/types"
import { Badge } from "@/components/ui/badge"

interface LegalCitationsProps {
  citations: Citation[]
}

export default function LegalCitations({ citations }: LegalCitationsProps) {
  if (!citations.length) return null

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
        Legal Citations
      </h4>
      <div className="space-y-2">
        {citations.map((c, i) => (
          <div key={i} className="rounded-md border p-3">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-xs font-medium text-primary">
                {c.norma}
              </span>
              <span className="text-xs text-muted-foreground">
                Art. {c.articulo}
              </span>
              <Badge variant="outline" className="text-[10px]">
                {c.tipo_norma}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground line-clamp-3">
              {c.texto}
            </p>
            {c.risk_flags.length > 0 && (
              <div className="flex gap-1 mt-1">
                {c.risk_flags.map((flag) => (
                  <Badge key={flag} variant="warning" className="text-[10px]">
                    {flag}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
