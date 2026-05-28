"use client"

import { useEffect, useState } from "react"
import { fetchCorpusStats } from "@/lib/api"
import type { CorpusStats } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts"

const CHART_COLOR = "hsl(var(--primary))"

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold">{value.toLocaleString()}</p>
      </CardContent>
    </Card>
  )
}

function ChartCard({
  title,
  data,
  layout,
}: {
  title: string
  data: { name: string; value: number }[]
  layout: "horizontal" | "vertical"
}) {
  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No data available</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={Math.max(data.length * 40, 150)}>
          {layout === "horizontal" ? (
            <BarChart data={data} layout="vertical" margin={{ left: 100 }}>
              <XAxis type="number" />
              <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="value" fill={CHART_COLOR} radius={[0, 4, 4, 0]}>
                {data.map((_, i) => (
                  <Cell key={i} fill={CHART_COLOR} />
                ))}
              </Bar>
            </BarChart>
          ) : (
            <BarChart data={data} margin={{ bottom: 60 }}>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill={CHART_COLOR} radius={[4, 4, 0, 0]}>
                {data.map((_, i) => (
                  <Cell key={i} fill={CHART_COLOR} />
                ))}
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}

function StatsSkeleton() {
  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <div className="space-y-1">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
      </div>
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Array.from({ length: 2 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-32" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-40 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

function StatsError({ status }: { status?: string }) {
  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <Card>
        <CardHeader>
          <CardTitle>Corpus not available</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {status === "no_corpus"
              ? "No corpus found. Run ingestion first (POST /api/v1/ingest)."
              : "Failed to load corpus statistics. Ensure the API is running and the corpus is ingested."}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

export default function StatsPage() {
  const [stats, setStats] = useState<CorpusStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchCorpusStats().then(s => {
      setStats(s)
      setLoading(false)
    })
  }, [])

  if (loading) return <StatsSkeleton />
  if (!stats || stats.status !== "ok") return <StatsError status={stats?.status} />

  const normTypeData = Object.entries(stats.by_norm_type ?? {}).map(
    ([name, value]) => ({ name, value }),
  )
  const subsectorData = Object.entries(stats.by_subsector ?? {}).map(
    ([name, value]) => ({ name, value }),
  )
  const riskData = Object.entries(stats.risk_flags ?? {}).map(
    ([name, value]) => ({ name: name.replace(/_/g, " "), value }),
  )

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Corpus Statistics</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Legal document coverage and distribution
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <MetricCard label="Total documents" value={stats.total_documents ?? 0} />
        <MetricCard label="Sources configured" value={stats.sources_configured ?? 0} />
        <MetricCard label="Incentive documents" value={stats.renewable_incentive_docs ?? 0} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard title="By norm type" data={normTypeData} layout="horizontal" />
        <ChartCard title="By subsector" data={subsectorData} layout="horizontal" />
      </div>

      <ChartCard title="Risk flags distribution" data={riskData} layout="vertical" />
    </div>
  )
}
