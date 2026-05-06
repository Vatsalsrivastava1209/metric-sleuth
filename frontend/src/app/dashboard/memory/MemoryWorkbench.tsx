'use client'

import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

type IndexedReport = {
  id: string
  anomaly_date?: string | null
  primary_metric?: string | null
  generated_at?: string | null
  n_hypotheses?: number | null
}

type Props = {
  token: string
  initialReports: IndexedReport[]
  initialDocumentCount: number
}

export function MemoryWorkbench({ token, initialReports, initialDocumentCount }: Props) {
  const [reports, setReports] = useState(initialReports)
  const [documentCount, setDocumentCount] = useState(initialDocumentCount)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState<IndexedReport[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'error' | 'success'>('idle')
  const [message, setMessage] = useState('Ask about similar past incidents or clear the indexed pattern library for this tenant.')

  const hasMemory = useMemo(() => documentCount > 0, [documentCount])

  const askMemory = async () => {
    if (!question.trim()) {
      setStatus('error')
      setMessage('Enter a question before searching the pattern library.')
      return
    }

    setStatus('loading')
    setMessage('Searching historical incidents...')
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/memory/query`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: question.trim() }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Pattern query failed with status ${response.status}`)
      }
      setAnswer(payload.answer as string)
      setSources((payload.sources as IndexedReport[]) ?? [])
      setStatus('success')
      setMessage('Pattern library returned a grounded answer.')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Pattern query failed.')
    }
  }

  const clearMemory = async () => {
    setStatus('loading')
    setMessage('Clearing indexed pattern library...')
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/memory`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail ?? `Clear failed with status ${response.status}`)
      }
      setReports([])
      setDocumentCount(0)
      setAnswer('')
      setSources([])
      setStatus('success')
      setMessage(payload.message ?? 'Indexed pattern library cleared.')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Could not clear the pattern library.')
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
      <div className="space-y-6">
        <Card className="border-slate-800 bg-slate-900/60">
          <CardHeader>
            <CardTitle className="text-lg text-slate-200">Historical pattern search</CardTitle>
            <CardDescription className="text-slate-400">
              Search prior investigations before your team drafts a new explanation for the client.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={4}
              placeholder="Have we seen a similar revenue drop tied to mobile traffic in another client account?"
              className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
            <div className="flex flex-wrap gap-3">
              <Button onClick={askMemory} disabled={!hasMemory || status === 'loading'} className="bg-blue-600 text-white hover:bg-blue-700">
                {status === 'loading' ? 'Searching...' : 'Search patterns'}
              </Button>
              <Button onClick={clearMemory} disabled={!hasMemory || status === 'loading'} variant="outline" className="border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800">
                Clear library
              </Button>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-sm text-slate-300">
              {message}
            </div>
            {answer ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-4">
                <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">Answer</div>
                <div className="whitespace-pre-wrap text-sm leading-7 text-slate-200">{answer}</div>
              </div>
            ) : null}
            {sources.length > 0 ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-4">
                <div className="mb-3 text-xs uppercase tracking-wide text-slate-500">Supporting briefs</div>
                <div className="space-y-3">
                  {sources.map((source, index) => (
                    <div key={`${source.id}-${index}`} className="rounded-md border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-300">
                      <div>{source.anomaly_date || 'Unknown date'} | {source.primary_metric || 'Unknown metric'}</div>
                      <div className="mt-1 text-xs text-slate-500">{source.n_hypotheses ?? 0} ranked drivers indexed</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card className="border-slate-800 bg-slate-900/60">
        <CardHeader>
          <CardTitle className="text-lg text-slate-200">Indexed briefs</CardTitle>
          <CardDescription className="text-slate-400">
            {documentCount.toLocaleString()} document(s) currently available to the library.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {reports.length === 0 ? (
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-400">
              No incident briefs indexed yet. Generate and persist reports first.
            </div>
          ) : (
            reports.map((report) => (
              <div key={report.id} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                <div className="text-sm font-medium text-slate-200">{report.primary_metric || 'Unknown metric'}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {report.anomaly_date || 'Unknown date'} | {report.n_hypotheses ?? 0} ranked drivers
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}
