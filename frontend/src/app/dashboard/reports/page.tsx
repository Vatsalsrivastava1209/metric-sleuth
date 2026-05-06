import type { Metadata } from 'next'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { Plus } from 'lucide-react'
import { createClient } from '@/utils/supabase/server'
import { ReportGrid } from './ReportGrid'

export const metadata: Metadata = { title: 'Reports | Metric Sleuth' }

export default async function ReportsPage({
  searchParams,
}: {
  searchParams: Promise<{ datasetId?: string }>
}) {
  const { datasetId } = await searchParams
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const [reportsResult, datasetsResult] = await Promise.all([
    supabase
      .from('rca_reports')
      .select('id, dataset_id, anomaly_date, primary_metric, executive_summary, top_hypothesis, n_anomalies, n_hypotheses, created_at, workflow_status, assigned_owner, last_client_delivery_at, confidence')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false }),
    supabase.from('datasets').select('id, name').eq('user_id', user.id),
  ])

  const allReports = reportsResult.data ?? []
  const datasetRows = datasetsResult.data ?? []

  const reports = allReports.filter((r) => datasetId ? r.dataset_id === datasetId : true)

  const datasetNames: Record<string, string> = {}
  for (const d of datasetRows) datasetNames[d.id] = d.name

  const selectedWorkspaceName = datasetId ? datasetNames[datasetId] : null

  return (
    <div className="space-y-5 md:space-y-6">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-lg sm:text-xl font-semibold text-white">Reports</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            {selectedWorkspaceName
              ? `Showing reports for ${selectedWorkspaceName}`
              : 'All investigation briefs across client workspaces'}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {selectedWorkspaceName && (
            <Link
              href="/dashboard/reports"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 transition-colors"
            >
              ← All reports
            </Link>
          )}
          <Link
            href="/dashboard/datasets"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            New investigation
          </Link>
        </div>
      </div>

      {/* ── Grid (search + filter + sort handled client-side) ────────────── */}
      <ReportGrid reports={reports} datasetNames={datasetNames} />
    </div>
  )
}
