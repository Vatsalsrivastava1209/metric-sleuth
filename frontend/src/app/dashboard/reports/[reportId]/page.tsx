import type { Metadata } from 'next'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { ChevronRight, Download, Send, ShieldCheck } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { createClient } from '@/utils/supabase/server'
import { ReportWorkflowPanel } from './ReportWorkflowPanel'

export async function generateMetadata({
  params,
}: {
  params: Promise<{ reportId: string }>
}): Promise<Metadata> {
  const { reportId } = await params
  const supabase = await createClient()
  const { data: report } = await supabase
    .from('rca_reports')
    .select('primary_metric, anomaly_date')
    .eq('id', reportId)
    .single()
  if (!report) return { title: 'Report | Metric Sleuth' }
  return { title: `${report.primary_metric ?? 'Report'} · ${report.anomaly_date ?? ''} | Metric Sleuth` }
}

function formatConfidence(v: number | string | null | undefined) {
  if (v === null || v === undefined) return 'Not recorded'
  const n = Number(v)
  if (!Number.isFinite(n)) return 'Not recorded'
  return `${Math.round(n <= 1 ? n * 100 : n)}%`
}

function buildClientNarrative(
  report: {
    anomaly_date: string; primary_metric: string
    executive_summary?: string | null; top_hypothesis?: string | null
    n_anomalies?: number | null; n_hypotheses?: number | null
    confidence?: number | string | null
  },
  workspaceName: string, agencyName: string
) {
  return {
    intro: `${agencyName} detected an unusual movement in ${report.primary_metric} for ${workspaceName} on ${report.anomaly_date}.`,
    likelyDriver: report.top_hypothesis || 'No single dominant driver was stored — review the internal brief before sending.',
    recommendation: report.executive_summary || 'Use this brief as a draft, then add channel and merchandising context before sending.',
    evidence: [
      `Confidence: ${formatConfidence(report.confidence)}`,
      `Supporting anomalies reviewed: ${report.n_anomalies ?? 0}`,
      `Ranked hypotheses reviewed: ${report.n_hypotheses ?? 0}`,
    ],
  }
}

const sectionCls = 'rounded-lg border border-slate-800 bg-slate-950/70 p-3 sm:p-4'
const labelCls   = 'text-xs uppercase tracking-wide text-slate-500 mb-2'

