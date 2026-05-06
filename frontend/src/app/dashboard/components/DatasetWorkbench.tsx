'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, Database, Loader2, PlugZap, Sparkles, Trash2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const CANONICAL_FIELDS = [
  'date',
  'revenue',
  'traffic',
  'orders',
  'conversion_rate',
  'region',
  'device',
  'traffic_source',
] as const
const REQUIRED_FIELDS = new Set(['date', 'revenue', 'traffic', 'orders', 'conversion_rate'])
const INTEGRATION_FIELDS: Record<string, Array<{ name: string; label: string; type?: string; placeholder?: string }>> = {
  shopify: [
    { name: 'shop_domain', label: 'Shop domain', placeholder: 'acme.myshopify.com' },
    { name: 'access_token', label: 'Admin API access token', type: 'password' },
  ],
  ga4: [
    { name: 'property_id', label: 'GA4 property ID', placeholder: '123456789' },
    { name: 'access_token', label: 'OAuth access token', type: 'password' },
  ],
  meta_ads: [
    { name: 'ad_account_id', label: 'Ad account ID', placeholder: 'act_123456789 or 123456789' },
    { name: 'access_token', label: 'Long-lived access token', type: 'password' },
  ],
  google_ads: [
    { name: 'customer_id', label: 'Customer ID', placeholder: '1234567890' },
    { name: 'developer_token', label: 'Developer token', type: 'password' },
    { name: 'access_token', label: 'OAuth access token', type: 'password' },
    { name: 'login_customer_id', label: 'Manager account ID (optional)', placeholder: 'Optional MCC ID' },
  ],
  klaviyo: [
    { name: 'private_key', label: 'Private API key', type: 'password' },
    { name: 'metric_id', label: 'Revenue metric ID', placeholder: 'Metric ID to aggregate daily' },
  ],
}

export type SavedDataset = {
  id: string
  name: string
  connector_type: string
  row_count?: number | null
  created_at?: string | null
  report_count?: number
  last_incident_at?: string | null
}

type DatasetPreview = {
  columns: string[]
  row_count: number
  suggested_mapping: Record<string, string>
  validation_errors: string[]
  preview_rows: Array<Record<string, unknown>>
}

type DatasetTemplate = {
  id: string
  label: string
  description: string
  connectors: string[]
  metrics: string[]
  recommended_for: string
}

type IntegrationCatalogItem = {
  id: string
  label: string
  status: string
  summary: string
}

type Props = {
  token: string
  initialDatasets: SavedDataset[]
}

