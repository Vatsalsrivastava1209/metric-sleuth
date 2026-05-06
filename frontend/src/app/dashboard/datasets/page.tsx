import { redirect } from 'next/navigation'
import { createClient } from '@/utils/supabase/server'
import { DatasetWorkbench } from '../components/DatasetWorkbench'

export default async function DatasetsPage() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()

  if (error || !user) {
    redirect('/login')
  }

  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token ?? ''

  const [{ data: datasets }, { data: reports }] = await Promise.all([
    supabase
      .from('datasets')
      .select('id, name, connector_type, row_count, created_at')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false }),
    supabase
      .from('rca_reports')
      .select('dataset_id, anomaly_date, created_at')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(100),
  ])

  const reportCountByDataset = new Map<string, number>()
  const lastIncidentByDataset = new Map<string, string>()

  for (const report of reports ?? []) {
    if (!report.dataset_id) {
      continue
    }
    reportCountByDataset.set(report.dataset_id, (reportCountByDataset.get(report.dataset_id) ?? 0) + 1)
    if (!lastIncidentByDataset.has(report.dataset_id) && report.anomaly_date) {
      lastIncidentByDataset.set(report.dataset_id, String(report.anomaly_date))
    }
  }

  const enrichedDatasets = (datasets ?? []).map((dataset) => ({
    ...dataset,
    report_count: reportCountByDataset.get(dataset.id) ?? 0,
    last_incident_at: lastIncidentByDataset.get(dataset.id) ?? null,
  }))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">Client Workspaces</h1>
        <p className="mt-1 text-sm text-slate-400">
          Save storefront and channel exports as reusable client workspaces so the team can investigate fast without rebuilding context every time.
        </p>
      </div>

      <DatasetWorkbench token={token} initialDatasets={enrichedDatasets} />
    </div>
  )
}
