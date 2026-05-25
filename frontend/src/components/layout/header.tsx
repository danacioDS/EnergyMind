"use client"

import { Scale } from "lucide-react"
import { Button } from "@/components/ui/button"

interface HeaderProps {
  onToggleFilters: () => void
  filtersVisible: boolean
}

export default function Header({ onToggleFilters, filtersVisible }: HeaderProps) {
  return (
    <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-14 items-center justify-between px-4 max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <Scale className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-lg font-semibold tracking-tight">LexEnergy Bolivia</h1>
            <p className="text-xs text-muted-foreground hidden sm:block">
              Legal RAG Platform &mdash; Renewable Energy Investments
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onToggleFilters}
            className="gap-2"
          >
            {filtersVisible ? "Hide Filters" : "Filters"}
          </Button>
        </div>
      </div>
    </header>
  )
}
