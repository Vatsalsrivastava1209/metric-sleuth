'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { generateApiKey } from './actions'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

type Profile = {
  id: string
  email?: string | null
  agency_name: string
  subscription_tier: string
  llm_backend: string
  llm_api_key_configured: boolean
  slack_webhook_url: string
  alert_email: string
  stripe_customer_id: string
}

export function SettingsWorkbench({ token, initialProfile }: { token: string; initialProfile: Profile }) {
  const [agencyName, setAgencyName] = useState(initialProfile.agency_name ?? '')
  const [llmBackend, setLlmBackend] = useState(initialProfile.llm_backend ?? 'gemini')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [slackWebhookUrl, setSlackWebhookUrl] = useState(initialProfile.slack_webhook_url ?? '')
  const [alertEmail, setAlertEmail] = useState(initialProfile.alert_email ?? '')
  const [message, setMessage] = useState('Agency branding and delivery preferences are saved through the backend API.')
  const [status, setStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [generatedKey, setGeneratedKey] = useState('')

  const saveSettings = async () => {
    setStatus('saving')
    setMessage('Persisting agency settings...')
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/account/profile`, {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          agency_name: agencyName || undefined,
          llm_backend: llmBackend,
          llm_api_key: llmApiKey || undefined,
          slack_webhook_url: slackWebhookUrl || undefined,
          alert_email: alertEmail || undefined,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Settings update failed with status ${response.status}`)
      }
      setStatus('success')
      setMessage(payload.message ?? 'Agency settings updated.')
      setLlmApiKey('')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Could not save agency settings.')
    }
  }

  const createApiKey = async () => {
    try {
      const formData = new FormData()
      formData.append('name', 'Next.js workspace key')
      const key = await generateApiKey(formData)
      setGeneratedKey(key)
      setStatus('success')
      setMessage('A new API key was generated. Store it now; it will not be shown again.')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Could not generate an API key.')
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="border-slate-800 bg-slate-900/60">
        <CardHeader>
          <CardTitle className="text-lg text-slate-200">Brand, AI, and Delivery</CardTitle>
          <CardDescription className="text-slate-400">
            Control the agency identity and channels used to prepare and distribute client investigation briefs.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">Agency name</label>
            <input
              type="text"
              value={agencyName}
              onChange={(event) => setAgencyName(event.target.value)}
              placeholder="Acme Growth Partners"
              className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
            <p className="text-xs text-slate-500">
              Used on client-ready exports so deliverables look like your agency, not ours.
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">LLM backend</label>
            <select
              value={llmBackend}
              onChange={(event) => setLlmBackend(event.target.value)}
              className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            >
              <option value="gemini">Gemini</option>
              <option value="openai">OpenAI</option>
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">LLM API key</label>
            <input
              type="password"
              value={llmApiKey}
              onChange={(event) => setLlmApiKey(event.target.value)}
              placeholder={initialProfile.llm_api_key_configured ? 'Key already configured. Paste to rotate it.' : 'Paste a provider key'}
              className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
            <p className="text-xs text-slate-500">
              Stored through the backend so encryption and vault handling stay server-side.
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">Slack webhook URL</label>
            <input
              type="url"
              value={slackWebhookUrl}
              onChange={(event) => setSlackWebhookUrl(event.target.value)}
              placeholder="https://hooks.slack.com/services/..."
              className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
            <p className="text-xs text-slate-500">
              Route incident alerts to the internal team channel that owns client follow-up.
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">Client update inbox</label>
            <input
              type="email"
              value={alertEmail}
              onChange={(event) => setAlertEmail(event.target.value)}
              placeholder="client-updates@youragency.com"
              className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
            <p className="text-xs text-slate-500">
              Use a shared inbox if multiple account managers review outbound summaries before delivery.
            </p>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-sm text-slate-300">
            {message}
          </div>

          <Button onClick={saveSettings} disabled={status === 'saving'} className="bg-blue-600 text-white hover:bg-blue-700">
            {status === 'saving' ? 'Saving...' : 'Save Settings'}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-6">
        <Card className="border-slate-800 bg-slate-900/60">
          <CardHeader>
            <CardTitle className="text-lg text-slate-200">Agency Snapshot</CardTitle>
            <CardDescription className="text-slate-400">Current operator identity and billing state.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-300">
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">Agency name</div>
              <div>{agencyName || 'Not configured'}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">Email</div>
              <div>{initialProfile.email || 'Unknown'}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">Subscription tier</div>
              <div>{initialProfile.subscription_tier.toUpperCase()}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">User ID</div>
              <div className="break-all font-mono text-xs">{initialProfile.id}</div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/60">
          <CardHeader>
            <CardTitle className="text-lg text-slate-200">API Keys</CardTitle>
            <CardDescription className="text-slate-400">
              Generate machine-to-machine keys for nightly client data syncs and automation jobs.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button variant="outline" className="border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800" onClick={createApiKey}>
              Generate API Key
            </Button>
            {generatedKey ? (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3">
                <div className="mb-1 text-xs uppercase tracking-wide text-emerald-300">New key</div>
                <div className="break-all font-mono text-sm text-emerald-100">{generatedKey}</div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
