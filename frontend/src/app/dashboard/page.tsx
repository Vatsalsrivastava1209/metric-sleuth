import type { Metadata } from 'next'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { AlertTriangle, ArrowRight, BriefcaseBusiness, Clock, Database, Plus } from 'lucide-react'
import { createClient } from '@/utils/supabase/server'
import { AnalyzeForm } from './components/AnalyzeForm'
import { IncidentList } from './components/IncidentList'
import { CollapsibleSection } from './components/CollapsibleSection'
import { cn } from '@/lib/utils'

export const metadata: Metadata = { title: 'Inbox | Metric Sleuth' }

function severityScore(r: { confidence?: number | null; n_anomalies?: number | null }) {
  return (Number(r.confidence ?? 0) * 10) + (Number(r.n_anomalies ?? 0) * 0.5)
}

function countRecent(records: Array<{ created_at?: string | null }>, days: number) {
  const cutoff = Date.now() - days * 864e5
  return records.filter((r) => {
    const t = new Date(r.created_at ?? '').getTime()
    return Number.isFinite(t) && t >= cutoff
  }).length
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ datasetId?: string }>
}) {
  const { datasetId } = await searchParams
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) redirect('/login')

  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token ?? ''

  const [{ data: datasets }, { data: reports }, { data: runs }] = await Promise.all([
    supabase.from('datasets').select('id, name, connector_type, row_count, created_at').eq('user_id', user.id).order('created_at', { ascending: false }),
    // NOTE: report_payload is intentionally excluded here — it can be 50-200 KB per
    // report, and loading it for 50 reports on every dashboard render transfers up to
    // 5 MB of JSON per page load. The full payload is fetched on the individual report
    // detail page only. (P0-C audit fix)
    supabase.from('rca_reports').select('id, dataset_id, anomaly_date, primary_metric, top_hypothesis, confidence, n_anomalies, created_at, workflow_status').eq('user_id', user.id).order('created_at', { ascending: false }).limit(50),
    supabase.from('analysis_runs').select('status, started_at, completed_at, created_at').eq('user_id', user.id).order('created_at', { ascending: false }).limit(120),
  ])

  const datasetRows = datasets ?? []
  const reportRows  = reports  ?? []

  // Build enriched datasets
  const reportCountByDataset = new Map<string, number>()
  const lastIncidentByDataset = new Map<string, string>()
  for (const r of reportRows) {
    if (!r.dataset_id) continue
    reportCountByDataset.set(r.dataset_id, (reportCountByDataset.get(r.dataset_id) ?? 0) + 1)
    if (!lastIncidentByDataset.has(r.dataset_id) && r.anomaly_date)
      lastIncidentByDataset.set(r.dataset_id, String(r.anomaly_date))
  }
  const enrichedDatasets = datasetRows.map((d) => ({
    ...d,
    report_count:     reportCountByDataset.get(d.id) ?? 0,
    last_incident_at: lastIncidentByDataset.get(d.id) ?? null,
  }))

  const selectedDatasetId = datasetId && datasetRows.some((d) => d.id === datasetId) ? datasetId : ''

  // KPI values
  const openIncidents = countRecent(reportRows, 14)
  const readyToSend   = reportRows.filter((r) => r.workflow_status === 'ready_to_send').length
  const coverageGaps  = enrichedDatasets.filter((d) => d.report_count === 0).length
  const durations = (runs ?? [])
    .map((r) => {
      if (!r.started_at || !r.completed_at) return null
      const ms = new Date(r.completed_at).getTime() - new Date(r.started_at).getTime()
      return ms > 0 ? Math.round(ms / 60000 * 10) / 10 : null
    })
    .filter((v): v is number => v !== null)
    .sort((a, b) => a - b)
  const medianMinutes = durations.length ? durations[Math.floor(durations.length / 2)] : 0

  const sortedReports = [...reportRows]
    .sort((a, b) => severityScore(b) - severityScore(a))

  // Dataset map for IncidentList (serializable)
  const datasetMap: Record<string, { name: string }> = {}
  for (const d of datasetRows) datasetMap[d.id] = { name: d.name }

  return (
    <div className="space-y-5 md:space-y-6">

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg sm:text-xl font-semibold text-white">Inbox</h1>
          <p className="mt-0.5 text-sm text-slate-500">Client incidents ranked by severity</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {readyToSend > 0 && (
            <Link
              href="/dashboard/reports?status=ready_to_send"
              className="hidden sm:inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-3 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 transition-colors"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              {readyToSend} ready
            </Link>
          )}
          <Link
            href="/dashboard/datasets"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Add client</span>
            <span className="sm:hidden">Add</span>
          </Link>
        </div>
      </div>

      {/* ── Onboarding banner — only on first login (no datasets yet) ────── */}
      {datasetRows.length === 0 && (
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-start gap-4">
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold text-white">Welcome to Metric Sleuth</h2>
              <p className="mt-1 text-sm text-slate-400">
                You&apos;re three steps away from your first client investigation.
              </p>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {[
                  { n: 1, title: 'Add a client workspace', desc: 'Connect Shopify, GA4, Meta Ads, or upload a CSV.' },
                  { n: 2, title: 'Run an investigation',   desc: 'The engine ranks anomalies and likely drivers automatically.' },
                  { n: 3, title: 'Send the brief',         desc: 'Export a white-label PDF or push the summary to Slack.' },
                ].map(({ n, title, desc }) => (
                  <div key={n} className="flex items-start gap-2.5">
                    <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-[11px] font-bold text-amber-400">
                      {n}
                    </div>
                    <div>
                      <div className="text-xs font-medium text-slate-200">{title}</div>
                      <div className="mt-0.5 text-xs text-slate-500 leading-5">{desc}</div>
                    </div>
                  </div>
                ))}
              </div>
              <Link
                href="/dashboard/datasets"
                className="mt-5 inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-400 transition-colors"
              >
                Add your first client
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* ── KPI pills ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:flex sm:flex-wrap gap-2 sm:gap-3">
        {[
          { icon: BriefcaseBusiness, label: 'Clients',        value: enrichedDatasets.length },
          { icon: AlertTriangle,     label: 'Open (14d)',      value: openIncidents,  warn: openIncidents > 0 },
          { icon: Database,          label: 'Coverage gaps',   value: coverageGaps,   warn: coverageGaps > 0 },
          { icon: Clock,             label: 'Median to brief', value: `${medianMinutes}m` },
        ].map(({ icon: Icon, label, value, warn }) => (
          <div
            key={label}
            className={cn(
              'flex items-center gap-2 rounded-xl border px-3 py-2.5 text-sm',
              warn ? 'border-amber-500/20 bg-amber-500/5' : 'border-slate-800 bg-slate-900/60'
            )}
          >
            <Icon className={cn('h-4 w-4 shrink-0', warn ? 'text-amber-400' : 'text-slate-500')} />
            <span className="font-semibold text-white">{value}</span>
            <span className="text-xs text-slate-500 truncate">{label}</span>
          </div>
        ))}
      </div>

      {/* ── Incident inbox ───────────────────────────────────────────────── */}
      <IncidentList reports={sortedReports} datasets={datasetMap} />

      {/* ── Analyst Workbench (collapsible) ──────────────────────────────── */}
      <CollapsibleSection
        title="Run investigation"
        description="Investigate a saved client workspace or upload a fresh CSV"
        defaultOpen={reportRows.length === 0}
      >
        <AnalyzeForm token={token} savedDatasets={enrichedDatasets} initialDatasetId={selectedDatasetId} />
      </CollapsibleSection>
    </div>
  )
}
