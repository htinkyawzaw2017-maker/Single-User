import { STATUS_LABEL, STATUS_TONE } from '../hooks'

/** Status chip for a project status. */
export function ProjectStatusBadge({ status }: { status: string }) {
  const running = status === 'LIP_SYNCING' && false
  const tone = STATUS_TONE[status] || 'neutral'
  const label = STATUS_LABEL[status] || status
  const pulsing =
    status === 'EXTRACTING_AUDIO' ||
    status === 'TRANSCRIBING' ||
    status === 'TRANSLATING' ||
    status === 'GENERATING_VOICE' ||
    status === 'ALIGNING_TIMING' ||
    status === 'LIP_SYNCING' ||
    status === 'RENDERING'
  return (
    <span className={`badge ${tone}`}>
      <span className={`dot${pulsing ? ' pulse' : ''}`} />
      {label}
      {running ? '…' : ''}
    </span>
  )
}

/** Status chip for a job. */
export function JobBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: 'neutral',
    running: 'info',
    completed: 'ok',
    failed: 'error',
    cancelled: 'neutral',
    skipped: 'neutral',
  }
  return (
    <span className={`badge ${map[status] || 'neutral'}`}>
      {status === 'running' && <span className="dot pulse" />}
      {status}
    </span>
  )
}

export function SegmentBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    draft: 'neutral',
    translated: 'info',
    pending: 'info',
    generating: 'info',
    generated: 'info',
    aligned: 'ok',
    too_long: 'warn',
    failed: 'error',
    approved: 'ok',
  }
  const labels: Record<string, string> = {
    too_long: 'too long',
  }
  return (
    <span className={`badge ${map[status] || 'neutral'}`}>
      {status === 'generating' && <span className="dot pulse" />}
      {labels[status] || status}
    </span>
  )
}
