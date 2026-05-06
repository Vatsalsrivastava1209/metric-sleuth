import { redirect } from 'next/navigation'
import { createClient } from '@/utils/supabase/server'
import { BillingWorkbench } from './BillingWorkbench'

export default async function BillingPage() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()

  if (error || !user) {
    redirect('/login')
  }

  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token ?? ''

  const { data: profile } = await supabase
    .from('profiles')
    .select('subscription_tier, stripe_customer_id')
    .eq('id', user.id)
    .single()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">Portfolio Plans</h1>
        <p className="mt-1 text-sm text-slate-400">
          Price the product by client account coverage, white-label delivery, and agency automation instead of generic seat count.
        </p>
      </div>

      <BillingWorkbench
        token={token}
        profile={{
          subscription_tier: profile?.subscription_tier ?? 'free',
          stripe_customer_id: profile?.stripe_customer_id ?? '',
        }}
      />
    </div>
  )
}
