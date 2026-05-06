import { redirect } from 'next/navigation'
import { createClient } from '@/utils/supabase/server'
import { SettingsWorkbench } from './SettingsWorkbench'

export default async function SettingsPage() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()

  if (error || !user) {
    redirect('/login')
  }

  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token ?? ''

  const { data: profile } = await supabase
    .from('profiles')
    // P1-D: llm_api_key (deprecated plaintext column) is intentionally excluded.
    // We only need llm_api_key_vault_id to know whether a key is configured.
    // Selecting the raw column exposes legacy keys for tenants with incomplete
    // Vault migrations. Use llm_api_key_vault_id as the single source of truth.
    .select('id, email, full_name, subscription_tier, llm_backend, llm_api_key_vault_id, slack_webhook_url, alert_email, stripe_customer_id')
    .eq('id', user.id)
    .single()

  const normalizedProfile = {
    id: user.id,
    email: user.email,
    agency_name: profile?.full_name ?? '',
    subscription_tier: profile?.subscription_tier ?? 'free',
    llm_backend: profile?.llm_backend ?? 'gemini',
    llm_api_key_configured: Boolean(profile?.llm_api_key_vault_id),  // P1-D: only vault ID is authoritative
    slack_webhook_url: profile?.slack_webhook_url ?? '',
    alert_email: profile?.alert_email ?? '',
    stripe_customer_id: profile?.stripe_customer_id ?? '',
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">Agency Settings</h1>
        <p className="mt-1 text-sm text-slate-400">
          Configure branding, alert delivery, and the automation credentials behind client-facing investigations.
        </p>
      </div>

      <SettingsWorkbench token={token} initialProfile={normalizedProfile} />
    </div>
  )
}
