"use client"

import type { IncentiveInfo as IncentiveInfoType } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Zap } from "lucide-react"

interface IncentivesPanelProps {
  incentives: IncentiveInfoType
}

export default function IncentivesPanel({ incentives }: IncentivesPanelProps) {
  if (!incentives.detected) return null

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
        Incentives Detected
      </h4>
      <div className="rounded-md border border-success/20 bg-success/5 p-3">
        <div className="flex items-center gap-2 mb-1">
          <Zap className="h-4 w-4 text-success" />
          <Badge variant="success">Active</Badge>
        </div>
        {incentives.type && (
          <p className="text-sm font-medium">{incentives.type}</p>
        )}
        {incentives.description && (
          <p className="text-xs text-muted-foreground mt-1">
            {incentives.description}
          </p>
        )}
        {incentives.articles.length > 0 && (
          <div className="flex gap-1 mt-2">
            {incentives.articles.map((art, i) => (
              <Badge key={i} variant="outline" className="text-[10px]">
                {art}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
