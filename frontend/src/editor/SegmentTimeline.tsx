import { useEffect, useRef } from 'react'
import type { Project, Segment } from '../types'

/**
 * Bottom pane of the editor: proportional timeline blocks on top,
 * scrollable segment list underneath. Clicking selects + seeks the video.
 */
export default function SegmentTimeline({
  project,
  selectedId,
  currentTime,
  onSelect,
}: {
  project: Project
  selectedId: string | null
  currentTime: number
  onSelect: (segment: Segment) => void
}) {
  const listRef = useRef<HTMLDivElement>(null)
  const duration = project.video_duration || 60

  useEffect(() => {
    if (!selectedId || !listRef.current) return
    const el = listRef.current.querySelector(`[data-seg="${selectedId}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [selectedId])

  return (
    <div className="timeline-wrap">
      <div className="timeline-track">
        {project.segments.map((s) => {
          const left = (s.start_time / duration) * 100
          const width = Math.max(0.7, ((s.end_time - s.start_time) / duration) * 100)
          const cls = [
            'timeline-block',
            s.id === selectedId ? 'selected' : '',
            s.status === 'failed' ? 'failed' : '',
            s.approved ? 'approved' : '',
          ]
            .filter(Boolean)
            .join(' ')
          return (
            <div
              key={s.id}
              className={cls}
              style={{ left: `${left}%`, width: `${width}%` }}
              title={`#${s.segment_index} ${s.speaker_id} — ${s.target_text?.slice(0, 60)}`}
              onClick={() => onSelect(s)}
            >
              <span>{s.segment_index}</span>
            </div>
          )
        })}
        <div
          className="timeline-playhead"
          style={{ left: `${Math.min(100, (currentTime / duration) * 100)}%` }}
        />
      </div>

      <div className="segment-list" ref={listRef}>
        {project.segments.map((s) => (
          <div
            key={s.id}
            data-seg={s.id}
            className={`segment-row${s.id === selectedId ? ' selected' : ''}`}
            onClick={() => onSelect(s)}
          >
            <span className="idx">#{s.segment_index}</span>
            <span className="spk">{s.speaker_id}</span>
            <span className="time">
              {s.start_time.toFixed(2)} → {s.end_time.toFixed(2)}
            </span>
            <span className="text">
              {s.target_text || s.source_text || '(empty)'}
            </span>
            {s.status === 'failed' && <span className="badge error">failed</span>}
            {s.status === 'too_long' && <span className="badge warn">too long</span>}
            {s.approved && <span className="badge ok">✓</span>}
          </div>
        ))}
      </div>
    </div>
  )
}