export default async function ReportDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ reportId: string }>
  searchParams: Promise<{ audience?: string }>
}) {
  const { reportId } = await params
  const { audience } = await searchParams
  const activeAudience = audience === 'client' ? 'client' : 'internal'

  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) redirect('/login')

  const { data: report } = await supabase
    .from('rca_reports').select('*').eq('id', reportId).eq('user_id', user.id).single()
  if (!report) redirect('/dashboard/reports')

  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token ?? ''

  const [{ data: dataset }, { data: profile }, { data: comments }] = await Promise.all([
    report.dataset_id
      ? supabase.from('datasets').select('name').eq('id', report.dataset_id).eq('user_id', user.id).single()
      : Promise.resolve({ data: null }),
    supabase.from('profiles').select('full_name').eq('id', user.id).single(),
    supabase.from('incident_comments').select('id, author_email, body, created_at').eq('report_id', report.id).eq('user_id', user.id).order('created_at', { ascending: true }),
  ])

  const workspaceName   = dataset?.name ?? 'Ad hoc investigation'
  const agencyName      = profile?.full_name || 'Your Agency'
  const clientNarrative = buildClientNarrative(report, workspaceName, agencyName)

  const reportPayload = (report.report_payload ?? {}) as {
    anomaly_summary?: Array<{ date?: string; observed?: number | string; expected?: number | string; z_score?: number | string; direction?: string; metric?: string }>
    hypotheses?: Array<{ id?: string; title?: string; confidence?: number; description?: string; supporting_evidence?: string[] }>
    recommended_actions?: string[]
  }
  const topHypotheses     = (reportPayload.hypotheses ?? []).slice(0, 3)
  const anomalyEvidence   = (reportPayload.anomaly_summary ?? []).slice(0, 3)
  const recommendedActions = (reportPayload.recommended_actions ?? []).slice(0, 4)

  const workflowProps = {
    id: report.id,
    workflow_status: report.workflow_status ?? 'new',
    assigned_owner: report.assigned_owner ?? '',
    internal_notes: report.internal_notes ?? '',
    share_token: report.share_token ?? null,
    share_created_at: report.share_created_at ?? null,
    share_expires_at: report.share_expires_at ?? null,
    share_last_accessed_at: report.share_last_accessed_at ?? null,
    share_revoked_at: report.share_revoked_at ?? null,
    last_client_delivery_at: report.last_client_delivery_at ?? null,
    delivery_channel: report.delivery_channel ?? null,
    feedback_rating: report.feedback_rating ?? null,
    feedback_notes: report.feedback_notes ?? null,
  }

  return (
    <div className="space-y-5 md:space-y-6">

      {/* ── Breadcrumb ───────────────────────────────────────────────────── */}
      <nav className="flex items-center gap-1.5 text-xs text-slate-500 overflow-x-auto whitespace-nowrap">
        <Link href="/dashboard" className="hover:text-white transition-colors">Inbox</Link>
        <ChevronRight className="h-3 w-3 shrink-0" />
        <Link href="/dashboard/reports" className="hover:text-white transition-colors">Reports</Link>
        <ChevronRight className="h-3 w-3 shrink-0" />
        <span className="text-slate-300 truncate max-w-[160px] sm:max-w-xs">{workspaceName}</span>
      </nav>

      {/* ── Sticky audience toggle + export bar ──────────────────────────── */}
      <div className="sticky top-0 z-20 -mx-4 sm:-mx-6 md:-mx-8 px-4 sm:px-6 md:px-8 py-3 bg-slate-950/95 backdrop-blur border-b border-slate-800/60">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          {/* Title */}
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-[0.28em] text-slate-500">
              {activeAudience === 'client' ? 'Client-ready brief' : 'Internal investigation'}
            </p>
            <h1 className="mt-0.5 text-base sm:text-lg font-semibold text-white truncate">
              {workspaceName} · {report.primary_metric} · {report.anomaly_date}
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-2 shrink-0">
            {/* Audience toggle */}
            <div className="flex rounded-lg border border-slate-800 overflow-hidden">
              <Link
                href={`/dashboard/reports/${report.id}`}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeAudience === 'internal'
                    ? 'bg-blue-500/20 text-blue-200 border-r border-slate-800'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800 border-r border-slate-800'
                }`}
              >
                Internal
              </Link>
              <Link
                href={`/dashboard/reports/${report.id}?audience=client`}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeAudience === 'client'
                    ? 'bg-amber-500/20 text-amber-200'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                Client
              </Link>
            </div>

            {/* Export buttons */}
            <a
              href={`/api/reports/markdown?reportId=${encodeURIComponent(report.id)}&audience=${activeAudience}`}
              target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 transition-colors"
            >
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Markdown</span>
            </a>
            <a
              href={`/api/reports/pdf?reportId=${encodeURIComponent(report.id)}&audience=client`}
              target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-200 hover:bg-amber-500/20 transition-colors"
            >
              <Send className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Client PDF</span>
            </a>
          </div>
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────────────── */}
      {activeAudience === 'client' ? (

        /* Client mode: 2-col on lg+, stacked on mobile */
        <div className="grid gap-5 lg:grid-cols-[1fr_340px] xl:grid-cols-[1fr_380px]">
          <div className="space-y-5">
            <Card className="border-slate-800 bg-slate-900/60">
              <CardHeader>
                <CardTitle className="text-base text-slate-200">Client-facing summary</CardTitle>
                <CardDescription className="text-slate-500 text-sm">Prepared under {agencyName}.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-7 text-slate-300">
                <div className={sectionCls}>
                  <div className={labelCls}>What changed</div>
                  {clientNarrative.intro}
                </div>
                <div className={sectionCls}>
                  <div className={labelCls}>Likely driver</div>
                  {clientNarrative.likelyDriver}
                </div>
                <div className={sectionCls}>
                  <div className={labelCls}>Recommended update</div>
                  {clientNarrative.recommendation}
                </div>
              </CardContent>
            </Card>

            <Card className="border-slate-800 bg-slate-900/60">
              <CardHeader>
                <CardTitle className="text-base text-slate-200">Evidence snapshot</CardTitle>
                <CardDescription className="text-slate-500 text-sm">Client-safe context without the full analyst narrative.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-slate-300">
                {[
                  { label: 'Client workspace', value: workspaceName },
                  { label: 'Metric', value: report.primary_metric },
                  { label: 'Detection date', value: report.anomaly_date },
                ].map(({ label, value }) => (
                  <div key={label} className={sectionCls}>
                    <div className={labelCls}>{label}</div>
                    {value}
                  </div>
                ))}
                <div className={sectionCls}>
                  <div className={labelCls}>Investigation evidence</div>
                  <ul className="space-y-1 text-sm text-slate-300">
                    {clientNarrative.evidence.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
                <div className="flex items-start gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm leading-7 text-emerald-100">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
                  <p>This view is intentionally shorter than the internal report to keep the client update clean.</p>
                </div>
              </CardContent>
            </Card>
          </div>

          <div>
            <ReportWorkflowPanel
              reportId={report.id} token={token} agencyName={agencyName}
              initialWorkflow={workflowProps} initialComments={comments ?? []}
            />
          </div>
        </div>

      ) : (

        /* Internal mode: content (2-col on xl) + workflow panel */
        <div className="grid gap-5 lg:grid-cols-[1fr_340px] xl:grid-cols-[1fr_360px]">

          {/* Left: evidence cards */}
          <div className="grid gap-5 xl:grid-cols-2 xl:items-start">

            {/* Col A: Overview + Client preview */}
            <div className="space-y-5">
              <Card className="border-slate-800 bg-slate-900/60">
                <CardHeader>
                  <CardTitle className="text-base text-slate-200">Investigation overview</CardTitle>
                  <CardDescription className="text-slate-500 text-sm">Persisted metadata from the pipeline.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2.5 text-sm text-slate-300">
                  {[
                    { label: 'Client workspace', value: workspaceName },
                    { label: 'Metric',            value: report.primary_metric },
                    { label: 'Anomaly date',      value: report.anomaly_date },
                    { label: 'Confidence',        value: formatConfidence(report.confidence) },
                    { label: 'Top driver',        value: report.top_hypothesis || 'Not recorded' },
                    { label: 'Executive summary', value: report.executive_summary || 'Not recorded' },
                  ].map(({ label, value }) => (
                    <div key={label} className={sectionCls}>
                      <div className={labelCls}>{label}</div>
                      <div className="leading-7">{value}</div>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card className="border-slate-800 bg-slate-900/60">
                <CardHeader>
                  <CardTitle className="text-base text-slate-200">Client summary preview</CardTitle>
                  <CardDescription className="text-slate-500 text-sm">Sanity-check before switching to client mode.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm leading-7 text-slate-300">
                  <div className={sectionCls}>{clientNarrative.intro}</div>
                  <div className={sectionCls}>{clientNarrative.recommendation}</div>
                </CardContent>
              </Card>
            </div>

            {/* Col B: Evidence + Drivers + Actions */}
            <div className="space-y-5">
              <Card className="border-slate-800 bg-slate-900/60">
                <CardHeader>
                  <CardTitle className="text-base text-slate-200">Why this was flagged</CardTitle>
                  <CardDescription className="text-slate-500 text-sm">Raw evidence from the anomaly payload.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-slate-300">
                  {anomalyEvidence.length === 0 ? (
                    <div className={sectionCls}>No structured anomaly evidence stored.</div>
                  ) : anomalyEvidence.map((item, i) => (
                    <div key={`${item.metric}-${i}`} className={sectionCls}>
                      <div className={labelCls}>{item.metric || report.primary_metric}</div>
                      <div className="text-sm leading-7 text-slate-200">
                        Observed {String(item.observed ?? 'n/a')} vs baseline {String(item.expected ?? 'n/a')}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">
                        {item.direction || 'direction unknown'} · z-score {String(item.z_score ?? 'n/a')}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card className="border-slate-800 bg-slate-900/60">
                <CardHeader>
                  <CardTitle className="text-base text-slate-200">Ranked likely drivers</CardTitle>
                  <CardDescription className="text-slate-500 text-sm">Evidence-backed, not guaranteed causal.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-slate-300">
                  {topHypotheses.length === 0 ? (
                    <div className={sectionCls}>No driver list stored.</div>
                  ) : topHypotheses.map((h) => (
                    <div key={h.id ?? h.title} className={sectionCls}>
                      <div className="flex items-center justify-between gap-3 mb-2">
                        <span className="text-sm font-medium text-white">{h.title || 'Unnamed driver'}</span>
                        {h.confidence !== undefined && (
                          <span className="text-[11px] text-slate-500 shrink-0">
                            {Math.round(Number(h.confidence) * 100)}% confidence
                          </span>
                        )}
                      </div>
                      <p className="leading-7 text-slate-300">{h.description || 'No explanation stored.'}</p>
                      {(h.supporting_evidence ?? []).length > 0 && (
                        <ul className="mt-2 space-y-0.5 text-xs text-slate-500">
                          {(h.supporting_evidence ?? []).slice(0, 3).map((ev) => <li key={ev}>— {ev}</li>)}
                        </ul>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card className="border-slate-800 bg-slate-900/60">
                <CardHeader>
                  <CardTitle className="text-base text-slate-200">Recommended actions</CardTitle>
                  <CardDescription className="text-slate-500 text-sm">For the analyst handoff and client follow-up.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm text-slate-300">
                  {recommendedActions.length === 0 ? (
                    <div className={sectionCls}>No structured actions stored.</div>
                  ) : recommendedActions.map((action, i) => (
                    <div key={`${i}-${action}`} className={sectionCls}>
                      {i + 1}. {action}
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Right: Workflow panel */}
          <div className="lg:sticky lg:top-[120px] lg:self-start">
            <ReportWorkflowPanel
              reportId={report.id} token={token} agencyName={agencyName}
              initialWorkflow={workflowProps} initialComments={comments ?? []}
            />
          </div>
        </div>
      )}

      {/* Full markdown — internal only */}
      {activeAudience === 'internal' && (
        <Card className="border-slate-800 bg-slate-900/60">
          <CardHeader>
            <CardTitle className="text-base text-slate-200">Full internal markdown</CardTitle>
            <CardDescription className="text-slate-500 text-sm">Stored investigation narrative for the analyst team.</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-950/80 p-4 text-xs sm:text-sm leading-7 text-slate-200">
              {report.report_md || 'No markdown body was stored for this report.'}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
