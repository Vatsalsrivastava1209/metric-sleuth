import { redirect } from 'next/navigation'
import { AlertTriangle, Clock3, Send, Siren } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { createClient } from '@/utils/supabase/server'

function median(values: number[]) {
  if (!values.length) {
    return 0
  }
  const sorted = [...values].sort((a, b) => a - b)
  const midpoint = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? Math.round(((sorted[midpoint - 1] + sorted[midpoint]) / 2) * 10) / 10
    : sorted[midpoint]
}

function getCurrentTimeMs() {
  return Date.now()
}

function isStuckRun(updatedAt: string | null | undefined, createdAt: string | null | undefined) {
  const updated = new Date(updatedAt ?? createdAt ?? '').getTime()
  return Number.isFinite(updated) && updated < getCurrentTimeMs() - 15 * 60 * 1000
}

function isDeliveredRecently(deliveredAt: string | null | undefined) {
  const delivered = deliveredAt ? new Date(deliveredAt).getTime() : Number.NaN
  return Number.isFinite(delivered) && delivered >= getCurrentTimeMs() - 30 * 24 * 60 * 60 * 1000
}

export default async function OpsPage() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()

  if (error || !user) {
    redirect('/login')
  }

  const [{ data: runs }, { data: reports }] = await Promise.all([
    supabase
      .from('analysis_runs')
      .select('status, started_at, completed_at, updated_at, created_at')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(200),
    supabase
      .from('rca_reports')
      .select('id, workflow_status, last_client_delivery_at, created_at')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(200),
  ])

  const durations = (runs ?? [])
    .map((run) => {
      if (!run.started_at || !run.completed_at) {
        return null
      }
      const started = new Date(run.started_at).getTime()
      const completed = new Date(run.completed_at).getTime()
      if (!Number.isFinite(started) || !Number.isFinite(completed) || completed < started) {
        return null
      }
      return (completed - started) / 60000
    })
    .filter((value): value is number => value !== null)
  const failedRuns = (runs ?? []).filter((run) => run.status === 'FAILURE')
  const stuckRuns = (runs ?? []).filter((run) => {
    if (run.status !== 'RUNNING') {
      return false
    }
    return isStuckRun(run.updated_at, run.created_at)
  })
  const deliveredLast30Days = (reports ?? []).filter((report) => isDeliveredRecently(report.last_client_delivery_at)).length
  const readyToSend = (reports ?? []).filter((report) => report.workflow_status === 'ready_to_send').length

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">Agency Ops</h1>
        <p className="mt-1 text-sm text-slate-400">
          Reliability and ROI signals for the active workspace portfolio. Use this page before bigger deployments and after any workflow change.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          {
            label: 'Median time to brief',
            value: `${median(durations)}m`,
            note: 'Typical elapsed time from run start to completed brief',
            icon: Clock3,
          },
          {
            label: 'Delivered in 30d',
            value: deliveredLast30Days.toLocaleString(),
            note: 'Client briefs recorded as delivered recently',
            icon: Send,
          },
          {
            label: 'Ready to send',
            value: readyToSend.toLocaleString(),
            note: 'Incidents waiting for outbound client delivery',
            icon: AlertTriangle,
          },
          {
            label: 'Stuck or failed',
            value: `${stuckRuns.length + failedRuns.length}`,
            note: 'Runs needing operator review',
            icon: Siren,
          },
        ].map((item) => {
          const Icon = item.icon
          return (
            <Card key={item.label} className="border-slate-800 bg-slate-900/60">
              <CardContent className="flex items-start justify-between p-5">
                <div>
                  <div className="text-xs uppercase tracking-[0.22em] text-slate-500">{item.label}</div>
                  <div className="mt-3 text-3xl font-semibold text-white">{item.value}</div>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{item.note}</p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-3">
                  <Icon className="h-5 w-5 text-amber-300" />
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="border-slate-800 bg-slate-900/60">
          <CardHeader>
            <CardTitle className="text-lg text-slate-200">Run health watchlist</CardTitle>
            <CardDescription className="text-slate-400">
              Investigations that need operator attention because they failed or may be stuck in the queue.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-300">
            {stuckRuns.length === 0 && failedRuns.length === 0 ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-4">
                No stuck or failed runs are visible in the recent sample.
              </div>
            ) : (
              <>
                {stuckRuns.map((run, index) => (
                  <div key={`stuck-${index}`} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4">
                    RUNNING too long since {new Date(run.updated_at ?? run.created_at ?? '').toLocaleString()}
                  </div>
                ))}
                {failedRuns.map((run, index) => (
                  <div key={`failed-${index}`} className="rounded-lg border border-red-500/20 bg-red-500/10 p-4">
                    FAILURE recorded at {new Date(run.updated_at ?? run.created_at ?? '').toLocaleString()}
                  </div>
                ))}
              </>
            )}
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/60">
          <CardHeader>
            <CardTitle className="text-lg text-slate-200">Operator guidance</CardTitle>
            <CardDescription className="text-slate-400">
              The product only earns trust if this page stays boring.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-7 text-slate-300">
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-4">
              Review every `ready to send` incident before weekly client reporting cycles.
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-4">
              If stuck or failed runs trend upward, pause outbound promises and verify worker health before sales calls.
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-4">
              Median time to brief is a real ROI signal. If it drifts upward, the platform is getting harder to operate.
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
