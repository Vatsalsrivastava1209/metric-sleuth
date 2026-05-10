import Link from 'next/link'
import { Activity, BellRing, CheckCircle2, FileText, Mail, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login, signup } from './actions'

const pillars = [
  {
    title: 'Portfolio monitoring',
    body: 'See which client accounts need attention before your team gets a surprise message.',
    icon: BellRing,
  },
  {
    title: 'Client-ready briefs',
    body: 'Turn internal investigations into summaries your agency can send without rewriting everything manually.',
    icon: FileText,
  },
  {
    title: 'Secure delivery',
    body: 'Keep client workspaces isolated with authenticated access, private storage, and audited exports.',
    icon: ShieldCheck,
  },
] as const

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; message?: string; mode?: string }>
}) {
  const { error, message, mode } = await searchParams
  const isSignUp = mode === 'signup'

  return (
    <div className="min-h-dvh bg-transparent text-slate-100 selection:bg-sky-500/30 relative overflow-hidden flex flex-col">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(255,255,255,0.03),_transparent_50%)]" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-3xl h-[1px] bg-gradient-to-r from-transparent via-sky-400/50 to-transparent" />
      <div className="relative mx-auto w-full max-w-7xl px-4 sm:px-6 py-8 sm:py-16 grid gap-10 lg:gap-16 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">

        {/* ── Left: value prop ─────────────────────────────────────────── */}
        <section className="space-y-6 lg:space-y-8">
          <div className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-[10px] uppercase tracking-[0.3em] font-medium text-slate-300 backdrop-blur-md shadow-[0_0_15px_rgba(255,255,255,0.05)]">
            Metric Sleuth
          </div>

          <div className="space-y-4">
            <h1 className="max-w-3xl text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-b from-white to-white/70 leading-[1.05] drop-shadow-sm">
              The anomaly desk for <span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-indigo-400">ecommerce agencies.</span>
            </h1>
            <p className="max-w-2xl text-lg sm:text-xl leading-relaxed text-slate-400 font-light">
              Monitor client accounts, rank likely drivers, and ship white-label investigation briefs faster than your reporting process can.
            </p>
          </div>

          {/* Pillars — hidden on mobile/tablet, shown on desktop */}
          <div className="hidden lg:grid gap-5 sm:grid-cols-3 mt-8">
            {pillars.map((pillar) => {
              const Icon = pillar.icon
              return (
                <div key={pillar.title} className="group glass rounded-3xl p-6 relative overflow-hidden transition-all hover:-translate-y-1 hover:shadow-[0_10px_40px_rgba(14,165,233,0.1)]">
                  <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                  <div className="inline-flex rounded-2xl border border-white/10 bg-white/5 p-3 shadow-inner backdrop-blur-md">
                    <Icon className="h-5 w-5 text-sky-400" />
                  </div>
                  <h2 className="mt-5 text-base font-semibold text-white tracking-tight">{pillar.title}</h2>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400 font-light">{pillar.body}</p>
                </div>
              )
            })}
          </div>

          {/* Compact trust line — shown on mobile/tablet instead of pillars */}
          <div className="lg:hidden flex flex-wrap gap-x-4 gap-y-2 mt-6">
            {['Portfolio monitoring', 'Client-ready briefs', 'Secure multi-tenant storage'].map((item) => (
              <span key={item} className="inline-flex items-center gap-2 text-sm text-slate-400 font-light">
                <CheckCircle2 className="h-3.5 w-3.5 text-sky-400 shrink-0" />
                {item}
              </span>
            ))}
          </div>

          {/* Testimonial block — desktop only */}
          <div className="hidden lg:block glass rounded-[28px] p-6 mt-8 relative overflow-hidden group">
            <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
            <div className="flex items-center gap-4">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-3 backdrop-blur-md">
                <Activity className="h-5 w-5 text-sky-400" />
              </div>
              <div>
                <div className="text-sm font-semibold text-white tracking-tight">Built for account managers and analytics leads</div>
                <div className="text-sm text-slate-400 font-light mt-0.5">
                  Connect client data, investigate the anomaly, review the brief, and send it.
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Right: auth form ─────────────────────────────────────────── */}
        <section className="relative group">
          <div className="absolute -inset-0.5 bg-gradient-to-b from-sky-400/20 to-transparent rounded-3xl opacity-0 lg:group-hover:opacity-100 transition-opacity duration-500 blur-md"></div>
          <Card className="relative glass border-white/10 bg-black/60 backdrop-blur-2xl text-slate-100 shadow-[0_32px_80px_rgba(0,0,0,0.8)] rounded-3xl overflow-hidden">

            {/* Tab toggle */}
            <div className="flex border-b border-white/10">
              <Link
                href="/login"
                className={`flex-1 py-4 text-center text-xs sm:text-sm font-medium transition-all ${
                  !isSignUp
                    ? 'text-white border-b-2 border-sky-400 bg-white/5 -mb-px'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.02]'
                }`}
              >
                Sign In
              </Link>
              <Link
                href="/login?mode=signup"
                className={`flex-1 py-4 text-center text-xs sm:text-sm font-medium transition-all ${
                  isSignUp
                    ? 'text-white border-b-2 border-sky-400 bg-white/5 -mb-px'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.02]'
                }`}
              >
                Create Account
              </Link>
            </div>

            <CardHeader className="space-y-1 pt-5">
              <CardTitle className="text-xl font-bold tracking-tight text-white">
                {isSignUp ? 'Create your agency workspace' : 'Welcome back'}
              </CardTitle>
              <CardDescription className="text-slate-400">
                {isSignUp ? 'Free to start — no card required.' : 'Sign in to your portfolio dashboard.'}
              </CardDescription>
            </CardHeader>

            <CardContent>
              {message === 'check-email' ? (
                <div className="flex flex-col items-center gap-4 rounded-2xl border border-sky-500/20 bg-sky-500/10 p-8 text-center backdrop-blur-md">
                  <div className="rounded-full border border-sky-500/20 bg-sky-500/10 p-4 shadow-[0_0_15px_rgba(14,165,233,0.15)]">
                    <Mail className="h-6 w-6 text-sky-400" />
                  </div>
                  <div>
                    <div className="text-lg font-semibold text-white tracking-tight">Check your inbox</div>
                    <p className="mt-2 text-sm text-slate-400 font-light leading-relaxed">
                      We sent you a confirmation link. Click it to activate your account, then sign in here.
                    </p>
                  </div>
                  <Link href="/login" className="mt-4 text-sm font-medium text-sky-400 hover:text-sky-300 transition-colors">
                    Back to Sign In
                  </Link>
                </div>
              ) : (
                <form className="space-y-4">
                  <div className="space-y-2.5">
                    <Label htmlFor="email" className="text-slate-200 font-medium tracking-tight">Email</Label>
                    <Input
                      id="email"
                      name="email"
                      type="email"
                      placeholder="ops@youragency.com"
                      required
                      autoComplete="email"
                      className="bg-white/5 border-white/10 text-slate-100 placeholder:text-slate-500 focus-visible:ring-sky-400/50 rounded-xl h-11 transition-all focus:bg-white/10"
                    />
                  </div>

                  <div className="space-y-2.5">
                    <Label htmlFor="password" className="text-slate-200 font-medium tracking-tight">Password</Label>
                    <Input
                      id="password"
                      name="password"
                      type="password"
                      placeholder={isSignUp ? 'At least 6 characters' : ''}
                      required
                      autoComplete={isSignUp ? 'new-password' : 'current-password'}
                      className="bg-white/5 border-white/10 text-slate-100 placeholder:text-slate-500 focus-visible:ring-sky-400/50 rounded-xl h-11 transition-all focus:bg-white/10"
                    />
                  </div>

                  {error && (
                    <p className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300 shadow-sm backdrop-blur-md">
                      {error}
                    </p>
                  )}

                  <div className="pt-2">
                    {isSignUp ? (
                      <>
                        <Button
                          formAction={signup}
                          className="w-full bg-white hover:bg-slate-100 hover:scale-[1.02] text-black font-semibold rounded-full h-11 transition-all shadow-[0_0_20px_rgba(255,255,255,0.15)]"
                        >
                          Create free account
                        </Button>
                        <div className="flex items-start gap-2 pt-4">
                          <CheckCircle2 className="h-3.5 w-3.5 text-sky-400 mt-0.5 shrink-0" />
                          <p className="text-xs text-slate-400 font-light leading-relaxed">
                            Free plan includes 3 client workspaces and unlimited investigations.
                          </p>
                        </div>
                      </>
                    ) : (
                      <>
                        <Button
                          formAction={login}
                          className="w-full bg-white hover:bg-slate-100 hover:scale-[1.02] text-black font-semibold rounded-full h-11 transition-all shadow-[0_0_20px_rgba(255,255,255,0.15)]"
                        >
                          Sign In
                        </Button>
                        <p className="text-center text-sm text-slate-400 pt-5 font-light">
                          No account yet?{' '}
                          <Link href="/login?mode=signup" className="text-sky-400 hover:text-sky-300 transition-colors font-medium">
                            Create one free
                          </Link>
                        </p>
                      </>
                    )}
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  )
}
