import { useEffect, useRef, useState } from 'react'
import {
  approveSegment,
  regenerateSegmentVoice,
  updateSegment,
} from '../api/client'
import {
  fmtDuration,
  useAction,
} from '../hooks'
import type { AppConfig, Segment } from '../types'
import { SegmentBadge } from '../components/StatusBadge'
import { useConfig } from '../components/Layout'

/**
 * Right-hand editor panel for ONE segment:
 * id, speaker, times, original text, translated text, voice, status,
 * play/regenerate/approve + speed & emotion controls.
 */
export default function SegmentPanel({
  segment,
  targetLanguage,
  onChanged,
}: {
  segment: Segment
  targetLanguage: string
  onChanged: () => void
}) {
  const config: AppConfig | null = useConfig()
  // local editable state, synced when the selected segment changes
  const [speaker, setSpeaker] = useState(segment.speaker_id)
  const [start, setStart] = useState(segment.start_time.toFixed(2))
  const [end, setEnd] = useState(segment.end_time.toFixed(2))
  const [sourceText, setSourceText] = useState(segment.source_text)
  const [targetText, setTargetText] = useState(segment.target_text)
  const [voiceId, setVoiceId] = useState(segment.voice_id || '')
  const [emotion, setEmotion] = useState(segment.emotion || 'neutral')
  const [speed, setSpeed] = useState(segment.speed_factor || 1.0)
  const dirty = useRef(false)
  const [savedAt, setSavedAt] = useState<number | null>(null)

  useEffect(() => {
    if (dirty.current) return
    setSpeaker(segment.speaker_id)
    setStart(segment.start_time.toFixed(2))
    setEnd(segment.end_time.toFixed(2))
    setSourceText(segment.source_text)
    setTargetText(segment.target_text)
    setVoiceId(segment.voice_id || '')
    setEmotion(segment.emotion || 'neutral')
    setSpeed(segment.speed_factor || 1.0)
  }, [segment])

  const save = useAction(async (patch: Record<string, unknown>) => {
    await updateSegment(segment.id, patch)
    dirty.current = false
    setSavedAt(Date.now())
    onChanged()
  })

  const regen = useAction(async () => {
    await regenerateSegmentVoice(segment.id)
    onChanged()
  })

  const approve = useAction(async (value: boolean) => {
    await approveSegment(segment.id, value)
    onChanged()
  })

  const voices = (config?.voices || []).filter(
    (v) => v.language === targetLanguage,
  )
  const hasAudio = !!segment.aligned_audio_key || !!segment.audio_s3_key

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="row between">
        <div className="row">
          <span className="badge neutral">#{segment.segment_index}</span>
          <SegmentBadge status={segment.status} />
          {segment.approved && <span className="badge ok">approved</span>}
        </div>
        <div className="row">
          <span className="faint" style={{ fontSize: 11 }}>
            {savedAt ? `saved ${new Date(savedAt).toLocaleTimeString()}` : ''}
          </span>
        </div>
      </div>

      <div className="form-grid">
        <div className="field">
          <label>Speaker</label>
          <input
            value={speaker}
            onChange={(e) => {
              dirty.current = true
              setSpeaker(e.target.value)
            }}
            onBlur={() => save.run({ speaker_id: speaker })}
          />
        </div>
        <div className="field">
          <label>Voice</label>
          <select
            value={voiceId}
            onChange={(e) => {
              setVoiceId(e.target.value)
              save.run({ voice_id: e.target.value })
            }}
          >
            {(config?.voices || []).map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
          {voices.length === 0 && (
            <span className="help">tip: pick a voice matching the target language</span>
          )}
        </div>
        <div className="field">
          <label>Start (s)</label>
          <input
            type="number"
            step="0.05"
            min="0"
            value={start}
            onChange={(e) => {
              dirty.current = true
              setStart(e.target.value)
            }}
            onBlur={() => save.run({ start_time: parseFloat(start) || 0 })}
          />
        </div>
        <div className="field">
          <label>End (s)</label>
          <input
            type="number"
            step="0.05"
            min="0"
            value={end}
            onChange={(e) => {
              dirty.current = true
              setEnd(e.target.value)
            }}
            onBlur={() => save.run({ end_time: parseFloat(end) || 0 })}
          />
        </div>
      </div>

      <div className="field">
        <label>Original ({segment.source_text ? 'source' : 'empty'})</label>
        <textarea
          rows={2}
          value={sourceText}
          onChange={(e) => {
            dirty.current = true
            setSourceText(e.target.value)
          }}
          onBlur={() => save.run({ source_text: sourceText })}
        />
      </div>

      <div className="field">
        <label>Translated / rewritten (dub text)</label>
        <textarea
          rows={4}
          value={targetText}
          onChange={(e) => {
            dirty.current = true
            setTargetText(e.target.value)
          }}
          onBlur={() => save.run({ target_text: targetText })}
        />
        <span className="help">
          edits invalidate the generated voice — regenerate after editing
        </span>
      </div>

      <div className="form-grid">
        <div className="field">
          <label>Emotion / style</label>
          <select
            value={emotion}
            onChange={(e) => {
              setEmotion(e.target.value)
              save.run({ emotion: e.target.value })
            }}
          >
            {(config?.emotions || ['neutral']).map((e) => (
              <option key={e} value={e}>{e}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Speech speed × {speed.toFixed(2)}</label>
          <input
            type="range"
            min="0.7"
            max="1.6"
            step="0.05"
            value={speed}
            onChange={(e) => {
              dirty.current = true
              setSpeed(parseFloat(e.target.value))
            }}
            onMouseUp={() => save.run({ speed_factor: speed })}
            onTouchEnd={() => save.run({ speed_factor: speed })}
          />
          <span className="help">auto-stretch applied: ×{segment.auto_stretch?.toFixed(2) || '1.00'}</span>
        </div>
      </div>

      {(segment.warning || segment.error_message) && (
        <div className={`banner ${segment.error_message ? 'error' : 'warn'}`} style={{ marginBottom: 0 }}>
          <span>⚠</span>
          <div>{segment.error_message || segment.warning}</div>
        </div>
      )}

      <div className="row" style={{ marginTop: 'auto', gap: 8 }}>
        <button
          className="btn"
          title="Play generated voice"
          disabled={!hasAudio}
          onClick={() => {
            const a = document.createElement('audio')
            a.src = `/api/segments/${segment.id}/audio`
            a.play().catch(() => {})
          }}
          style={{ padding: '8px 12px' }}
        >
          ▶ Voice {segment.aligned_duration ? `(${fmtDuration(segment.aligned_duration)})` : ''}
        </button>
        <button
          className="btn"
          disabled={regen.loading || segment.status === 'generating'}
          onClick={() => regen.run()}
        >
          {segment.status === 'generating' ? '⏳ generating…' : '🔄 Regenerate voice'}
        </button>
        <button
          className={`btn ${segment.approved ? 'ok' : 'primary'}`}
          disabled={!hasAudio || approve.loading}
          onClick={() => approve.run(!segment.approved)}
        >
          {segment.approved ? '✓ Approved (undo)' : 'Approve'}
        </button>
      </div>
      {(save.error || regen.error || approve.error) && (
        <div className="banner error" style={{ marginBottom: 0 }}>
          {save.error || regen.error || approve.error}
        </div>
      )}
    </div>
  )
}
