import { useState } from 'react'
import {
  approveSegment,
  projectAction,
  regenerateSegmentVoice,
  updateProject,
  updateSegment,
} from '../api/client'
import { fmtDuration, useAction } from '../hooks'
import { SegmentBadge } from '../components/StatusBadge'
import { useProject } from './ProjectShell'
import type { Segment } from '../types'

function diffTone(diff: number | null): string {
  if (diff == null) return 'neutral'
  if (diff <= 0.3) return 'ok'
  if (diff <= 1.0) return 'warn'
  return 'error'
}

/**
 * Voice review (spec 4.5): for every segment show original duration,
 * generated duration, difference, play buttons, regenerate, speed, accept.
 */
export default function VoiceReview() {
  const { project, refresh } = useProject()
  const [busySeg, setBusySeg] = useState<string | null>(null)

  const continue_ = useAction(async () => {
    await projectAction(project!.id, 'voice-complete')
    refresh()
  })

  const bgVolume = useAction(async (value: number) => {
    await updateProject(project!.id, { bg_volume: value })
    refresh()
  })

  const regen = async (s: Segment) => {
    setBusySeg(s.id)
    try {
      await regenerateSegmentVoice(s.id)
      refresh()
    } finally {
      setBusySeg(null)
    }
  }

  const setSpeed = async (s: Segment, value: number) => {
    await updateSegment(s.id, { speed_factor: value })
    refresh()
  }

  const accept = async (s: Segment, value: boolean) => {
    try {
      await approveSegment(s.id, value)
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e))
    }
    refresh()
  }

  if (!project) return null

  if (project.status === 'CREATED' || project.segments.length === 0) {
    return <div className="banner info">⏳ Generate voices first (Editor tab).</div>
  }

  const voiced = project.segments.filter((s) => s.aligned_duration != null)
  const approved = project.segments.filter((s) => s.approved)
  const canContinue = project.status === 'AWAITING_VOICE_APPROVAL' && voiced.length > 0
  const tooLongCount = project.segments.filter((s) => s.status === 'too_long').length

  return (
    <>
      <div className="row between" style={{ marginBottom: 14 }}>
        <div className="muted">
          {voiced.length}/{project.segments.length} voiced ·{' '}
          {approved.length} accepted
          {tooLongCount > 0 && (
            <span style={{ color: 'var(--warn)' }}>
              {' '}· {tooLongCount} too long
            </span>
          )}
        </div>
        <div className="row">
          <span className="muted">original background volume</span>
          <input
            type="range"
            min="0"
            max="0.6"
            step="0.05"
            defaultValue={project.bg_volume}
            style={{ width: 130 }}
            onMouseUp={(e) => bgVolume.run(parseFloat((e.target as HTMLInputElement).value))}
            onTouchEnd={(e) => bgVolume.run(parseFloat((e.target as HTMLInputElement).value))}
          />
          <span className="mono">{(project.bg_volume * 100).toFixed(0)}%</span>
          <button
            className="btn primary"
            disabled={!canContinue || continue_.loading}
            onClick={() => continue_.run()}
            title={
              canContinue
                ? 'continue to lip-sync / rendering'
                : 'available at AWAITING_VOICE_APPROVAL'
            }
          >
            {continue_.loading
              ? '⏳'
              : project.mode === 'dialogue_lipsync'
                ? 'Approve & lip-sync →'
                : 'Approve & render →'}
          </button>
        </div>
      </div>

      {/* source video for the "play original" buttons (kept compact) */}
      <div className="card" style={{ padding: 12, marginBottom: 14 }}>
        <video
          id="voice-review-video"
          controls
          muted
          src={`/api/projects/${project.id}/video`}
          style={{ maxHeight: 220 }}
        />
        <div className="faint" style={{ fontSize: 11, marginTop: 6 }}>
          source video (muted) — used by the 🎬 play-original buttons
        </div>
      </div>

      {tooLongCount > 0 && (
        <div className="banner warn">
          ⚠ {tooLongCount} segment(s) don’t fit their original timing even
          after speed-up. Shorten their text in the editor or raise the speed
          slider below.
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="data">
          <thead>
            <tr>
              <th>#</th>
              <th>Speaker</th>
              <th>Original</th>
              <th>Generated</th>
              <th>Diff</th>
              <th>Play</th>
              <th style={{ width: 150 }}>Speed</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {project.segments.map((s) => {
              const diff = s.duration_diff
              return (
                <tr key={s.id}>
                  <td className="mono">{s.segment_index}</td>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      <span>{s.speaker_id}</span>
                      <SegmentBadge status={s.status} />
                    </div>
                    {s.warning && (
                      <div className="faint" style={{ fontSize: 11, maxWidth: 320 }}>
                        ⚠ {s.warning}
                      </div>
                    )}
                  </td>
                  <td className="mono">{fmtDuration(s.slot_duration)}</td>
                  <td className="mono">
                    {s.aligned_duration != null ? fmtDuration(s.aligned_duration) : '—'}
                    {s.status === 'generating' && <span className="spinner" style={{ marginLeft: 6 }} />}
                  </td>
                  <td>
                    <span className={`badge ${diffTone(diff)}`}>
                      {diff != null ? `${diff > 0 ? '+' : ''}${diff.toFixed(2)}s` : '—'}
                    </span>
                  </td>
                  <td>
                    <div className="row" style={{ gap: 2 }}>
                      <button
                        className="icon-btn"
                        title="play original (seeks video)"
                        onClick={() => {
                          const v = document.getElementById(
                            'voice-review-video',
                          ) as HTMLVideoElement | null
                          if (v) {
                            v.currentTime = s.start_time
                            v.play().catch(() => {})
                          }
                        }}
                      >
                        🎬
                      </button>
                      <button
                        className="icon-btn"
                        title="play generated voice"
                        disabled={!s.aligned_audio_key}
                        style={{ opacity: s.aligned_audio_key ? 1 : 0.35 }}
                        onClick={() => {
                          const a = new Audio(`/api/segments/${s.id}/audio`)
                          a.play().catch(() => alert('audio not ready yet'))
                        }}
                      >
                        🔊
                      </button>
                    </div>
                  </td>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      <input
                        type="range"
                        min="0.7"
                        max="1.6"
                        step="0.05"
                        defaultValue={s.speed_factor || 1}
                        disabled={!s.audio_s3_key}
                        onMouseUp={(e) => setSpeed(s, parseFloat((e.target as HTMLInputElement).value))}
                        onTouchEnd={(e) => setSpeed(s, parseFloat((e.target as HTMLInputElement).value))}
                      />
                      <span className="mono" style={{ fontSize: 11 }}>
                        ×{(s.speed_factor || 1).toFixed(2)}
                      </span>
                    </div>
                  </td>
                  <td>
                    <div className="row" style={{ gap: 4 }}>
                      <button
                        className="btn small"
                        disabled={busySeg === s.id || s.status === 'generating'}
                        onClick={() => regen(s)}
                        title="regenerate this segment only"
                      >
                        🔄
                      </button>
                      <button
                        className={`btn small ${s.approved ? 'ok' : ''}`}
                        disabled={!s.aligned_audio_key}
                        onClick={() => accept(s, !s.approved)}
                      >
                        {s.approved ? '✓ accepted' : 'accept'}
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {continue_.error && <div className="banner error">{continue_.error}</div>}
    </>
  )
}
