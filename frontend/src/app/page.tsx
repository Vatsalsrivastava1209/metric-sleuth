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
    new:       { dot: 'bg-slate-400',   glow: 'shadow-[0_0_8px_rgba(148,163,184,0.6)]', label: 'New' },
    in_review: { dot: 'bg-amber-400',   glow: 'shadow-[0_0_8px_rgba(251,191,36,0.6)]', label: 'In review' },
    ready:     { dot: 'bg-emerald-400', glow: 'shadow-[0_0_8px_rgba(52,211,153,0.6)]', label: 'Ready to send' },
    watch:     { dot: 'bg-sky-400',     glow: 'shadow-[0_0_8px_rgba(56,189,248,0.6)]', label: 'Watch only' },
  }
  const s = map[status]
  return (
    <span className="inline-flex items-center gap-2 text-xs font-medium text-slate-400 whitespace-nowrap bg-black/40 px-2.5 py-1 rounded-full border border-white/5">
      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${s.dot} ${s.glow}`} />
      {s.label}
    </span>
  )
}

export default async function Home() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (user) redirect('/dashboard')

  return (
    <main className="min-h-dvh bg-transparent text-slate-100 selection:bg-sky-500/30">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b border-white/5">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(255,255,255,0.05),_transparent_50%)]" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-3xl h-[1px] bg-gradient-to-r from-transparent via-sky-400/50 to-transparent" />

        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 pt-20 sm:pt-32 pb-16 sm:pb-24 text-center flex flex-col items-center">

          <div className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs uppercase tracking-[0.2em] font-medium text-slate-300 backdrop-blur-md mb-8 shadow-[0_0_15px_rgba(255,255,255,0.05)]">
            For ecommerce &amp; paid media agencies
          </div>

          <h1 className="max-w-4xl text-4xl sm:text-5xl lg:text-7xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-b from-white to-white/70 leading-[1.1] drop-shadow-sm">
            Your client&apos;s revenue dropped.
            <br className="hidden sm:block" />
            {' '}<span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-indigo-400">Know why in 5 minutes.</span>
          </h1>

          <p className="mt-6 sm:mt-8 max-w-2xl text-base sm:text-xl leading-relaxed text-slate-400 font-light">
            Metric Sleuth monitors client KPIs, explains the likely drivers automatically, and produces a client-ready brief — before anyone has to ask.
          </p>

          <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 w-full px-2">
            <Link
              href="/login?mode=signup"
              className="group flex w-full sm:w-auto justify-center items-center rounded-full bg-white px-8 py-3.5 text-sm font-semibold text-black transition-all hover:scale-105 hover:bg-slate-100 hover:shadow-[0_0_20px_rgba(255,255,255,0.3)]"
            >
              Start free — no card required
              <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <Link
              href="/login"
              className="flex w-full sm:w-auto justify-center items-center rounded-full border border-white/10 bg-white/5 backdrop-blur-md px-8 py-3.5 text-sm font-medium text-white transition-all hover:bg-white/10 hover:border-white/20"
            >
              Sign in
            </Link>
          </div>

          <div className="mt-12 sm:mt-16 grid grid-cols-1 sm:flex sm:flex-wrap justify-center gap-3 sm:gap-6 w-full">
            {[
              { value: '10 – 100', label: 'client accounts per agency' },
              { value: '1 workflow', label: 'detect → explain → send' },
              { value: '0 fluff', label: 'no generic BI, just agency ops' },
            ].map(({ value, label }) => (
              <div key={label} className="glass rounded-2xl px-5 sm:px-6 py-4 text-center sm:min-w-[160px] w-full sm:w-auto">
                <div className="text-xl sm:text-2xl font-bold text-white tracking-tight">{value}</div>
                <div className="mt-1 text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</div>
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

        <div className="mx-auto max-w-3xl glass rounded-3xl p-1 sm:p-2 shadow-[0_40px_100px_rgba(0,0,0,0.8)] relative group overflow-hidden sm:overflow-visible">
          <div className="absolute -inset-0.5 bg-gradient-to-b from-sky-400/20 to-transparent rounded-[26px] opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-md"></div>
          <div className="relative rounded-[22px] bg-black/80 p-4 sm:p-8 backdrop-blur-2xl border border-white/10">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between border-b border-white/10 pb-4 mb-4 gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.3em] text-sky-400 font-semibold mb-1">Portfolio inbox</div>
                <div className="text-base sm:text-lg font-semibold text-white tracking-tight">3 incidents need attention</div>
              </div>
              <span className="inline-flex items-center gap-2 rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-300 shrink-0 shadow-[0_0_10px_rgba(244,63,94,0.1)]">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                </span>
                2 urgent
              </span>
            </div>

            <div className="space-y-3">
              {[
                { name: 'Aurelia Skin',       metric: '↓ revenue',          note: 'Mobile CVR down 22%. Traffic held.',               status: 'in_review' as const },
                { name: 'Northstar Outdoors', metric: '↓ conversion_rate',  note: 'Checkout drop, desktop only. GA4 lag possible.',   status: 'ready' as const },
                { name: 'Luna Home',          metric: '↑ traffic',          note: 'Branded search spike — monitor before escalating.', status: 'watch' as const },
              ].map((item) => (
                <div key={item.name} className="group/item flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4 rounded-2xl border border-white/5 bg-white/[0.02] px-4 py-4 transition-all hover:bg-white/[0.04] hover:border-white/10">
                  <div className="min-w-0 w-full">
                    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                      <span className="text-sm font-semibold text-white">{item.name}</span>
                      <span className="rounded-md bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-400 font-mono border border-white/5">{item.metric}</span>
                    </div>
                    <div className="mt-1.5 text-xs sm:text-sm text-slate-400 sm:truncate line-clamp-2 sm:line-clamp-none">{item.note}</div>
                  </div>
                  <div className="w-full sm:w-auto flex justify-start sm:justify-end">
                    <MockStatus status={item.status} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Outcomes ─────────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 pb-16 sm:pb-24">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {outcomes.map((outcome) => {
            const Icon = outcome.icon
            return (
              <div key={outcome.title} className="glass rounded-3xl p-6 sm:p-8 relative group overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                <div className="inline-flex rounded-2xl border border-white/10 bg-white/5 p-3 mb-6 shadow-inner backdrop-blur-md">
                  <Icon className="h-6 w-6 text-sky-400" />
                </div>
                <h3 className="text-lg font-semibold text-white tracking-tight">{outcome.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-slate-400 font-light">{outcome.body}</p>
              </div>
            )
          })}
        </div>
      </section>

      {/* ── Why agencies buy ─────────────────────────────────────────────── */}
      <section className="border-y border-white/5 bg-white/[0.01] relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_bottom_left,_rgba(139,92,246,0.05),_transparent_40%)]" />
        <div className="relative mx-auto grid max-w-7xl gap-12 sm:gap-16 px-4 sm:px-6 py-16 sm:py-24 lg:grid-cols-[1.1fr_0.9fr] items-center">
          <div className="space-y-6">
            <div className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-[10px] uppercase tracking-[0.3em] text-slate-300 backdrop-blur-md">
              Why agencies buy
            </div>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-white leading-tight">
              The product is the workflow.<br className="hidden sm:block" />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-slate-400 to-slate-600">Detect, explain, review, send.</span>
            </h2>
            <p className="max-w-xl text-lg leading-relaxed text-slate-400 font-light">
              Not a BI tool. Not a dashboard. A faster operating loop for the repeated work agencies actually bill for.
            </p>
          </div>
          <div className="space-y-4">
            {proofPoints.map((point) => (
              <div key={point} className="flex items-start gap-4 rounded-2xl border border-white/5 bg-black/40 p-5 backdrop-blur-md transition hover:border-white/10 hover:bg-white/[0.02]">
                <div className="rounded-full bg-emerald-400/10 p-1.5 shrink-0 mt-0.5">
                  <ShieldCheck className="h-4 w-4 text-emerald-400" />
                </div>
                <p className="text-sm leading-relaxed text-slate-300 font-light">{point}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-5xl px-4 sm:px-6 py-16 sm:py-32">
        <div className="glass rounded-3xl sm:rounded-[40px] p-6 sm:p-16 text-center relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-sky-400/10 via-transparent to-indigo-400/10" />
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-1/2 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          
          <div className="relative z-10">
            <div className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-[10px] uppercase tracking-[0.3em] font-medium text-slate-300 backdrop-blur-md mb-6 sm:mb-8">
              Built for ecommerce agency teams
            </div>
            <h2 className="text-3xl sm:text-5xl font-bold tracking-tight text-white max-w-2xl mx-auto leading-tight">
              Replace reactive reporting with <span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-indigo-400">proactive operations.</span>
            </h2>
            <p className="mt-4 sm:mt-6 text-base sm:text-lg text-slate-400 max-w-xl mx-auto font-light leading-relaxed">
              Connect client workspaces, review the anomaly inbox, and deliver evidence-backed updates that make your team look prepared.
            </p>
            <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
              <Link
                href="/login?mode=signup"
                className="group flex w-full sm:w-auto justify-center items-center rounded-full bg-white px-8 py-3.5 text-sm font-semibold text-black transition-all hover:scale-105 hover:bg-slate-100 hover:shadow-[0_0_20px_rgba(255,255,255,0.3)]"
              >
                Start free trial
                <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <Link
                href="/login"
                className="flex w-full sm:w-auto justify-center items-center rounded-full border border-white/10 bg-white/5 backdrop-blur-md px-8 py-3.5 text-sm font-medium text-white transition-all hover:bg-white/10 hover:border-white/20"
              >
                Sign in to dashboard
              </Link>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}
