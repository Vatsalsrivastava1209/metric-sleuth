import { notFound } from 'next/navigation'
import { ShieldCheck } from 'lucide-react'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

type PublicBrief = {
  agency_name: string
  workspace_name: string
  anomaly_date: string
  primary_metric: string
  executive_summary: string
  likely_driver: string
  evidence: string[]
  report_id: string
}

export default async function PublicBriefPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const { token } = await params
  const response = await fetch(`${API_BASE_URL}/api/v1/public/brief/${encodeURIComponent(token)}`, {
    cache: 'no-store',
  })

  if (!response.ok) {
    notFound()
  }

  const brief = (await response.json()) as PublicBrief

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="rounded-3xl border border-slate-800 bg-slate-900/60 p-8">
          <div className="text-xs uppercase tracking-[0.28em] text-slate-500">{brief.agency_name}</div>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-white">Client incident brief</h1>
          <p className="mt-3 max-w-2xl text-base leading-8 text-slate-300">
            {brief.workspace_name} saw an unusual movement in {brief.primary_metric} on {brief.anomaly_date}. This summary is a client-safe view of the stored investigation.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="space-y-6">
            <section className="rounded-3xl border border-slate-800 bg-slate-900/60 p-6">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Likely driver</div>
              <div className="mt-3 text-2xl font-medium text-white">{brief.likely_driver}</div>
              <p className="mt-4 text-sm leading-8 text-slate-300">{brief.executive_summary}</p>
            </section>

            <section className="rounded-3xl border border-slate-800 bg-slate-900/60 p-6">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-500">What we reviewed</div>
              <div className="mt-4 space-y-3 text-sm text-slate-300">
                {brief.evidence.map((item) => (
                  <div key={item} className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                    {item}
                  </div>
                ))}
              </div>
            </section>
          </div>

          <section className="space-y-6 rounded-3xl border border-slate-800 bg-slate-900/60 p-6">
            <div className="text-xs uppercase tracking-[0.22em] text-slate-500">Brief details</div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-300">
              <div className="text-xs uppercase tracking-wide text-slate-500">Workspace</div>
              <div className="mt-2">{brief.workspace_name}</div>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-300">
              <div className="text-xs uppercase tracking-wide text-slate-500">Metric</div>
              <div className="mt-2">{brief.primary_metric}</div>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-300">
              <div className="text-xs uppercase tracking-wide text-slate-500">Detection date</div>
              <div className="mt-2">{brief.anomaly_date}</div>
            </div>
            <div className="flex items-start gap-3 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm leading-7 text-emerald-100">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                This client brief intentionally excludes internal analyst notes and only exposes the evidence needed for external communication.
              </p>
            </div>
          </section>
        </div>
      </div>
    </main>
  )
}