export function DatasetWorkbench({ token, initialDatasets }: Props) {
  const [datasets, setDatasets] = useState<SavedDataset[]>(initialDatasets)
  const [file, setFile] = useState<File | null>(null)
  const [datasetName, setDatasetName] = useState('')
  const [preview, setPreview] = useState<DatasetPreview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<'idle' | 'previewing' | 'saving' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState(
    'Upload a client export, confirm the evidence mapping, and save it as a reusable workspace.'
  )
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [demoLoading, setDemoLoading] = useState(false)
  const [templates, setTemplates] = useState<DatasetTemplate[]>([])
  const [integrations, setIntegrations] = useState<IntegrationCatalogItem[]>([])
  const [integrationProvider, setIntegrationProvider] = useState('shopify')
  const [integrationWorkspaceName, setIntegrationWorkspaceName] = useState('')
  const [integrationLookbackDays, setIntegrationLookbackDays] = useState(90)
  const [integrationConfig, setIntegrationConfig] = useState<Record<string, string>>({})
  const [integrationStatus, setIntegrationStatus] = useState<'idle' | 'testing' | 'saving' | 'success' | 'error'>('idle')
  const [integrationMessage, setIntegrationMessage] = useState(
    'Use provider tokens to create a repeatable native workspace. OAuth app install is still a future hardening step.'
  )

  const columnOptions = useMemo(() => [''].concat(preview?.columns ?? []), [preview?.columns])
  const integrationFields = INTEGRATION_FIELDS[integrationProvider] ?? []

  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/datasets/templates`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(payload.detail ?? `Template request failed with status ${response.status}`)
        }
        setTemplates((payload.templates ?? []) as DatasetTemplate[])
        setIntegrations((payload.integrations ?? []) as IntegrationCatalogItem[])
      } catch (error) {
        console.warn('Could not load dataset templates:', error)
      }
    }
    void loadTemplates()
  }, [token])

  const handleFileChange = (nextFile: File | null) => {
    setFile(nextFile)
    setPreview(null)
    setMapping({})
    if (!nextFile) {
      return
    }

    const inferredName = nextFile.name.replace(/\.[^.]+$/, '')
    if (!datasetName.trim()) {
      setDatasetName(inferredName)
    }
    setStatus('idle')
    setMessage(`Selected ${nextFile.name}. Generate a schema preview before saving the client workspace.`)
  }

  const previewDataset = async () => {
    if (!file) {
      setStatus('error')
      setMessage('Select a client export before generating a preview.')
      return
    }

    setStatus('previewing')
    setMessage('Inspecting columns and generating a suggested evidence schema...')

    try {
      const formData = new FormData()
      formData.append('file_payload', file)

      const response = await fetch(`${API_BASE_URL}/api/v1/datasets/preview`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      })

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Preview failed with status ${response.status}`)
      }

      const nextPreview = payload as DatasetPreview
      setPreview(nextPreview)
      setMapping(nextPreview.suggested_mapping ?? {})
      setStatus('idle')
      setMessage(`Preview ready. ${nextPreview.row_count.toLocaleString()} rows detected for this workspace.`)
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Workspace preview failed.')
    }
  }

  const saveDataset = async () => {
    if (!file) {
      setStatus('error')
      setMessage('Select a client export before saving.')
      return
    }
    if (!datasetName.trim()) {
      setStatus('error')
      setMessage('Give the client workspace a clear name before saving it.')
      return
    }

    setStatus('saving')
    setMessage('Persisting client workspace to secure storage...')

    try {
      const formData = new FormData()
      formData.append('dataset_name', datasetName.trim())
      formData.append('mapping_json', JSON.stringify(mapping))
      formData.append('file_payload', file)

      const response = await fetch(`${API_BASE_URL}/api/v1/datasets/`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      })

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Save failed with status ${response.status}`)
      }

      setDatasets((current) => [
        {
          id: payload.dataset_id as string,
          name: payload.name as string,
          connector_type: 'csv',
          row_count: payload.row_count as number,
          created_at: new Date().toISOString(),
          report_count: 0,
          last_incident_at: null,
        },
        ...current,
      ])
      setFile(null)
      setPreview(null)
      setMapping({})
      setDatasetName('')
      setStatus('success')
      setMessage(payload.message ?? 'Client workspace saved.')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Could not save client workspace.')
    }
  }

  const deleteSavedDataset = async (datasetId: string) => {
    setDeletingId(datasetId)
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/datasets/${encodeURIComponent(datasetId)}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Delete failed with status ${response.status}`)
      }

      setDatasets((current) => current.filter((dataset) => dataset.id !== datasetId))
      setStatus('success')
      setMessage('Client workspace deleted.')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Could not delete client workspace.')
    } finally {
      setDeletingId(null)
    }
  }

  const createDemoWorkspace = async () => {
    setDemoLoading(true)
    setStatus('idle')
    setMessage('Creating a demo workspace with realistic ecommerce agency data...')
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/datasets/demo`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Demo workspace failed with status ${response.status}`)
      }
      setDatasets((current) => [
        {
          id: payload.dataset_id as string,
          name: payload.name as string,
          connector_type: 'csv',
          row_count: payload.row_count as number,
          created_at: new Date().toISOString(),
          report_count: 0,
          last_incident_at: null,
        },
        ...current,
      ])
      setStatus('success')
      setMessage(payload.message ?? 'Demo workspace created.')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Could not create the demo workspace.')
    } finally {
      setDemoLoading(false)
    }
  }

  const updateIntegrationField = (field: string, value: string) => {
    setIntegrationConfig((current) => ({ ...current, [field]: value }))
  }

  const buildIntegrationPayload = () => {
    const credentials = { ...integrationConfig }
    const metricId = credentials.metric_id
    delete credentials.metric_id
    return {
      provider: integrationProvider,
      workspace_name: integrationWorkspaceName.trim() || `${integrationProvider.replace('_', ' ')} client workspace`,
      credentials,
      metric_id: metricId || undefined,
      lookback_days: integrationLookbackDays,
    }
  }

  const testIntegration = async () => {
    setIntegrationStatus('testing')
    setIntegrationMessage(`Testing ${integrationProvider.replace('_', ' ')} credentials...`)
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/datasets/integrations/test`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(buildIntegrationPayload()),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Integration test failed with status ${response.status}`)
      }
      setIntegrationStatus('success')
      setIntegrationMessage(payload.message ?? 'Integration credentials are valid.')
    } catch (error) {
      setIntegrationStatus('error')
      setIntegrationMessage(error instanceof Error ? error.message : 'Could not test the integration.')
    }
  }

  const saveIntegrationWorkspace = async () => {
    setIntegrationStatus('saving')
    setIntegrationMessage('Syncing provider data and saving a native client workspace...')
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/datasets/integrations/workspace`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(buildIntegrationPayload()),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Workspace creation failed with status ${response.status}`)
      }
      setDatasets((current) => [
        {
          id: payload.dataset_id as string,
          name: payload.name as string,
          connector_type: payload.connector_type as string,
          row_count: payload.row_count as number,
          created_at: new Date().toISOString(),
          report_count: 0,
          last_incident_at: null,
        },
        ...current,
      ])
      setIntegrationStatus('success')
      setIntegrationMessage(payload.message ?? 'Native integration workspace saved.')
      setIntegrationWorkspaceName('')
      setIntegrationConfig({})
    } catch (error) {
      setIntegrationStatus('error')
      setIntegrationMessage(error instanceof Error ? error.message : 'Could not save the native integration workspace.')
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card className="border-slate-800 bg-slate-900/70">
          <CardHeader>
            <CardTitle className="text-lg text-slate-200">30-minute onboarding lane</CardTitle>
            <CardDescription className="text-slate-400">
              Start with a demo workspace or align a live client export to one of the common agency templates below.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="text-sm font-medium text-white">Demo | Northstar Outfitters</div>
                  <div className="mt-1 text-sm leading-7 text-slate-400">
                    Seed a realistic ecommerce workspace so account managers can learn the workflow before connecting a live client.
                  </div>
                </div>
                <Button onClick={createDemoWorkspace} disabled={demoLoading} className="bg-blue-600 text-white hover:bg-blue-700">
                  {demoLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                  Create demo workspace
                </Button>
              </div>
            </div>

            <div className="grid gap-3">
              {templates.length === 0 ? (
                <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
                  Template catalog is loading. You can still upload a live client export below.
                </div>
              ) : (
                templates.map((template) => (
                  <div key={template.id} className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="text-sm font-medium text-white">{template.label}</div>
                        <div className="mt-1 text-sm leading-7 text-slate-400">{template.description}</div>
                      </div>
                      <div className="text-xs uppercase tracking-[0.2em] text-slate-500">{template.recommended_for}</div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
                      {template.connectors.map((connector) => (
                        <span key={`${template.id}-${connector}`} className="rounded-full border border-slate-700 px-2.5 py-1">
                          {connector}
                        </span>
                      ))}
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      Monitor first: {template.metrics.join(', ')}
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/70">
          <CardHeader>
            <CardTitle className="text-lg text-slate-200">Native integration catalog</CardTitle>
            <CardDescription className="text-slate-400">
              Token-based workspace setup for the agency stack. OAuth marketplace flows still need a later provider-certification pass.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {integrations.length === 0 ? (
              <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
                Integration catalog is loading.
              </div>
            ) : (
              integrations.map((integration) => (
                <div key={integration.id} className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
                  <div className="flex items-start gap-3">
                    <div className="rounded-xl border border-slate-700 bg-slate-900 p-2">
                      <PlugZap className="h-4 w-4 text-amber-300" />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white">{integration.label}</div>
                      <div className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">{integration.status}</div>
                      <div className="mt-2 text-sm leading-7 text-slate-400">{integration.summary}</div>
                    </div>
                  </div>
                </div>
              ))
            )}

            <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
              <div>
                <div className="text-sm font-medium text-white">Create native workspace</div>
                <div className="mt-1 text-xs leading-6 text-slate-500">
                  Credentials are sent to the backend and persisted through the encrypted dataset config path.
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium uppercase tracking-wide text-slate-400">Provider</label>
                <select
                  value={integrationProvider}
                  onChange={(event) => {
                    setIntegrationProvider(event.target.value)
                    setIntegrationConfig({})
                  }}
                  className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                >
                  {Object.keys(INTEGRATION_FIELDS).map((provider) => (
                    <option key={provider} value={provider}>
                      {provider.replace('_', ' ').toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium uppercase tracking-wide text-slate-400">Workspace name</label>
                <input
                  value={integrationWorkspaceName}
                  onChange={(event) => setIntegrationWorkspaceName(event.target.value)}
                  placeholder="e.g. Aurelia Skin | Shopify"
                  className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium uppercase tracking-wide text-slate-400">Lookback window</label>
                <input
                  type="number"
                  min={7}
                  max={365}
                  value={integrationLookbackDays}
                  onChange={(event) => setIntegrationLookbackDays(Number(event.target.value))}
                  className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                />
              </div>

              <div className="grid gap-3">
                {integrationFields.map((field) => (
                  <div key={`${integrationProvider}-${field.name}`} className="space-y-2">
                    <label className="text-xs font-medium uppercase tracking-wide text-slate-400">{field.label}</label>
                    <input
                      type={field.type ?? 'text'}
                      value={integrationConfig[field.name] ?? ''}
                      onChange={(event) => updateIntegrationField(field.name, event.target.value)}
                      placeholder={field.placeholder}
                      className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                    />
                  </div>
                ))}
              </div>

              <div className={`rounded-lg border p-3 text-sm ${
                integrationStatus === 'error'
                  ? 'border-red-500/30 bg-red-500/10 text-red-200'
                  : integrationStatus === 'success'
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
                    : 'border-slate-800 bg-slate-950 text-slate-300'
              }`}>
                {integrationMessage}
              </div>

              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={testIntegration}
                  disabled={integrationStatus === 'testing' || integrationStatus === 'saving'}
                  variant="outline"
                  className="border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800"
                >
                  {integrationStatus === 'testing' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Test connection
                </Button>
                <Button
                  onClick={saveIntegrationWorkspace}
                  disabled={integrationStatus === 'testing' || integrationStatus === 'saving'}
                  className="bg-blue-600 text-white hover:bg-blue-700"
                >
                  {integrationStatus === 'saving' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Save native workspace
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.95fr]">
        <Card className="border-slate-800 bg-slate-900">
          <CardHeader>
            <CardTitle className="text-lg text-slate-200">New Client Workspace</CardTitle>
            <CardDescription className="text-slate-400">
              Upload a client export once, confirm the evidence mapping, and reuse the workspace for future investigations.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-300">Client or workspace name</label>
              <input
                value={datasetName}
                onChange={(event) => setDatasetName(event.target.value)}
                placeholder="e.g. Aurelia Skin | Shopify daily export"
                className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
              />
            </div>

            <label className="flex h-40 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-800 bg-slate-950/60 transition-colors hover:bg-slate-900">
              <div className="flex flex-col items-center justify-center p-6 text-center">
                <Upload className="mb-2 h-6 w-6 text-slate-400" />
                <span className="text-sm font-medium text-slate-200">Select CSV or Excel client export</span>
                <span className="mt-1 text-xs text-slate-500">
                  {file ? file.name : 'Supported: .csv, .xls, .xlsx'}
                </span>
                <input
                  type="file"
                  accept=".csv,.xls,.xlsx"
                  className="hidden"
                  onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
                />
              </div>
            </label>

            <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
              <div className="flex items-center gap-3">
                {status === 'previewing' || status === 'saving' ? <Loader2 className="h-4 w-4 animate-spin text-blue-500" /> : null}
                {status === 'success' ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : null}
                {status === 'error' ? <AlertCircle className="h-4 w-4 text-red-500" /> : null}
                {status === 'idle' ? <div className="h-2 w-2 rounded-full bg-slate-500" /> : null}
                <p className={`text-sm ${status === 'error' ? 'text-red-300' : 'text-slate-300'}`}>{message}</p>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button
                onClick={previewDataset}
                disabled={!file || status === 'previewing' || status === 'saving'}
                className="bg-blue-600 text-white hover:bg-blue-700"
              >
                {status === 'previewing' ? 'Profiling...' : 'Generate Preview'}
              </Button>
              <Button
                onClick={saveDataset}
                disabled={!file || !preview || status === 'previewing' || status === 'saving'}
                variant="outline"
                className="border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800"
              >
                {status === 'saving' ? 'Saving...' : 'Save Workspace'}
              </Button>
            </div>

            {preview ? (
              <div className="space-y-5 rounded-lg border border-slate-800 bg-slate-950/70 p-4">
                <div>
                  <h3 className="text-sm font-medium text-slate-200">Evidence schema mapping</h3>
                  <p className="text-xs text-slate-500">
                    {preview.row_count.toLocaleString()} rows detected. Required fields must be mapped before the workspace can be reused safely.
                  </p>
                </div>

                {preview.validation_errors.length > 0 ? (
                  <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
                    {preview.validation_errors.join(' ')}
                  </div>
                ) : null}

                <div className="grid gap-3 md:grid-cols-2">
                  {CANONICAL_FIELDS.map((field) => (
                    <div key={field} className="space-y-1.5">
                      <label className="text-xs font-medium uppercase tracking-wide text-slate-400">
                        {REQUIRED_FIELDS.has(field) ? `${field} (required)` : field}
                      </label>
                      <select
                        value={mapping[field] ?? ''}
                        onChange={(event) =>
                          setMapping((current) => ({ ...current, [field]: event.target.value }))
                        }
                        className="flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                      >
                        {columnOptions.map((column) => (
                          <option key={`${field}-${column || 'blank'}`} value={column}>
                            {column || 'Not mapped'}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>

                <div className="overflow-hidden rounded-lg border border-slate-800">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-800 text-left text-xs">
                      <thead className="bg-slate-950/80 text-slate-400">
                        <tr>
                          {preview.columns.map((column) => (
                            <th key={column} className="px-3 py-2 font-medium">
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800 bg-slate-900/40 text-slate-300">
                        {preview.preview_rows.map((row, index) => (
                          <tr key={`preview-row-${index}`}>
                            {preview.columns.map((column) => (
                              <td key={`${index}-${column}`} className="max-w-[16rem] truncate px-3 py-2">
                                {String(row[column] ?? '')}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/70">
          <CardHeader>
            <CardTitle className="text-lg text-slate-200">Workspace Catalog</CardTitle>
            <CardDescription className="text-slate-400">
              Reusable client workspaces available to the investigation pipeline.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {datasets.length === 0 ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-6 text-center">
                <Database className="mx-auto mb-3 h-8 w-8 text-slate-600" />
                <p className="text-sm text-slate-300">No client workspaces yet.</p>
                <p className="mt-1 text-xs text-slate-500">
                  Save the first client export here and it will immediately appear in the analyst workbench.
                </p>
              </div>
            ) : (
              datasets.map((dataset) => (
                <div
                  key={dataset.id}
                  className="rounded-lg border border-slate-800 bg-slate-950/60 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-200">{dataset.name}</p>
                      <p className="text-xs text-slate-500">
                        {dataset.connector_type.toUpperCase()} | {(dataset.row_count ?? 0).toLocaleString()} rows
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => deleteSavedDataset(dataset.id)}
                      disabled={deletingId === dataset.id}
                      className="text-slate-400 hover:bg-slate-800 hover:text-white"
                    >
                      {deletingId === dataset.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </Button>
                  </div>

                  <div className="mt-3 text-xs leading-6 text-slate-400">
                    {dataset.report_count && dataset.report_count > 0
                      ? `${dataset.report_count} incident briefs recorded. Latest anomaly on ${dataset.last_incident_at}.`
                      : 'No incident history yet. Run the first investigation for this account.'}
                  </div>

                  <div className="mt-3 flex gap-2">
                    <Link
                      href={`/dashboard?datasetId=${encodeURIComponent(dataset.id)}`}
                      className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800"
                    >
                      Investigate
                    </Link>
                    <Link
                      href={`/dashboard/reports?datasetId=${encodeURIComponent(dataset.id)}`}
                      className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-900"
                    >
                      View briefs
                    </Link>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
