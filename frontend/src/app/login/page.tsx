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
    <div className="min-h-dvh bg-slate-950 text-slate-100">
      <div className="mx-auto grid min-h-dvh max-w-7xl gap-8 px-4 sm:px-6 py-8 sm:py-10
                      lg:grid-cols-[1.1fr_0.9fr] lg:items-center">

        {/* ── Left: value prop ─────────────────────────────────────────── */}
        <section className="space-y-6 lg:space-y-8">
          <div className="inline-flex items-center rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs uppercase tracking-[0.26em] text-sky-200">
            Metric Sleuth
          </div>

          <div className="space-y-3">
            <h1 className="max-w-3xl text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-tight text-white">
              The anomaly desk for ecommerce agencies.
            </h1>
            <p className="max-w-2xl text-base sm:text-lg leading-8 text-slate-300">
              Monitor client accounts, rank likely drivers, and ship white-label investigation briefs faster than your reporting process can.
            </p>
          </div>

          {/* Pillars — hidden on mobile/tablet, shown on desktop */}
          <div className="hidden lg:grid gap-4 sm:grid-cols-3">
            {pillars.map((pillar) => {
              const Icon = pillar.icon
              return (
                <div key={pillar.title} className="rounded-3xl border border-slate-800 bg-slate-900/60 p-5">
                  <div className="inline-flex rounded-2xl border border-slate-700 bg-slate-950/70 p-3">
                    <Icon className="h-4 w-4 text-amber-300" />
                  </div>
                  <h2 className="mt-4 text-base font-medium text-white">{pillar.title}</h2>
                  <p className="mt-2 text-sm leading-7 text-slate-400">{pillar.body}</p>
                </div>
              )
            })}
          </div>

          {/* Compact trust line — shown on mobile/tablet instead of pillars */}
          <div className="lg:hidden flex flex-wrap gap-x-4 gap-y-2">
            {['Portfolio monitoring', 'Client-ready briefs', 'Secure multi-tenant storage'].map((item) => (
              <span key={item} className="inline-flex items-center gap-1.5 text-sm text-slate-400">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                {item}
              </span>
            ))}
          </div>

          {/* Testimonial block — desktop only */}
          <div className="hidden lg:block rounded-[28px] border border-slate-800 bg-slate-900/60 p-6">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-slate-700 bg-slate-950/80 p-3">
                <Activity className="h-5 w-5 text-emerald-300" />
              </div>
              <div>
                <div className="text-sm font-medium text-white">Built for account managers and analytics leads</div>
                <div className="text-sm text-slate-400">
                  Connect client data, investigate the anomaly, review the brief, and send it.
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Right: auth form ─────────────────────────────────────────── */}
        <section>
          <Card className="border-slate-800 bg-slate-900/80 text-slate-100 shadow-[0_32px_80px_rgba(2,6,23,0.42)]">

            {/* Tab toggle */}
            <div className="flex border-b border-slate-800">
              <Link
                href="/login"
                className={`flex-1 py-3.5 text-center text-sm font-medium transition-colors ${
                  !isSignUp
                    ? 'text-white border-b-2 border-amber-400 -mb-px'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Sign In
              </Link>
              <Link
                href="/login?mode=signup"
                className={`flex-1 py-3.5 text-center text-sm font-medium transition-colors ${
                  isSignUp
                    ? 'text-white border-b-2 border-amber-400 -mb-px'
                    : 'text-slate-400 hover:text-slate-200'
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
                <div className="flex flex-col items-center gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-6 text-center">
                  <div className="rounded-full border border-emerald-500/20 bg-emerald-500/10 p-3">
                    <Mail className="h-5 w-5 text-emerald-400" />
                  </div>
                  <div>
                    <div className="font-medium text-emerald-300">Check your inbox</div>
                    <p className="mt-1 text-sm text-slate-400">
                      We sent you a confirmation link. Click it to activate your account, then sign in here.
                    </p>
                  </div>
                  <Link href="/login" className="mt-2 text-sm text-amber-400 hover:text-amber-300 transition-colors">
                    Back to Sign In
                  </Link>
                </div>
              ) : (
                <form className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email" className="text-slate-200">Email</Label>
                    <Input
                      id="email"
                      name="email"
                      type="email"
                      placeholder="ops@youragency.com"
                      required
                      autoComplete="email"
                      className="bg-slate-950 border-slate-800 text-slate-100 placeholder:text-slate-500 focus-visible:ring-amber-400/40"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="password" className="text-slate-200">Password</Label>
                    <Input
                      id="password"
                      name="password"
                      type="password"
                      placeholder={isSignUp ? 'At least 6 characters' : ''}
                      required
                      autoComplete={isSignUp ? 'new-password' : 'current-password'}
                      className="bg-slate-950 border-slate-800 text-slate-100 placeholder:text-slate-500 focus-visible:ring-amber-400/40"
                    />
                  </div>

                  {error && (
                    <p className="rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                      {error}
                    </p>
                  )}

                  {isSignUp ? (
                    <>
                      <Button
                        formAction={signup}
                        className="w-full bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold"
                      >
                        Create free account
                      </Button>
                      <div className="flex items-start gap-2 pt-1">
                        <CheckCircle2 className="h-3.5 w-3.5 text-slate-500 mt-0.5 shrink-0" />
                        <p className="text-xs text-slate-500">
                          Free plan includes 3 client workspaces and unlimited investigations.
                        </p>
                      </div>
                    </>
                  ) : (
                    <>
                      <Button
                        formAction={login}
                        className="w-full bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold"
                      >
                        Sign In
                      </Button>
                      <p className="text-center text-xs text-slate-500 pt-1">
                        No account yet?{' '}
                        <Link href="/login?mode=signup" className="text-amber-400 hover:text-amber-300 transition-colors">
                          Create one free
                        </Link>
                      </p>
                    </>
                  )}
                </form>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  )
}
