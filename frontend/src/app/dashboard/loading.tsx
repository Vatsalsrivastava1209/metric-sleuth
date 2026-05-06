export default function DashboardLoading() {
  return (
    <div className="space-y-5 md:space-y-6 animate-pulse">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5">
          <div className="h-6 w-16 rounded-md bg-slate-800" />
          <div className="h-4 w-44 rounded-md bg-slate-800/60" />
        </div>
        <div className="h-8 w-24 rounded-lg bg-slate-800" />
      </div>

      <div className="grid grid-cols-2 sm:flex gap-2 sm:gap-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-10 rounded-xl bg-slate-800 sm:w-36" />
        ))}
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
        <div className="hidden sm:grid grid-cols-[1.8fr_1fr_1fr_1fr_auto] gap-4 px-5 py-3 border-b border-slate-800 bg-slate-900/60">
          {[...Array(5)].map((_, i) => <div key={i} className="h-3 w-16 rounded bg-slate-800" />)}
        </div>
        {[...Array(5)].map((_, i) => (
          <div key={i} className="px-5 py-4 border-b border-slate-800/60 flex gap-4 items-center">
            <div className="flex-1 space-y-1.5">
              <div className="h-4 w-32 rounded bg-slate-800" />
              <div className="h-3 w-48 rounded bg-slate-800/60" />
            </div>
            <div className="h-4 w-20 rounded bg-slate-800 hidden sm:block" />
            <div className="h-4 w-16 rounded bg-slate-800 hidden sm:block" />
            <div className="h-4 w-20 rounded bg-slate-800 hidden sm:block" />
            <div className="h-7 w-24 rounded bg-slate-800" />
          </div>
        ))}
      </div>
    </div>
  )
}
