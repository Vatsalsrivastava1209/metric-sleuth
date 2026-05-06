'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { ArrowRight, Bell, Plus, Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'

type Report = {
  id: string
  dataset_id: string | null
  anomaly_date: string | null
  primary_metric: string | null
  top_hypothesis: string | null
  confidence: number | null
  n_anomalies: number | null
  workflow_status: string | null
  report_payload: Record<string, unknown> | null
}

type DatasetInfo = { name: string }
type StatusFilter = 'all' | 'new' | 'in_review' | 'ready_to_send' | 'closed'

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: 'all',          label: 'All' },
  { key: 'new',          label: 'New' },
  { key: 'in_review',    label: 'In review' },
  { key: 'ready_to_send',label: 'Ready' },
  { key: 'closed',       label: 'Sent' },
]

const STATUS_MAP: Record<string, { dot: string; label: string }> = {
  new:           { dot: 'bg-slate-500',   label: 'New' },
  in_review:     { dot: 'bg-amber-400',   label: 'In review' },
  ready_to_send: { dot: 'bg-emerald-400', label: 'Ready to send' },
  closed:        { dot: 'bg-blue-400',    label: 'Sent' },
}

function StatusDot({ status }: { status: string }) {
  const s = STATUS_MAP[status] ?? { dot: 'bg-slate-500', label: status.replaceAll('_', ' ') }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
      <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', s.dot)} />
      {s.label}
    </span>
  )
}

function directionLabel(payload: Record<string, unknown> | null): '↓' | '↑' | null {
  const anomalies = Array.isArray((payload as { anomaly_summary?: unknown })?.anomaly_summary)
    ? (payload as { anomaly_summary: Array<{ direction?: string; deviation_score?: number }> }).anomaly_summary
    : []
  if (!anomalies.length) return null
  const worst = anomalies.reduce((a, b) => ((b.deviation_score ?? 0) > (a.deviation_score ?? 0) ? b : a))
  return worst.direction === 'drop' ? '↓' : '↑'
}

