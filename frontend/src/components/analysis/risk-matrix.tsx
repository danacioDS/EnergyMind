"use client"

import { Badge } from "@/components/ui/badge"
import type { RiskMatrix as RiskMatrixType } from "@/lib/types"

const riskColor = (level: string) => {
  const normalized = level.toLowerCase().replace(/[- ]/g, "_")
  if (normalized.includes("high") || normalized.includes("critical")) return "destructive"
  if (normalized.includes("medium") || normalized.includes("limited")) return "warning"
  return "success"
}

const labels: Record<keyof RiskMatrixType, string> = {
  ideological_framework: "Ideological Framework",
  constitutional_conflict_risk: "Constitutional Conflict",
  nationalization_risk: "Nationalization Risk",
  regulatory_instability: "Regulatory Instability",
  legal_ambiguity: "Legal Ambiguity",
  arbitration_protection: "Arbitration Protection",
}

interface RiskMatrixProps {
  matrix: RiskMatrixType
}

export default function RiskMatrix({ matrix }: RiskMatrixProps) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
        Risk Matrix
      </h4>
      <div className="grid grid-cols-2 gap-2">
        {(Object.keys(labels) as Array<keyof RiskMatrixType>).map((key) => (
          <div
            key={key}
            className="flex items-center justify-between rounded-md border px-3 py-2"
          >
            <span className="text-xs text-muted-foreground">{labels[key]}</span>
            <Badge variant={riskColor(matrix[key])}>{matrix[key]}</Badge>
          </div>
        ))}
      </div>
    </div>
  )
}
