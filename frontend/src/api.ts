export interface Box {
  bbox: [number, number, number, number]
  is_checked: boolean
}

export interface DetectResponse {
  boxes: Box[]
}

export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024

export async function health(): Promise<{ status: string; model_version: string }> {
  const response = await fetch('/api/health')
  if (!response.ok) throw new Error(`Health check failed (${response.status})`)
  return response.json()
}

export interface Detection {
  result: DetectResponse
  serverMs?: number
}

function serverMs(header: string | null): number | undefined {
  const durations = [...(header ?? '').matchAll(/dur=([\d.]+)/g)].map((m) => Number(m[1]))
  return durations.length ? durations.reduce((a, b) => a + b) : undefined
}

export async function detect(file: Blob, signal?: AbortSignal): Promise<Detection> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch('/api/detect', { method: 'POST', body, signal })
  if (response.ok) return { result: await response.json(), serverMs: serverMs(response.headers.get('Server-Timing')) }
  if (response.status === 429 || response.status === 503) throw new Error('Too many requests, try again in a moment.')
  const detail = await response
    .json()
    .then((b) => b.detail)
    .catch(() => undefined)
  throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`)
}