export function IncidentList({
  reports,
  datasets,
}: {
  reports: Report[]
  datasets: Record<string, DatasetInfo>
}) {
  const [search, setSearch] = useState('')
  const [activeStatus, setActiveStatus] = useState<StatusFilter>('all')
  const searchRef = useRef<HTMLInputElement>(null)

  // Press "/" to focus search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) {
        e.preventDefault()
        searchRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  const counts = reports.reduce<Record<string, number>>((acc, r) => {
    const k = r.workflow_status ?? 'new'
    acc[k] = (acc[k] ?? 0) + 1
    return acc
  }, {})

  const filtered = reports.filter((r) => {
    const name = (datasets[r.dataset_id ?? '']?.name ?? '').toLowerCase()
    const metric = (r.primary_metric ?? '').toLowerCase()
    const q = search.toLowerCase()
    return (!q || name.includes(q) || metric.includes(q)) &&
           (activeStatus === 'all' || r.workflow_status === activeStatus)
  })

  if (reports.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 py-16 sm:py-20 text-center px-4">
        <div className="rounded-2xl border border-slate-800 bg-slate-950 p-4 mb-4">
          <Bell className="h-8 w-8 text-slate-600" />
        </div>
        <h3 className="text-base font-medium text-slate-300">No open incidents</h3>
        <p className="mt-2 max-w-sm text-sm text-slate-500">
          Connect your first client workspace to start monitoring for anomalies.
        </p>
        <Link
          href="/dashboard/datasets"
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-amber-400 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add client workspace
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* ── Filter bar ──────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
        {/* Status tabs */}
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-none pb-0.5">
          {STATUS_TABS.map(({ key, label }) => {
            const count = key === 'all' ? reports.length : (counts[key] ?? 0)
            const active = activeStatus === key
            return (
              <button
                key={key}
                onClick={() => setActiveStatus(key)}
                className={cn(
                  'flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                  active ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                )}
              >
                {label}
                {count > 0 && (
                  <span className={cn(
                    'rounded-full px-1.5 py-0.5 text-[10px] font-bold leading-none',
                    active ? 'bg-amber-500 text-slate-950' : 'bg-slate-800 text-slate-500'
                  )}>
                    {count}
                  </span>
                )}
              </button>
            )
          })}
        </div>

        {/* Search */}
        <div className="relative sm:ml-auto">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-600" />
          <input
            ref={searchRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search clients… (/)"
            className="h-8 w-full sm:w-52 rounded-lg border border-slate-800 bg-slate-900 pl-8 pr-7 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-amber-400/40"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      {/* ── Table ────────────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">

        {/* Desktop header */}
        <div className="hidden sm:grid grid-cols-[1.8fr_1fr_1fr_1fr_auto] gap-4 px-5 py-3 border-b border-slate-800 bg-slate-900/60">
          {['Client', 'Metric', 'Date', 'Status', ''].map((h) => (
            <div key={h} className="text-[11px] uppercase tracking-[0.18em] text-slate-500 font-medium">{h}</div>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div className="px-5 py-12 text-center text-sm text-slate-500">
            No incidents match your filters.{' '}
            <button
              onClick={() => { setSearch(''); setActiveStatus('all') }}
              className="text-amber-400 hover:text-amber-300 transition-colors"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/60">
            {filtered.map((report) => {
              const name = datasets[report.dataset_id ?? '']?.name ?? 'Ad hoc'
              const dir  = directionLabel(report.report_payload)
              const conf = Math.round(Number(report.confidence ?? 0) * 100)
              const urgent = (report.workflow_status === 'new' || report.workflow_status === 'in_review') && conf >= 70

              const actions = (
                <>
                  <Link
                    href={`/dashboard/reports/${report.id}`}
                    className="rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[11px] font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors whitespace-nowrap"
                  >
                    Review
                  </Link>
                  <Link
                    href={`/dashboard/reports/${report.id}?audience=client`}
                    className="rounded border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] font-medium text-amber-200 hover:bg-amber-500/15 transition-colors whitespace-nowrap"
                  >
                    Client
                  </Link>
                </>
              )

              return (
                <div key={report.id}>
                  {/* Mobile card */}
                  <div className={cn('sm:hidden px-4 py-3.5 hover:bg-slate-800/30 transition-colors', urgent && 'border-l-2 border-l-amber-400/60')}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline gap-1.5 flex-wrap">
                          <span className="text-sm font-medium text-white">{name}</span>
                          {dir && <span className={cn('text-sm font-bold', dir === '↓' ? 'text-red-400' : 'text-emerald-400')}>{dir}</span>}
                          <span className="text-xs text-slate-500 font-mono">{report.primary_metric ?? ''}</span>
                        </div>
                        <div className="mt-0.5 text-xs text-slate-600 truncate">{report.top_hypothesis ?? 'No driver captured yet'}</div>
                        <div className="mt-1.5 flex items-center gap-3">
                          <StatusDot status={report.workflow_status ?? 'new'} />
                          <span className="text-xs text-slate-600">{report.anomaly_date ?? ''}</span>
                        </div>
                      </div>
                      <div className="shrink-0 flex flex-col items-end gap-2 pt-0.5">
                        {conf > 0 && <span className="text-[11px] text-slate-600">{conf}%</span>}
                        <div className="flex gap-1">{actions}</div>
                      </div>
                    </div>
                  </div>

                  {/* Desktop row */}
                  <div className={cn('hidden sm:grid grid-cols-[1.8fr_1fr_1fr_1fr_auto] gap-4 px-5 py-4 items-center hover:bg-slate-800/30 transition-colors', urgent && 'border-l-2 border-l-amber-400/60')}>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white truncate">{name}</span>
                        {urgent && (
                          <span className="shrink-0 rounded-full bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 text-[10px] font-medium text-amber-300">
                            Urgent
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 text-xs text-slate-500 truncate">{report.top_hypothesis ?? 'No driver captured yet'}</div>
                    </div>
                    <div className="text-sm text-slate-300">
                      {dir && <span className={cn('mr-1 font-bold', dir === '↓' ? 'text-red-400' : 'text-emerald-400')}>{dir}</span>}
                      {report.primary_metric ?? '—'}
                    </div>
                    <div className="text-sm text-slate-400">{report.anomaly_date ?? '—'}</div>
                    <div>
                      <StatusDot status={report.workflow_status ?? 'new'} />
                      {conf > 0 && <div className="mt-0.5 text-[11px] text-slate-600">{conf}% confidence</div>}
                    </div>
                    <div className="flex items-center gap-1.5">{actions}</div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        <div className="flex items-center justify-between px-5 py-3 border-t border-slate-800 bg-slate-900/60">
          <span className="text-xs text-slate-600">
            {filtered.length === reports.length ? `${reports.length} incidents` : `${filtered.length} of ${reports.length} incidents`}
          </span>
          <Link href="/dashboard/reports" className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">
            View all reports
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </div>
  )
}
