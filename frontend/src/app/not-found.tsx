import Link from 'next/link'
import { Activity, ArrowRight } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="min-h-dvh bg-slate-950 text-slate-100 flex flex-col items-center justify-center px-4">
      <div className="text-center space-y-6 max-w-md">

        <div className="inline-flex items-center gap-2">
          <Activity className="h-5 w-5 text-amber-400" />
          <span className="font-semibold text-white tracking-tight">Metric Sleuth</span>
        </div>

        <div>
          <div className="text-[96px] font-bold leading-none text-slate-800 select-none tabular-nums">404</div>
          <h1 className="mt-4 text-2xl font-semibold text-white">Page not found</h1>
          <p className="mt-2 text-slate-400 text-sm leading-7">
            The report, workspace, or URL you&apos;re looking for isn&apos;t here — it may have been deleted or the link is wrong.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-amber-400 transition-colors"
          >
            Go to inbox
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href="/dashboard/reports"
            className="inline-flex items-center rounded-lg border border-slate-700 px-5 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-900 transition-colors"
          >
            View all reports
          </Link>
        </div>
      </div>
    </div>
  )
}
