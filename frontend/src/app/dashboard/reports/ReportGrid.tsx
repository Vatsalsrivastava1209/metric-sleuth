'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, Bell, ChevronDown, FolderKanban, Search, Send, X } from 'lucide-react'
import { cn } from '@/lib/utils'

type Report = {
  id: string
  dataset_id: string | null
  anomaly_date: string | null
  primary_metric: string | null
  executive_summary: string | null
  top_hypothesis: string | null
  n_anomalies: number | null
  n_hypotheses: number | null
  created_at: string
  workflow_status: string | null
  assigned_owner: string | null
  last_client_delivery_at: string | null
  confidence: number | null
}

type StatusFilter = 'all' | 'new' | 'investigating' | 'ready_to_send' | 'sent'
type SortKey = 'newest' | 'confidence' | 'anomalies'

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: 'all',           label: 'All' },
  { key: 'new',           label: 'New' },
  { key: 'investigating', label: 'Investigating' },
  { key: 'ready_to_send', label: 'Ready' },
  { key: 'sent',          label: 'Sent' },
]

const STATUS_MAP: Record<string, { dot: string; label: string }> = {
  new:           { dot: 'bg-slate-500',   label: 'New' },
  investigating: { dot: 'bg-amber-400',   label: 'Investigating' },
  ready_to_send: { dot: 'bg-emerald-400', label: 'Ready to send' },
  sent:          { dot: 'bg-blue-400',    label: 'Sent' },
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

export function ReportGrid({
  reports,
  datasetNames,
}: {
  reports: Report[]
  datasetNames: Record<string, string>
}) {
  const [search, setSearch] = useState('')
  const [activeStatus, setActiveStatus] = useState<StatusFilter>('all')
  const [sort, setSort] = useState<SortKey>('newest')
  const [sortOpen, setSortOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)

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

  const filtered = reports
    .filter((r) => {
      const name = (datasetNames[r.dataset_id ?? ''] ?? '').toLowerCase()
      const metric = (r.primary_metric ?? '').toLowerCase()
      const q = search.toLowerCase()
      return (!q || name.includes(q) || metric.includes(q)) &&
             (activeStatus === 'all' || r.workflow_status === activeStatus)
    })
    .sort((a, b) => {
      if (sort === 'confidence') return Number(b.confidence ?? 0) - Number(a.confidence ?? 0)
      if (sort === 'anomalies')  return Number(b.n_anomalies ?? 0) - Number(a.n_anomalies ?? 0)
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

  const SORT_LABELS: Record<SortKey, string> = {
    newest:     'Newest first',
    confidence: 'Highest confidence',
    anomalies:  'Most anomalies',
  }

  if (reports.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 py-16 sm:py-20 text-center px-4">
        <div className="rounded-2xl border border-slate-800 bg-slate-950 p-4 mb-4">
          <Bell className="h-8 w-8 text-slate-600" />
        </div>
        <h3 className="text-base font-medium text-slate-300">No investigation briefs yet</h3>
        <p className="mt-2 max-w-sm text-sm text-slate-500">
          Run your first investigation from the Inbox or connect a client workspace to get started.
        </p>
        <Link
          href="/dashboard"
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-amber-400 transition-colors"
        >
          Go to Inbox
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-4">
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

        <div className="flex items-center gap-2 sm:ml-auto">
          {/* Search */}
          <div className="relative flex-1 sm:flex-none">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-600" />
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search… (/)"
              className="h-8 w-full sm:w-48 rounded-lg border border-slate-800 bg-slate-900 pl-8 pr-7 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-amber-400/40"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                <X className="h-3 w-3" />
              </button>
            )}
          </div>

          {/* Sort */}
          <div className="relative">
            <button
              onClick={() => setSortOpen((o) => !o)}
              className="h-8 flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 text-xs text-slate-400 hover:text-white transition-colors"
            >
              {SORT_LABELS[sort]}
              <ChevronDown className="h-3 w-3" />
            </button>
            {sortOpen && (
              <div className="absolute right-0 top-9 z-10 w-44 rounded-xl border border-slate-800 bg-slate-950 shadow-xl">
                {(Object.keys(SORT_LABELS) as SortKey[]).map((k) => (
                  <button
                    key={k}
                    onClick={() => { setSort(k); setSortOpen(false) }}
                    className={cn(
                      'w-full px-3 py-2.5 text-left text-xs transition-colors hover:bg-slate-800',
                      sort === k ? 'text-amber-400' : 'text-slate-300'
                    )}
                  >
                    {SORT_LABELS[k]}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Grid ─────────────────────────────────────────────────────────── */}
      {filtered.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 px-5 py-12 text-center text-sm text-slate-500">
          No reports match your filters.{' '}
          <button onClick={() => { setSearch(''); setActiveStatus('all') }} className="text-amber-400 hover:text-amber-300">
            Clear
          </button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((report) => {
            const workspaceName = report.dataset_id ? (datasetNames[report.dataset_id] ?? 'Ad hoc') : 'Ad hoc investigation'
            const conf = Math.round(Number(report.confidence ?? 0) * 100)

            return (
              <div key={report.id} className="flex flex-col rounded-2xl border border-slate-800 bg-slate-900 hover:border-slate-700 transition-colors overflow-hidden">
                {/* Card header */}
                <div className="px-4 pt-4 pb-3 border-b border-slate-800/60">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-white truncate">{workspaceName}</p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {report.primary_metric ?? 'metric'} · {new Date(report.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="shrink-0 text-right space-y-1">
                      <div className="text-xs font-mono text-slate-500">{report.anomaly_date}</div>
                      <StatusDot status={report.workflow_status ?? 'new'} />
                    </div>
                  </div>
                </div>

                {/* Card body */}
                <div className="flex-1 px-4 py-3 space-y-3">
                  <p className="text-sm leading-6 text-slate-300 line-clamp-3">
                    {report.top_hypothesis ?? report.executive_summary ?? 'No summary recorded for this investigation.'}
                  </p>

                  <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3 text-amber-400" />
                      {report.n_anomalies ?? 0} anomalies
                    </span>
                    <span className="flex items-center gap-1">
                      <FolderKanban className="h-3 w-3 text-sky-400" />
                      {report.n_hypotheses ?? 0} drivers
                    </span>
                    {conf > 0 && (
                      <span className={cn(
                        'font-semibold',
                        conf >= 80 ? 'text-emerald-400' : conf >= 55 ? 'text-amber-400' : 'text-slate-500'
                      )}>
                        {conf}% confidence
                      </span>
                    )}
                  </div>

                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-500">
                    {report.assigned_owner ? `Owner: ${report.assigned_owner}` : 'Unassigned'}
                    {' · '}
                    {report.last_client_delivery_at
                      ? `Sent ${new Date(report.last_client_delivery_at).toLocaleDateString()}`
                      : 'Not delivered yet'}
                  </div>
                </div>

                {/* Card footer */}
                <div className="px-4 pb-4 pt-0 space-y-2">
                  <div className="flex gap-2">
                    <Link
                      href={`/dashboard/reports/${report.id}`}
                      className="flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-center text-xs font-medium text-slate-200 hover:bg-slate-800 transition-colors"
                    >
                      Internal brief
                    </Link>
                    <Link
                      href={`/dashboard/reports/${report.id}?audience=client`}
                      className="flex-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-center text-xs font-medium text-amber-200 hover:bg-amber-500/20 transition-colors"
                    >
                      Client view
                    </Link>
                  </div>
                  <div className="flex items-center gap-3 px-0.5">
                    <a
                      href={`/api/reports/markdown?reportId=${encodeURIComponent(report.id)}&audience=internal`}
                      target="_blank" rel="noreferrer"
                      className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                    >
                      Markdown
                    </a>
                    <a
                      href={`/api/reports/pdf?reportId=${encodeURIComponent(report.id)}&audience=client`}
                      target="_blank" rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                    >
                      <Send className="h-3 w-3" />
                      Client PDF
                    </a>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <p className="text-xs text-slate-600 text-right">
        {filtered.length === reports.length ? `${reports.length} reports` : `${filtered.length} of ${reports.length} reports`}
      </p>
    </div>
  )
}
