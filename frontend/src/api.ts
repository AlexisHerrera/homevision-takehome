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

export async function detect(file: Blob, signal?: AbortSignal): Promise<DetectResponse> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch('/api/detect', { method: 'POST', body, signal })
  if (response.ok) return response.json()
  if (response.status === 429 || response.status === 503) throw new Error('Too many requests, try again in a moment.')
  const detail = await response
    .json()
    .then((b) => b.detail)
    .catch(() => undefined)
  throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`)
}
