import Link from 'next/link'
import { redirect } from 'next/navigation'
import { ArrowRight, BellRing, FileText, LineChart, ShieldCheck } from 'lucide-react'
import { createClient } from '@/utils/supabase/server'

const outcomes = [
  {
    title: 'Catch client issues before the panic message',
    body: 'Flag revenue, traffic, and conversion anomalies before account managers get ambushed in Slack.',
    icon: BellRing,
  },
  {
    title: 'Move from raw data to a usable explanation fast',
    body: 'Turn storefront and channel data into ranked likely drivers with evidence instead of another dashboard tab.',
    icon: LineChart,
  },
  {
    title: 'Send a brief that looks like your agency wrote it',
    body: 'Package the internal investigation into a client-ready summary your team can review and send.',
    icon: FileText,
  },
] as const

const proofPoints = [
  'Built for ecommerce and paid media agencies, not generic enterprise analytics teams.',
  'Designed around client workspaces, incident triage, and white-label investigation briefs.',
  'Secure multi-tenant storage, async investigations, and role-aware exports from day one.',
] as const

function MockStatus({ status }: { status: 'new' | 'in_review' | 'ready' | 'watch' }) {
  const map = {
    new:       { dot: 'bg-slate-500',   label: 'New' },
    in_review: { dot: 'bg-amber-400',   label: 'In review' },
    ready:     { dot: 'bg-emerald-400', label: 'Ready to send' },
    watch:     { dot: 'bg-blue-400',    label: 'Watch only' },
  }
  const s = map[status]
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-400 whitespace-nowrap">
      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${s.dot}`} />
      {s.label}
    </span>
  )
}

export default async function Home() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (user) redirect('/dashboard')

  return (
    <main className="min-h-dvh bg-slate-950 text-slate-100">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b border-slate-800">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(14,165,233,0.18),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(245,158,11,0.14),_transparent_28%)]" />

        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 pt-14 sm:pt-20 pb-12 sm:pb-16">

          <div className="inline-flex items-center rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs uppercase tracking-[0.28em] text-sky-300 mb-6 sm:mb-8">
            For ecommerce &amp; paid media agencies
          </div>

          <h1 className="max-w-3xl text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight text-white leading-[1.1]">
            Your client&apos;s revenue just dropped.
            <br className="hidden sm:block" />
            {' '}<span className="text-amber-400">You&apos;ll know why in 5 minutes.</span>
          </h1>

          <p className="mt-5 sm:mt-6 max-w-xl text-base sm:text-lg leading-8 text-slate-400">
            Metric Sleuth monitors client KPIs, explains the likely drivers automatically, and produces a client-ready brief — before anyone has to ask.
          </p>

          <div className="mt-6 sm:mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/login?mode=signup"
              className="inline-flex items-center rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-amber-400"
            >
              Start free — no card required
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center rounded-lg border border-slate-700 bg-slate-950/70 px-5 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-slate-900"
            >
              Sign in
            </Link>
          </div>

          <div className="mt-8 sm:mt-10 flex flex-wrap gap-3 sm:gap-4">
            {[
              { value: '10 – 100', label: 'client accounts per agency' },
              { value: '1 workflow', label: 'detect → explain → send' },
              { value: '0 fluff', label: 'no generic BI, just agency ops' },
            ].map(({ value, label }) => (
              <div key={label} className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 sm:px-5 py-2.5 sm:py-3">
                <div className="text-lg sm:text-xl font-semibold text-white">{value}</div>
                <div className="mt-0.5 text-xs text-slate-500">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Mock dashboard ───────────────────────────────────────────────── */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 py-12 sm:py-16">
        <div className="text-center mb-8 sm:mb-10">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500 mb-2">Monday morning, 9am</p>
          <h2 className="text-xl sm:text-2xl font-semibold text-white">Everything your team needs to triage, in one view</h2>
        </div>

        <div className="mx-auto max-w-2xl rounded-[24px] border border-slate-800 bg-slate-900/70 p-4 sm:p-6 shadow-[0_40px_100px_rgba(0,0,0,0.5)] backdrop-blur">
          <div className="flex items-start sm:items-center justify-between border-b border-slate-800 pb-4 mb-4 gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Portfolio inbox</div>
              <div className="mt-1 text-sm sm:text-base font-semibold text-white">3 incidents need attention</div>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 sm:px-3 py-1 text-xs font-medium text-amber-300 shrink-0">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              2 urgent
            </span>
          </div>

          <div className="space-y-2">
            {[
              { name: 'Aurelia Skin',       metric: '↓ revenue',          note: 'Mobile CVR down 22%. Traffic held.',               status: 'in_review' as const },
              { name: 'Northstar Outdoors', metric: '↓ conversion_rate',  note: 'Checkout drop, desktop only. GA4 lag possible.',   status: 'ready' as const },
              { name: 'Luna Home',          metric: '↑ traffic',          note: 'Branded search spike — monitor before escalating.', status: 'watch' as const },
            ].map((item) => (
              <div key={item.name} className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/60 px-3 sm:px-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-white">{item.name}</span>
                    <span className="text-xs text-slate-500 font-mono">{item.metric}</span>
                  </div>
                  <div className="mt-0.5 text-xs text-slate-500 truncate">{item.note}</div>
                </div>
                <MockStatus status={item.status} />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Outcomes ─────────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 pb-12 sm:pb-16">
        <div className="grid gap-4 sm:gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {outcomes.map((outcome) => {
            const Icon = outcome.icon
            return (
              <div key={outcome.title} className="rounded-2xl border border-slate-800 bg-slate-900/50 p-5 sm:p-6">
                <div className="inline-flex rounded-xl border border-slate-700 bg-slate-950/80 p-2.5 mb-4">
                  <Icon className="h-5 w-5 text-amber-400" />
                </div>
                <h3 className="text-base font-semibold text-white">{outcome.title}</h3>
                <p className="mt-2 text-sm leading-7 text-slate-400">{outcome.body}</p>
              </div>
            )
          })}
        </div>
      </section>

      {/* ── Why agencies buy ─────────────────────────────────────────────── */}
      <section className="border-t border-slate-800 bg-slate-900/30">
        <div className="mx-auto grid max-w-7xl gap-8 sm:gap-10 px-4 sm:px-6 py-12 sm:py-16 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-4">
            <div className="inline-flex items-center rounded-full border border-slate-700 bg-slate-950/70 px-3 py-1 text-xs uppercase tracking-[0.28em] text-slate-400">
              Why agencies buy
            </div>
            <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-white">
              The product is the workflow:<br className="hidden sm:block" /> detect, explain, review, send.
            </h2>
            <p className="max-w-xl text-base leading-8 text-slate-400">
              Not a BI tool. Not a dashboard. A faster operating loop for the repeated work agencies actually bill for.
            </p>
          </div>
          <div className="space-y-3">
            {proofPoints.map((point) => (
              <div key={point} className="flex items-start gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <ShieldCheck className="mt-0.5 h-4 w-4 text-emerald-400 shrink-0" />
                <p className="text-sm leading-7 text-slate-300">{point}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 py-12 sm:py-16">
        <div className="rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-8 sm:p-10 text-center">
          <div className="inline-flex items-center rounded-full border border-amber-500/20 bg-amber-500/10 px-3 py-1 text-xs uppercase tracking-[0.24em] text-amber-300 mb-5 sm:mb-6">
            Built for ecommerce agency teams
          </div>
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-white max-w-2xl mx-auto">
            Replace reactive reporting with proactive client operations.
          </h2>
          <p className="mt-4 text-base text-slate-400 max-w-xl mx-auto">
            Connect client workspaces, review the anomaly inbox, and deliver evidence-backed updates that make your team look prepared.
          </p>
          <div className="mt-6 sm:mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/login?mode=signup"
              className="inline-flex items-center rounded-lg bg-amber-500 px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-400"
            >
              Start free
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center rounded-lg border border-slate-700 px-5 sm:px-6 py-2.5 sm:py-3 text-sm font-medium text-slate-300 transition hover:bg-slate-900"
            >
              Sign in to dashboard
            </Link>
          </div>
        </div>
      </section>
    </main>
  )
}
