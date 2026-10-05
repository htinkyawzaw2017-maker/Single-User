import { useState } from 'react'
import { withKey } from '../api/client'
import { useAction } from '../hooks'
import VideoPlayer, { type VideoPlayerHandle } from '../components/VideoPlayer'
import SegmentTimeline from '../editor/SegmentTimeline'
import SegmentPanel from '../editor/SegmentPanel'
import { useProject } from './ProjectShell'
import type { Segment } from '../types'
import { useRef } from 'react'

/**
 * Transcript & translation editor (spec 4.4):
 *   left = video player · bottom = timeline + segment list · right = segment panel
 */
export default function Editor() {
  const { project, refresh } = useProject()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const playerRef = useRef<VideoPlayerHandle>(null)

  const generateAll = useAction(async () => {
    const { projectAction } = await import('../api/client')
    await projectAction(project!.id, 'review-complete')
    refresh()
  })

  const regenerateAll = useAction(async () => {
    const { projectAction } = await import('../api/client')
    await projectAction(project!.id, 'generate-all-voices')
    refresh()
  })

  if (!project) return null

  if (project.status === 'CREATED') {
    return (
      <div className="banner info">
        📼 Upload a video first — the transcript appears after transcription.
      </div>
    )
  }

  if (project.segments.length === 0) {
    return (
      <div className="banner info">
        ⏳ No segments yet — transcription may still be running. Check the
        Processing tab.
      </div>
    )
  }

  const selected: Segment =
    project.segments.find((s) => s.id === selectedId) || project.segments[0]

  const selectSegment = (s: Segment) => {
    setSelectedId(s.id)
    playerRef.current?.seek(s.start_time, false)
  }

  const playOriginal = (s: Segment) => {
    playerRef.current?.seek(s.start_time, true)
  }

  const editable = project.status === 'AWAITING_USER_REVIEW' ||
    project.status === 'AWAITING_VOICE_APPROVAL' ||
    project.status === 'COMPLETED' ||
    project.status === 'FAILED'
  if (!editable) {
    return (
      <div className="banner info">
        ⏳ The pipeline is still working ({project.status}). Editing unlocks at{' '}
        <b>AWAITING_USER_REVIEW</b>.
      </div>
    )
  }

  return (
    <>
      <div className="row between" style={{ marginBottom: 12 }}>
        <div className="muted">
          {project.segments.length} segments ·{' '}
          {project.segments.filter((s) => s.approved).length} approved ·
          editing text or voice invalidates that segment’s audio
        </div>
        <div className="row">
          {project.status === 'AWAITING_USER_REVIEW' && (
            <button
              className="btn primary"
              onClick={() => generateAll.run()}
              disabled={generateAll.loading}
            >
              🗣 Generate all voices & continue
            </button>
          )}
          {project.status === 'AWAITING_VOICE_APPROVAL' && (
            <button
              className="btn"
              onClick={() => regenerateAll.run()}
              disabled={regenerateAll.loading}
            >
              🔄 Regenerate all voices
            </button>
          )}
        </div>
      </div>

      <div className="editor-grid">
        <div className="editor-left">
          <VideoPlayer
            ref={playerRef}
            src={`/api/projects/${project.id}/video`}
            muted
            onTime={setCurrentTime}
            label={`source video · ${project.source_video_filename || ''}`}
          />
          <div className="row">
            <button className="btn small" onClick={() => playOriginal(selected)}>
              ▶ Play original slot (#{selected.segment_index})
            </button>
            <span className="faint">
              segment {selected.start_time.toFixed(2)}s → {selected.end_time.toFixed(2)}s
            </span>
          </div>
        </div>

        <div className="editor-right">
          <SegmentPanel
            key={selected.id}
            segment={selected}
            targetLanguage={project.target_language}
            onChanged={refresh}
          />
        </div>

        <div className="editor-bottom">
          <SegmentTimeline
            project={project}
            selectedId={selected.id}
            currentTime={currentTime}
            onSelect={selectSegment}
          />
        </div>
      </div>

      {generateAll.error && (
        <div className="banner error" style={{ marginTop: 12 }}>
          {generateAll.error}
        </div>
      )}

      {/* hidden helper: dub preview audio source */}
      <audio hidden src={withKey(`/api/projects/${project.id}/dub-audio`)} />
    </>
  )
}
