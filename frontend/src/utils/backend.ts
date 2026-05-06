const DEFAULT_API_BASE_URL = 'http://localhost:8000'

export function getBackendApiBaseUrl() {
  return (
    process.env.METRICSLEUTH_API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    DEFAULT_API_BASE_URL
  ).replace(/\/$/, '')
}

export function buildBackendApiUrl(path: string) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${getBackendApiBaseUrl()}${normalizedPath}`
}
