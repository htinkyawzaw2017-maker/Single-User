// Shared React helpers: polling, async actions, formatting.

import { useCallback, useEffect, useRef, useState } from 'react'
import type { ProjectStatus } from './types'

/** Repeatedly run an async function while `enabled`.
 *  Changing `refreshKey` forces an immediate refetch. */
export function usePoll<T>(
  fn: () => Promise<T>,
  intervalMs: number,
  enabled: boolean,
  refreshKey: unknown = null,
): T | null {
  const [data, setData] = useState<T | null>(null)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) return
    let alive = true
    let timer: number | undefined

    const tick = async () => {
      try {
        const result = await fnRef.current()
        if (alive) setData(result)
      } catch {
        /* keep last good data; errors surface via manual calls */
      } finally {
        if (alive) timer = window.setTimeout(tick, intervalMs)
      }
    }
    tick()
    return () => {
      alive = false
      if (timer) window.clearTimeout(timer)
    }
  }, [intervalMs, enabled, refreshKey])

  return data
}

/** Async action wrapper with loading + error state. */
export function useAction<Args extends unknown[], R>(
  fn: (...args: Args) => Promise<R>,
) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const run = useCallback(async (...args: Args): Promise<R | null> => {
    setLoading(true)
    setError(null)
    try {
      return await fnRef.current(...args)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  return { run, loading, error, setError }
}

// ------------------------------------------------------------ formatting
export function fmtTime(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return '–'
  const m = Math.floor(seconds / 60)
  const s = seconds - m * 60
  return `${m}:${s.toFixed(1).padStart(4, '0')}`
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return '–'
  return `${seconds.toFixed(2)}s`
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '–'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

export const LANG_LABEL: Record<string, string> = { en: 'English', my: 'မြန်မာ' }
export const LANG_FLAG: Record<string, string> = { en: '🇬🇧', my: '🇲🇲' }

export const MODE_LABEL: Record<string, string> = {
  recap_narration: 'Recap narration',
  dialogue_dubbing: 'Dialogue dubbing',
  dialogue_lipsync: 'Dubbing + lip-sync',
}

export const STATUS_LABEL: Record<string, string> = {
  CREATED: 'Created',
  UPLOADED: 'Uploaded',
  EXTRACTING_AUDIO: 'Extracting audio',
  TRANSCRIBING: 'Transcribing',
  TRANSLATING: 'Translating',
  AWAITING_USER_REVIEW: 'Awaiting review',
  GENERATING_VOICE: 'Generating voice',
  ALIGNING_TIMING: 'Aligning timing',
  AWAITING_VOICE_APPROVAL: 'Awaiting voice approval',
  LIP_SYNCING: 'Lip-sync',
  RENDERING: 'Rendering',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
}

export const STATUS_TONE: Record<string, string> = {
  CREATED: 'neutral',
  UPLOADED: 'info',
  EXTRACTING_AUDIO: 'info',
  TRANSCRIBING: 'info',
  TRANSLATING: 'info',
  AWAITING_USER_REVIEW: 'warn',
  GENERATING_VOICE: 'info',
  ALIGNING_TIMING: 'info',
  AWAITING_VOICE_APPROVAL: 'warn',
  LIP_SYNCING: 'info',
  RENDERING: 'info',
  COMPLETED: 'ok',
  FAILED: 'error',
  CANCELLED: 'neutral',
}

export const RUNNING_STATUSES: ProjectStatus[] = [
  'UPLOADED', 'EXTRACTING_AUDIO', 'TRANSCRIBING', 'TRANSLATING',
  'GENERATING_VOICE', 'ALIGNING_TIMING', 'LIP_SYNCING', 'RENDERING',
]

/** Which project sub-page to open for a status (mirrors backend logic). */
export function pageForStatus(status: string, mode: string): string {
  if (status === 'CREATED') return 'setup'
  if (status === 'AWAITING_USER_REVIEW') return 'editor'
  if (status === 'GENERATING_VOICE' || status === 'ALIGNING_TIMING') return 'processing'
  if (status === 'AWAITING_VOICE_APPROVAL') return 'voice'
  if (status === 'LIP_SYNCING') return mode === 'dialogue_lipsync' ? 'lipsync' : 'processing'
  if (status === 'COMPLETED') return 'export'
  return 'processing'
}
