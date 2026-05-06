'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { AlertCircle, CheckCircle2, Database, Loader2, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { SavedDataset } from './DatasetWorkbench'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024
const MAX_FILE_SIZE_LABEL = '200 MB'
const MAX_POLL_ATTEMPTS = 150

export function AnalyzeForm({
  token,
  savedDatasets,
  initialDatasetId = '',
}: {
  token: string
  savedDatasets: SavedDataset[]
  initialDatasetId?: string
}) {
  const [file, setFile] = useState<File | null>(null)
  const [analysisMode, setAnalysisMode] = useState<'upload' | 'saved'>(
    initialDatasetId || savedDatasets.length > 0 ? 'saved' : 'upload'
  )
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>(
    initialDatasetId || savedDatasets[0]?.id || ''
  )
  const [metric, setMetric] = useState('revenue')
  const [status, setStatus] = useState<'IDLE' | 'UPLOADING' | 'POLLING' | 'SUCCESS' | 'FAILURE'>('IDLE')
  const [message, setMessage] = useState('')
  const [completedReportId, setCompletedReportId] = useState<string | null>(null)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollAttemptsRef = useRef(0)

  useEffect(() => () => { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current) }, [])

  useEffect(() => {
    if (savedDatasets.length === 0) {
      setAnalysisMode('upload')
      setSelectedDatasetId('')
      return
    }
    if (initialDatasetId && savedDatasets.some((d) => d.id === initialDatasetId)) {
      setAnalysisMode('saved')
      setSelectedDatasetId(initialDatasetId)
      return
    }
    setSelectedDatasetId((cur) =>
      cur && savedDatasets.some((d) => d.id === cur) ? cur : (savedDatasets[0]?.id ?? '')
    )
  }, [initialDatasetId, savedDatasets])

  const stopPolling = () => {
    if (pollIntervalRef.current) { clearInterval(pollIntervalRef.current); pollIntervalRef.current = null }
    pollAttemptsRef.current = 0
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    if (f.size > MAX_FILE_SIZE_BYTES) {
      toast.error(`File too large: ${(f.size / 1024 / 1024).toFixed(1)} MB. Max is ${MAX_FILE_SIZE_LABEL}.`)
      e.target.value = ''
      return
    }
    setFile(f)
    setStatus('IDLE')
    setMessage('')
  }

  const startAnalysis = async () => {
    if (analysisMode === 'upload' && !file) return
    if (analysisMode === 'saved' && !selectedDatasetId) return

    stopPolling()
    setCompletedReportId(null)
    setStatus('UPLOADING')
    setMessage('Preparing secure upload…')

    try {
      const formData = new FormData()
      formData.append('metric', metric || 'revenue')

      if (analysisMode === 'upload' && file) {
        const signedForm = new FormData()
        signedForm.append('filename', file.name)

        const signedRes = await fetch(`${API_BASE_URL}/api/v1/analyze/signed-url`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: signedForm,
        })
        if (!signedRes.ok) {
          const e = await signedRes.json().catch(() => ({}))
          throw new Error(e.detail ?? `Upload prep failed (${signedRes.status})`)
        }
        const { upload_url, storage_key, job_id } = await signedRes.json() as {
          upload_url: string; storage_key: string; job_id: string
        }

        setMessage('Uploading to secure storage…')
        const uploadRes = await fetch(upload_url, {
          method: 'PUT',
          headers: { 'Content-Type': file.type || 'text/csv' },
          body: file,
        })
        if (!uploadRes.ok) throw new Error(`Storage upload failed (${uploadRes.status})`)

        formData.append('storage_key', storage_key)
        formData.append('job_id', job_id)
      } else {
        formData.append('dataset_id', selectedDatasetId)
      }

      const res = await fetch(`${API_BASE_URL}/api/v1/analyze/`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        throw new Error(e.detail ?? `API returned ${res.status}`)
      }
      const { job_id } = await res.json() as { job_id: string }

      setStatus('POLLING')
      setMessage('Investigation queued — waiting for findings…')
      beginPolling(job_id)
    } catch (err) {
      setStatus('FAILURE')
      const msg = err instanceof Error ? err.message : 'Submission failed'
      setMessage(msg)
      toast.error(msg)
    }
  }

  const beginPolling = (jobId: string) => {
    pollAttemptsRef.current = 0
    pollIntervalRef.current = setInterval(async () => {
      pollAttemptsRef.current += 1
      if (pollAttemptsRef.current > MAX_POLL_ATTEMPTS) {
        const msg = 'Investigation timed out after 5 minutes. Retry once the worker recovers.'
        setStatus('FAILURE')
        setMessage(msg)
        toast.error(msg)
        stopPolling()
        return
      }
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/analyze/jobs/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) throw new Error(`Polling returned ${res.status}`)
        const data = await res.json() as { state: string; meta?: { message?: string; report_id?: string; error?: string } }

        if (data.state === 'SUCCESS') {
          const rid = data.meta?.report_id ?? null
          setStatus('SUCCESS')
          setCompletedReportId(rid)
          setMessage('Investigation complete — brief saved to inbox.')
          stopPolling()
          toast.success('Investigation complete!', {
            description: 'Brief saved to the incident inbox.',
            action: { label: 'View inbox', onClick: () => { window.location.href = '/dashboard' } },
          })
        } else if (data.state === 'FAILURE') {
          const msg = `Worker error: ${data.meta?.error ?? 'unknown'}`
          setStatus('FAILURE')
          setMessage(msg)
          toast.error(msg)
          stopPolling()
        } else {
          setMessage(data.meta?.message ?? 'Processing in the investigation queue…')
        }
      } catch {
        // transient network error — keep polling
      }
    }, 2000)
  }

  const inputCls = 'flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/30'
  const isRunning = status === 'UPLOADING' || status === 'POLLING'
  const canRun = analysisMode === 'upload' ? !!file : !!selectedDatasetId

  return (
    <Card className="border-slate-800 bg-slate-900 shadow-none">
      <CardHeader>
        <CardTitle className="text-base text-slate-200">Analyst Workbench</CardTitle>
        <CardDescription className="text-slate-500 text-sm">
          Run a fresh investigation against a one-off CSV or a saved client workspace.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        {/* Source toggle */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Investigation source</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {[
              { mode: 'upload' as const, icon: Upload, label: 'One-off upload', desc: 'Fresh CSV from a client export.' },
              { mode: 'saved' as const, icon: Database, label: 'Client workspace', desc: 'Use a saved portfolio workspace.', disabled: savedDatasets.length === 0 },
            ].map(({ mode, icon: Icon, label, desc, disabled }) => (
              <button
                key={mode}
                type="button"
                onClick={() => !disabled && setAnalysisMode(mode)}
                disabled={disabled}
                className={[
                  'rounded-lg border p-3 text-left transition-colors',
                  analysisMode === mode ? 'border-amber-500/40 bg-amber-500/5 text-white' : 'border-slate-800 bg-slate-950/60 text-slate-300 hover:bg-slate-900',
                  disabled ? 'cursor-not-allowed opacity-40' : '',
                ].join(' ')}
              >
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Icon className="h-4 w-4" />
                  {label}
                </div>
                <p className="mt-1 text-xs text-slate-500">{desc}</p>
              </button>
            ))}
          </div>
        </div>

        {/* KPI field */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Primary KPI field</label>
          <input
            type="text"
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            className={inputCls}
            placeholder="e.g. revenue, conversion_rate, traffic"
          />
        </div>

        {/* Source input */}
        {analysisMode === 'upload' ? (
          <label className={[
            'flex h-40 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed transition-colors',
            file ? 'border-amber-500/40 bg-amber-500/5' : 'border-slate-800 bg-slate-950/50 hover:bg-slate-900',
          ].join(' ')}>
            <div className="flex flex-col items-center text-center p-4">
              {file ? (
                <>
                  <CheckCircle2 className="mb-2 h-5 w-5 text-amber-400" />
                  <span className="text-sm font-medium text-white">{file.name}</span>
                  <span className="mt-0.5 text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(1)} MB · click to change</span>
                </>
              ) : (
                <>
                  <Upload className="mb-2 h-5 w-5 text-slate-500" />
                  <span className="text-sm font-medium text-slate-300">Upload client CSV</span>
                  <span className="mt-0.5 text-xs text-slate-600">CSV or Parquet, up to {MAX_FILE_SIZE_LABEL}</span>
                </>
              )}
            </div>
            <input type="file" accept=".csv,.parquet" className="hidden" onChange={handleFileUpload} />
          </label>
        ) : (
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Saved workspace</label>
            <select
              value={selectedDatasetId}
              onChange={(e) => setSelectedDatasetId(e.target.value)}
              className={inputCls}
            >
              {savedDatasets.length === 0
                ? <option value="">No saved workspaces</option>
                : savedDatasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({(d.row_count ?? 0).toLocaleString()} rows)
                    </option>
                  ))}
            </select>
          </div>
        )}

        {/* Status + Run button */}
        <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2.5 min-w-0">
              {status === 'IDLE' && <span className="h-2 w-2 rounded-full bg-slate-700 shrink-0" />}
              {isRunning && <Loader2 className="h-4 w-4 animate-spin text-amber-400 shrink-0" />}
              {status === 'SUCCESS' && <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />}
              {status === 'FAILURE' && <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />}
              <span className={[
                'text-xs truncate',
                status === 'FAILURE' ? 'text-red-400' : status === 'SUCCESS' ? 'text-emerald-400' : 'text-slate-400',
              ].join(' ')}>
                {message || 'Ready to investigate.'}
              </span>
            </div>
            <Button
              onClick={startAnalysis}
              disabled={isRunning || !canRun}
              size="sm"
              className="shrink-0 bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold"
            >
              {isRunning ? 'Running…' : 'Run'}
            </Button>
          </div>

          {status === 'SUCCESS' && (
            <div className="mt-3 pt-3 border-t border-slate-800 flex items-center gap-3">
              <Link
                href={completedReportId ? `/dashboard/reports/${completedReportId}` : '/dashboard'}
                className="text-xs font-medium text-amber-400 hover:text-amber-300 transition-colors"
              >
                {completedReportId ? 'View report →' : 'Go to inbox →'}
              </Link>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
