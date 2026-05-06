export default function ReportsLoading() {
  return (
    <div className="space-y-5 animate-pulse">
      <div className="flex items-end justify-between gap-3">
        <div className="space-y-1.5">
          <div className="h-6 w-24 rounded-md bg-slate-800" />
          <div className="h-4 w-56 rounded-md bg-slate-800/60" />
        </div>
        <div className="h-8 w-32 rounded-lg bg-slate-800" />
      </div>

      <div className="flex gap-1">
        {[...Array(5)].map((_, i) => <div key={i} className="h-7 w-16 rounded-lg bg-slate-800" />)}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3">
            <div className="flex justify-between">
              <div className="h-4 w-28 rounded bg-slate-800" />
              <div className="h-4 w-16 rounded bg-slate-800" />
            </div>
            <div className="space-y-1.5">
              <div className="h-3 w-full rounded bg-slate-800/60" />
              <div className="h-3 w-3/4 rounded bg-slate-800/60" />
              <div className="h-3 w-1/2 rounded bg-slate-800/60" />
            </div>
            <div className="flex gap-2">
              <div className="h-8 flex-1 rounded-md bg-slate-800" />
              <div className="h-8 flex-1 rounded-md bg-slate-800/60" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
