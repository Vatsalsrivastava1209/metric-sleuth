import { NextResponse } from 'next/server'
import { createClient } from '@/utils/supabase/server'
import { buildBackendApiUrl } from '@/utils/backend'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const reportId = url.searchParams.get('reportId')
  const audience = url.searchParams.get('audience') ?? 'internal'
  const brandName = url.searchParams.get('brandName')

  if (!reportId) {
    return NextResponse.json({ detail: 'Missing reportId query parameter.' }, { status: 400 })
  }

  const supabase = await createClient()
  const { data: { user }, error: userError } = await supabase.auth.getUser()

  if (userError || !user) {
    return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 })
  }

  const { data: { session } } = await supabase.auth.getSession()
  const accessToken = session?.access_token

  if (!accessToken) {
    return NextResponse.json({ detail: 'Missing access token.' }, { status: 401 })
  }

  const upstreamParams = new URLSearchParams({ audience })
  if (brandName) {
    upstreamParams.set('brand_name', brandName)
  }

  const upstream = await fetch(
    buildBackendApiUrl(`/api/v1/export/markdown/${encodeURIComponent(reportId)}?${upstreamParams.toString()}`),
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      cache: 'no-store',
    },
  )

  const body = await upstream.arrayBuffer()
  const response = new Response(body, { status: upstream.status })
  const contentType = upstream.headers.get('content-type')
  const contentDisposition = upstream.headers.get('content-disposition')
  const contentLength = upstream.headers.get('content-length')

  if (contentType) {
    response.headers.set('Content-Type', contentType)
  }
  if (contentDisposition) {
    response.headers.set('Content-Disposition', contentDisposition)
  }
  if (contentLength) {
    response.headers.set('Content-Length', contentLength)
  }
  response.headers.set('Cache-Control', 'no-store')

  return response
}
