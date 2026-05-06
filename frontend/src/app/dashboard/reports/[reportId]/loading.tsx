export default function ReportDetailLoading() {
  return (
    <div className="space-y-5 md:space-y-6 animate-pulse">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2">
        <div className="h-3 w-10 rounded bg-slate-800" />
        <div className="h-3 w-2 rounded bg-slate-800" />
        <div className="h-3 w-14 rounded bg-slate-800" />
        <div className="h-3 w-2 rounded bg-slate-800" />
        <div className="h-3 w-24 rounded bg-slate-800" />
      </div>

      {/* Sticky bar */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-5 py-3 flex items-center justify-between gap-4">
        <div className="space-y-1.5">
          <div className="h-3 w-20 rounded bg-slate-800" />
          <div className="h-5 w-64 rounded bg-slate-800" />
        </div>
        <div className="flex gap-2">
          <div className="h-8 w-28 rounded-lg bg-slate-800" />
          <div className="h-8 w-20 rounded-md bg-slate-800/60" />
          <div className="h-8 w-20 rounded-md bg-slate-800/60" />
        </div>
      </div>

      {/* Content grid */}
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="grid gap-5 xl:grid-cols-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3 min-h-48">
              <div className="h-4 w-32 rounded bg-slate-800" />
              <div className="h-3 w-48 rounded bg-slate-800/60" />
              <div className="space-y-2 pt-2">
                {[...Array(3)].map((_, j) => (
                  <div key={j} className="h-14 rounded-lg bg-slate-800/50" />
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-48 rounded-xl border border-slate-800 bg-slate-900" />
          ))}
        </div>
      </div>
    </div>
  )
}
