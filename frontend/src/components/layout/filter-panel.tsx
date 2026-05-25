"use client"

import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export interface FilterValues {
  subsector: string
  tipo_norma: string
  use_agent: boolean
}

interface FilterPanelProps {
  filters: FilterValues
  onChange: (filters: FilterValues) => void
}

export default function FilterPanel({ filters, onChange }: FilterPanelProps) {
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-medium mb-3">Filters</h3>
      </div>

      <div className="space-y-2">
        <Label htmlFor="subsector">Subsector</Label>
        <Select
          value={filters.subsector}
          onValueChange={(v) =>
            onChange({ ...filters, subsector: v === "all" ? "" : v })
          }
        >
          <SelectTrigger id="subsector">
            <SelectValue placeholder="All subsectors" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All subsectors</SelectItem>
            <SelectItem value="Solar">Solar</SelectItem>
            <SelectItem value="Eolica">Eólica</SelectItem>
            <SelectItem value="Biomasa">Biomasa</SelectItem>
            <SelectItem value="Hidroelectrica">Hidroeléctrica</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="tipo_norma">Norm Type</Label>
        <Select
          value={filters.tipo_norma}
          onValueChange={(v) =>
            onChange({ ...filters, tipo_norma: v === "all" ? "" : v })
          }
        >
          <SelectTrigger id="tipo_norma">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            <SelectItem value="Constitucion">Constitución</SelectItem>
            <SelectItem value="Ley">Ley</SelectItem>
            <SelectItem value="Decreto Supremo">Decreto Supremo</SelectItem>
            <SelectItem value="Resolucion">Resolución</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center justify-between">
        <Label htmlFor="use-agent" className="cursor-pointer">
          Agent mode
        </Label>
        <Switch
          id="use-agent"
          checked={filters.use_agent}
          onCheckedChange={(v) => onChange({ ...filters, use_agent: v })}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Enables LangGraph agent with query refinement loop
      </p>
    </div>
  )
}
