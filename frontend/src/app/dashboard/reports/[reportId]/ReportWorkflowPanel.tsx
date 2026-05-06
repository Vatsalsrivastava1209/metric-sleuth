'use client'

import { useMemo, useState } from 'react'
import { CheckCircle2, Copy, Loader2, MessageSquarePlus, Send, Share2, ShieldOff, ThumbsDown, ThumbsUp } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

type Workflow = {
  id: string
  workflow_status: string
  assigned_owner: string
  internal_notes: string
  share_token?: string | null
  share_created_at?: string | null
  share_expires_at?: string | null
  share_last_accessed_at?: string | null
  share_revoked_at?: string | null
  last_client_delivery_at?: string | null
  delivery_channel?: string | null
  feedback_rating?: number | null
  feedback_notes?: string | null
}

type Comment = {
  id: string
  author_email?: string | null
  body: string
  created_at?: string | null
}

const STATUS_LABELS: Record<string, string> = {
  new:           'New',
  investigating: 'Investigating',
  ready_to_send: 'Ready to send',
  sent:          'Sent',
}

export function ReportWorkflowPanel({
  reportId,
  token,
  agencyName,
  initialWorkflow,
  initialComments,
}: {
  reportId: string
  token: string
  agencyName: string
  initialWorkflow: Workflow
  initialComments: Comment[]
}) {
  const [workflowStatus, setWorkflowStatus] = useState(initialWorkflow.workflow_status || 'new')
  const [assignedOwner, setAssignedOwner] = useState(initialWorkflow.assigned_owner || '')
  const [internalNotes, setInternalNotes] = useState(initialWorkflow.internal_notes || '')
  const [comments, setComments] = useState<Comment[]>(initialComments)
  const [newComment, setNewComment] = useState('')
  const [sharePath, setSharePath] = useState(
    initialWorkflow.share_token ? `/brief/${initialWorkflow.share_token}` : ''
  )
  const [shareExpiresAt, setShareExpiresAt] = useState(initialWorkflow.share_expires_at || '')
  const [shareRevokedAt, setShareRevokedAt] = useState(initialWorkflow.share_revoked_at || '')
  const [deliveryAt, setDeliveryAt] = useState(initialWorkflow.last_client_delivery_at || '')
  const [feedbackRating, setFeedbackRating] = useState<number | null>(initialWorkflow.feedback_rating ?? null)
  const [saving, setSaving] = useState(false)
  const [commenting, setCommenting] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [delivering, setDelivering] = useState(false)
  const [feedbackLoading, setFeedbackLoading] = useState<number | null>(null)

  const shareUrl = useMemo(() => {
    if (!sharePath) return ''
    if (sharePath.startsWith('http')) return sharePath
    if (typeof window !== 'undefined') return `${window.location.origin}${sharePath}`
    return sharePath
  }, [sharePath])

  const authorizedFetch = (url: string, method: string, body?: unknown) =>
    fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    })

  const saveWorkflow = async () => {
    setSaving(true)
    try {
      const res = await authorizedFetch(
        `${API_BASE_URL}/api/v1/reports/${reportId}`,
        'PATCH',
        { workflow_status: workflowStatus, assigned_owner: assignedOwner, internal_notes: internalNotes }
      )
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.detail ?? `Save failed (${res.status})`)
      toast.success('Workflow saved')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save workflow')
    } finally {
      setSaving(false)
    }
  }

  const addComment = async () => {
    if (!newComment.trim()) return
    setCommenting(true)
    try {
      const res = await authorizedFetch(
        `${API_BASE_URL}/api/v1/reports/${reportId}/comments`,
        'POST',
        { body: newComment.trim() }
      )
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.detail ?? `Comment failed (${res.status})`)
      setComments((c) => [...c, payload as Comment])
      setNewComment('')
      toast.success('Note added')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save note')
    } finally {
      setCommenting(false)
    }
  }

  const createShareLink = async () => {
    setSharing(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/reports/${reportId}/share-link`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.detail ?? `Share link failed (${res.status})`)
      setSharePath(String(payload.public_path ?? ''))
      setShareExpiresAt(String(payload.expires_at ?? ''))
      setShareRevokedAt('')
      setWorkflowStatus('ready_to_send')
      toast.success('Client share link created')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not create share link')
    } finally {
      setSharing(false)
    }
  }

  const revokeShareLink = async () => {
    setSharing(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/reports/${reportId}/share-link`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.detail ?? `Share link revoke failed (${res.status})`)
      setShareRevokedAt(String(payload.share_revoked_at ?? new Date().toISOString()))
      toast.success('Client share link revoked')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not revoke share link')
    } finally {
      setSharing(false)
    }
  }

  const copyShareLink = async () => {
    if (!shareUrl || typeof navigator === 'undefined' || !navigator.clipboard) return
    await navigator.clipboard.writeText(shareUrl)
    toast.success('Link copied to clipboard')
  }

  const deliverToSlack = async () => {
    setDelivering(true)
    try {
      const res = await authorizedFetch(
        `${API_BASE_URL}/api/v1/reports/${reportId}/deliver/slack`,
        'POST',
        { brand_name: agencyName || undefined }
      )
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.detail ?? `Slack delivery failed (${res.status})`)
      setWorkflowStatus('sent')
      setDeliveryAt(new Date().toISOString())
      toast.success(payload.message ?? 'Client brief sent to Slack')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not send to Slack')
    } finally {
      setDelivering(false)
    }
  }

  const sendFeedback = async (rating: number) => {
    setFeedbackLoading(rating)
    try {
      const res = await authorizedFetch(
        `${API_BASE_URL}/api/v1/reports/${reportId}/feedback`,
        'POST',
        { rating, notes: rating >= 4 ? 'Marked useful.' : 'Needs better evidence.' }
      )
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload.detail ?? `Feedback failed (${res.status})`)
      setFeedbackRating(payload.feedback_rating ?? rating)
      toast.success(rating >= 4 ? 'Marked as useful' : 'Feedback recorded')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not record feedback')
    } finally {
      setFeedbackLoading(null)
    }
  }

  const inputCls = 'flex h-10 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/30'
  const textareaCls = 'w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/30'

  return (
    <div className="space-y-4">
      {/* ── Workflow card ─────────────────────────────────────────────────── */}
      <Card className="border-slate-800 bg-slate-900/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base text-slate-200">Agency workflow</CardTitle>
          <CardDescription className="text-slate-500 text-xs">
            Assign ownership, approve the brief, and track delivery.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Status</label>
              <select
                value={workflowStatus}
                onChange={(e) => setWorkflowStatus(e.target.value)}
                className={inputCls}
              >
                {Object.entries(STATUS_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Owner</label>
              <input
                value={assignedOwner}
                onChange={(e) => setAssignedOwner(e.target.value)}
                placeholder="alex@agency.com"
                className={inputCls}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Internal notes</label>
            <textarea
              value={internalNotes}
              onChange={(e) => setInternalNotes(e.target.value)}
              rows={4}
              placeholder="Context for the next analyst before this brief goes out..."
              className={textareaCls}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={saveWorkflow} disabled={saving} size="sm" className="bg-blue-600 hover:bg-blue-700 text-white">
              {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
              {saving ? 'Saving…' : 'Save workflow'}
            </Button>
            <Button onClick={createShareLink} disabled={sharing} size="sm" variant="outline" className="border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800">
              {sharing ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Share2 className="mr-1.5 h-3.5 w-3.5" />}
              {sharing ? 'Creating…' : 'Create link'}
            </Button>
            {shareUrl && (
              <Button onClick={revokeShareLink} disabled={sharing} size="sm" variant="outline" className="border-red-500/30 bg-red-500/10 text-red-100 hover:bg-red-500/20">
                {sharing ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <ShieldOff className="mr-1.5 h-3.5 w-3.5" />}
                Revoke link
              </Button>
            )}
            <Button onClick={deliverToSlack} disabled={delivering} size="sm" variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-100 hover:bg-amber-500/20">
              {delivering ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Send className="mr-1.5 h-3.5 w-3.5" />}
              {delivering ? 'Sending…' : 'Send to Slack'}
            </Button>
          </div>

          {shareUrl && (
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1.5">Client brief link</div>
              <div className="flex items-center gap-2">
                <span className="flex-1 text-xs text-slate-300 break-all">{shareUrl}</span>
                <Button onClick={copyShareLink} size="sm" variant="outline" className="shrink-0 border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800">
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </div>
              <div className="mt-2 space-y-1 text-[11px] text-slate-500">
                {shareExpiresAt && <div>Expires {new Date(shareExpiresAt).toLocaleString()}</div>}
                {shareRevokedAt && <div className="text-red-300">Revoked {new Date(shareRevokedAt).toLocaleString()}</div>}
              </div>
            </div>
          )}

          {deliveryAt && (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              Delivered {new Date(deliveryAt).toLocaleString()}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Handoff notes ─────────────────────────────────────────────────── */}
      <Card className="border-slate-800 bg-slate-900/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base text-slate-200">Handoff notes</CardTitle>
          <CardDescription className="text-slate-500 text-xs">
            Analyst context that stays out of the client brief.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            rows={2}
            placeholder="Add a note for the next teammate..."
            className={textareaCls}
          />
          <Button
            onClick={addComment}
            disabled={commenting || !newComment.trim()}
            size="sm"
            variant="outline"
            className="border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800"
          >
            {commenting ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <MessageSquarePlus className="mr-1.5 h-3.5 w-3.5" />}
            Add note
          </Button>

          <div className="space-y-2 pt-1">
            {comments.length === 0 ? (
              <p className="text-xs text-slate-600 py-2">No notes yet.</p>
            ) : (
              comments.map((c) => (
                <div key={c.id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                  <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1">
                    <span>{c.author_email ?? 'Unknown'}</span>
                    <span>{c.created_at ? new Date(c.created_at).toLocaleString() : ''}</span>
                  </div>
                  <p className="text-sm text-slate-200 leading-6">{c.body}</p>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── Feedback ──────────────────────────────────────────────────────── */}
      <Card className="border-slate-800 bg-slate-900/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base text-slate-200">Driver feedback</CardTitle>
          <CardDescription className="text-slate-500 text-xs">
            Teach the model which explanations were evidence-backed enough to send.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Button
            onClick={() => sendFeedback(5)}
            disabled={feedbackLoading !== null}
            size="sm"
            variant="outline"
            className={feedbackRating && feedbackRating >= 4
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
              : 'border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800'}
          >
            {feedbackLoading === 5 ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <ThumbsUp className="mr-1.5 h-3.5 w-3.5" />}
            Useful
          </Button>
          <Button
            onClick={() => sendFeedback(2)}
            disabled={feedbackLoading !== null}
            size="sm"
            variant="outline"
            className={feedbackRating !== null && feedbackRating < 4
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-100'
              : 'border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800'}
          >
            {feedbackLoading === 2 ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <ThumbsDown className="mr-1.5 h-3.5 w-3.5" />}
            Needs work
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
