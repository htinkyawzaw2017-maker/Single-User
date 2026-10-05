import { useState } from 'react'
import { retryJob } from '../api/client'
import type { Job, Project } from '../types'
import { JobBadge } from './StatusBadge'
import LogViewer from './LogViewer'

const STEP_META: { type: string; label: string; icon: string }[] = [
  { type: 'validate', label: 'Validate input', icon: '🔎' },
  { type: 'extract_audio', label: 'Extract audio', icon: '🎚' },
  { type: 'transcribe', label: 'Transcribe', icon: '📝' },
  { type: 'translate', label: 'Translate / rewrite', icon: '🌐' },
  { type: 'generate_voice', label: 'Generate voice', icon: '🗣' },
  { type: 'align_timing', label: 'Align timing', icon: '⏱' },
  { type: 'lip_sync', label: 'Lip-sync (beta)', icon: '👄' },
  { type: 'render', label: 'Render output', icon: '🎬' },
]

/**
 * The processing pipeline view:
 * Upload → Extract audio → Transcribe → Translate → Generate voice →
 * Align timing → Lip-sync (if enabled) → Render
 * Every step: pending / running / completed / failed + logs + retry.
 */
export default function Pipeline({
  project,
  onRefresh,
}: {
  project: Project
  onRefresh: () => void
}) {
  const [retrying, setRetrying] = useState<string | null>(null)
  const jobsByType = new Map(project.jobs.map((j) => [j.job_type, j]))

  const retry = async (job: Job) => {
    setRetrying(job.id)
    try {
      await retryJob(job.id)
      onRefresh()
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e))
    } finally {
      setRetrying(null)
    }
  }

  const lipsyncSkipped =
    project.mode !== 'dialogue_lipsync' &&
    jobsByType.get('lip_sync')?.status === 'cancelled'

  return (
    <div className="pipeline">
      <div className="pipe-step">
        <div className="step-icon">{project.source_video_s3_key ? '✓' : '1'}</div>
        <div className="step-name">
          Upload video
          <div className="step-sub">
            {project.source_video_filename
              ? `${project.source_video_filename} → cloud storage (S3)`
              : 'no video uploaded yet'}
          </div>
        </div>
        <span className={`badge ${project.source_video_s3_key ? 'ok' : 'warn'}`}>
          {project.source_video_s3_key ? 'completed' : 'pending'}
        </span>
      </div>

      {STEP_META.map((step) => {
        const job = jobsByType.get(step.type)
        const status = lipsyncSkipped && step.type === 'lip_sync'
          ? 'skipped'
          : job?.status || 'pending'
        const isFailed = status === 'failed'
        const isRunning = status === 'running'
        return (
          <div
            key={step.type}
            className={`pipe-step ${status}`}
          >
            <div className="step-icon">
              {status === 'completed' ? '✓' : isFailed ? '✕' : isRunning ? <span className="spinner" /> : '○'}
            </div>
            <div className="step-name">
              {step.label}
              {step.type === 'lip_sync' && project.mode !== 'dialogue_lipsync' && (
                <div className="step-sub">not enabled for this project mode</div>
              )}
              {isFailed && job?.error_message && (
                <div className="step-sub" style={{ color: 'var(--error)' }}>
                  {job.error_message.slice(0, 160)}
                </div>
              )}
              {isRunning && job && job.progress > 0 && (
                <div className="step-sub">{job.progress}%</div>
              )}
            </div>
            {isRunning && (
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${job?.progress || 4}%` }} />
              </div>
            )}
            <JobBadge status={status} />
            {job && (
              <LogViewer jobId={job.id} title={`Logs — ${step.label}`} />
            )}
            {isFailed && job && (
              <button
                className="btn small"
                onClick={() => retry(job)}
                disabled={retrying === job.id}
              >
                {retrying === job.id ? '…' : '↻ Retry'}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
