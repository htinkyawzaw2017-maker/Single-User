// API client — thin fetch wrapper with single-user access key support.
// All URLs are relative so the app works behind the Vite dev proxy,
// ECS/ALB, or CloudFront without changes.

import type {
  AppConfig,
  ExportItem,
  Job,
  Language,
  Mode,
  Project,
  ProjectSummary,
  Segment,
  UploadTicket,
} from '../types'

const KEY_STORAGE = 'dubbing_access_key'
let accessKey: string | null = localStorage.getItem(KEY_STORAGE)

export function setAccessKey(key: string | null) {
  accessKey = key
  if (key) localStorage.setItem(KEY_STORAGE, key)
  else localStorage.removeItem(KEY_STORAGE)
}

export function getAccessKey() {
  return accessKey
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (accessKey) headers.set('X-Access-Key', accessKey)
  if (init.body && !headers.has('Content-Type') && typeof init.body === 'string') {
    headers.set('Content-Type', 'application/json')
  }
  const resp = await fetch(path, { ...init, headers })
  if (resp.status === 401) {
    const msg = 'Access key required — set it in the app (top bar).'
    throw new ApiError(401, msg)
  }
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const data = await resp.json()
      detail = data.detail || JSON.stringify(data)
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, detail)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

export function withKey(url: string): string {
  if (!accessKey) return url
  return url + (url.includes('?') ? '&' : '?') + 'key=' + encodeURIComponent(accessKey)
}

// ---------------------------------------------------------------- config
export const getConfig = () => request<AppConfig>('/api/config')

// ---------------------------------------------------------------- projects
export const listProjects = () => request<ProjectSummary[]>('/api/projects')

export const createProject = (body: {
  name: string
  source_language: Language
  target_language: Language
  mode: Mode
  voice_style: string
  instructions: string
}) =>
  request<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const getProject = (id: string) => request<Project>(`/api/projects/${id}`)

export const updateProject = (id: string, body: Record<string, unknown>) =>
  request<Project>(`/api/projects/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const deleteProject = (id: string) =>
  request<void>(`/api/projects/${id}`, { method: 'DELETE' })

export const requestUploadUrl = (
  projectId: string,
  filename: string,
  contentType: string,
  size: number,
) =>
  request<UploadTicket>(`/api/projects/${projectId}/upload-url`, {
    method: 'POST',
    body: JSON.stringify({ filename, content_type: contentType, size }),
  })

export const completeUpload = (projectId: string, key: string, filename: string) =>
  request<Project>(`/api/projects/${projectId}/upload-complete`, {
    method: 'POST',
    body: JSON.stringify({ key, filename }),
  })

export const useDemoClip = (projectId: string) =>
  request<Project>(`/api/projects/${projectId}/use-demo`, { method: 'POST' })

// ------------------------------------------------------------- pipeline
export const projectAction = (projectId: string, action: string) =>
  request<Project>(`/api/projects/${projectId}/actions/${action}`, {
    method: 'POST',
  })

// ---------------------------------------------------------------- segments
export const updateSegment = (segmentId: string, body: Record<string, unknown>) =>
  request<Segment>(`/api/segments/${segmentId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const regenerateSegmentVoice = (segmentId: string) =>
  request<{ job_id: string; segment_id: string }>(
    `/api/segments/${segmentId}/voice`,
    { method: 'POST' },
  )

export const approveSegment = (segmentId: string, approved: boolean) =>
  request<Segment>(`/api/segments/${segmentId}/approve?approved=${approved}`, {
    method: 'POST',
  })

// ------------------------------------------------------------------- jobs
export const getJob = (jobId: string) => request<Job>(`/api/jobs/${jobId}`)
export const retryJob = (jobId: string) =>
  request<Job>(`/api/jobs/${jobId}/retry`, { method: 'POST' })

// ----------------------------------------------------------------- exports
export const listExports = (projectId: string) =>
  request<ExportItem[]>(`/api/projects/${projectId}/exports`)

export const createExport = (projectId: string, kind: string) =>
  request<ExportItem>(`/api/projects/${projectId}/exports/${kind}`, {
    method: 'POST',
  })

// ------------------------------------------------------------------ upload
export interface UploadProgress {
  loaded: number
  total: number
}

/** Upload a file via the presigned URL with progress events (XHR). */
export function uploadFile(
  ticket: UploadTicket,
  file: File,
  onProgress?: (p: UploadProgress) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open(ticket.method, ticket.url, true)
    Object.entries(ticket.headers || {}).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    if (ticket.mode === 's3' && accessKey) {
      // S3 presigned URLs must not receive the app access key
    }
    xhr.upload.onprogress = (e) => {
      if (onProgress) onProgress({ loaded: e.loaded, total: e.total })
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new ApiError(xhr.status, `upload failed: ${xhr.status} ${xhr.responseText?.slice(0, 200)}`))
    }
    xhr.onerror = () => reject(new ApiError(0, 'network error during upload'))
    xhr.send(file)
  })
}
