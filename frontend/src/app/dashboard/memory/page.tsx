import { redirect } from 'next/navigation'
import { createClient } from '@/utils/supabase/server'
import { MemoryWorkbench } from './MemoryWorkbench'

const API_BASE_URL = process.env.METRICSLEUTH_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function fetchMemoryData(token: string) {
  const headers = { Authorization: `Bearer ${token}` }

  const [statsResponse, reportsResponse] = await Promise.all([
    fetch(`${API_BASE_URL.replace(/\/$/, '')}/api/v1/memory/stats`, { headers, cache: 'no-store' }),
    fetch(`${API_BASE_URL.replace(/\/$/, '')}/api/v1/memory/reports`, { headers, cache: 'no-store' }),
  ])

  if (!statsResponse.ok || !reportsResponse.ok) {
    return {
      stats: { total_documents: 0, index_dir: 'data/rag_index', is_empty: true },
      reports: [],
    }
  }

  const stats = await statsResponse.json()
  const reportPayload = await reportsResponse.json()
  return { stats, reports: reportPayload.reports ?? [] }
}

export default async function MemoryPage() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()

  if (error || !user) {
    redirect('/login')
  }

  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token ?? ''

  const { data: profile } = await supabase
    .from('profiles')
    .select('subscription_tier')
    .eq('id', user.id)
    .single()

  const tier = profile?.subscription_tier ?? 'free'
  const isEligible = tier === 'pro' || tier === 'business'
  const { stats, reports } = isEligible ? await fetchMemoryData(token) : { stats: { total_documents: 0, index_dir: 'data/rag_index', is_empty: true }, reports: [] }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">Pattern Library</h1>
        <p className="mt-1 text-sm text-slate-400">
          Search prior incidents before your team drafts a new client update.
        </p>
      </div>

      {isEligible ? (
        <MemoryWorkbench token={token} initialReports={reports} initialDocumentCount={stats.total_documents ?? 0} />
      ) : (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6 text-sm text-slate-300">
          Pattern Library access is available on Growth and Portfolio plans.
        </div>
      )}
    </div>
  )
}
