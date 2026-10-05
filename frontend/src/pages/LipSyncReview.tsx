import { projectAction } from '../api/client'
import { fmtDuration, useAction } from '../hooks'
import { withKey } from '../api/client'
import { useProject } from './ProjectShell'

/**
 * Lip-sync review (spec 4.6): original clip · dubbed audio · lip-synced
 * preview · face-quality warning · retry · approve · continue audio-only.
 */
export default function LipSyncReview() {
  const { project, refresh } = useProject()

  const approve = useAction(async () => {
    await projectAction(project!.id, 'lipsync-approve')
    refresh()
  })
  const audioOnly = useAction(async () => {
    await projectAction(project!.id, 'lipsync-audio-only')
    refresh()
  })
  const retry = useAction(async () => {
    await projectAction(project!.id, 'lipsync-retry')
    refresh()
  })

  if (!project) return null
  if (project.mode !== 'dialogue_lipsync') {
    return (
      <div className="banner info">
        Lip-sync is not enabled for this project (mode: {project.mode}).
      </div>
    )
  }

  const ls = project.lipsync_status
  const running = ls === 'running'
  const failed = ls === 'failed'
  const ready = ls === 'preview_ready'

  return (
    <>
      {running && (
        <div className="banner info">
          <span className="spinner" /> Generating the 10–30s lip-sync preview…
        </div>
      )}

      {failed && (
        <div className="banner error">
          <div>
            <b>⚠ Lip-sync failed / face not suitable.</b>
            <div className="muted" style={{ marginTop: 4 }}>
              {project.face_quality || 'Face check failed — side-facing, occluded, moving, or multiple speakers.'}
              <br />
              Your audio-only dub is safe. Continue without lip-sync or retry.
            </div>
          </div>
        </div>
      )}

      {ready && (
        <div className="banner ok">
          ✅ Lip-sync preview is ready. Review it below — if the mouth movement
          looks wrong, retry or continue with audio-only dubbing.
        </div>
      )}

      {project.status === 'COMPLETED' && (
        <div className="banner ok">🎉 This project has been rendered. See the Export tab.</div>
      )}

      <div className="card">
        <h3>
          👄 Lip-sync preview window{' '}
          {project.lipsync_window_start != null && (
            <span className="muted">
              ({project.lipsync_window_start.toFixed(1)}s →{' '}
              {(project.lipsync_window_end || 0).toFixed(1)}s ·{' '}
              {fmtDuration(
                (project.lipsync_window_end || 0) - (project.lipsync_window_start || 0),
              )})
            </span>
          )}
        </h3>
        <div
          className="stack"
          style={{
            gridTemplateColumns: 'none',
            display: 'grid',
            gap: 14,
          }}
        >
          <div>
            <div className="muted" style={{ marginBottom: 6 }}>
              <b>Original clip</b> (from the source video)
            </div>
            <video
              controls
              src={withKey(`/api/projects/${project.id}/video`)}
              style={{ maxHeight: 300 }}
            />
          </div>
          <div>
            <div className="muted" style={{ marginBottom: 6 }}>
              <b>Dubbed audio</b> (voices + quiet background)
            </div>
            <audio controls src={withKey(`/api/projects/${project.id}/dub-audio`)} />
          </div>
          <div>
            <div className="muted" style={{ marginBottom: 6 }}>
              <b>Lip-synced preview</b>{' '}
              {ls !== 'preview_ready' && (
                <span className="faint">— appears here once generated</span>
              )}
            </div>
            {ls === 'preview_ready' && project.lipsync_preview_key ? (
              <video
                controls
                src={withKey(`/api/projects/${project.id}/lipsync-preview`)}
                style={{ maxHeight: 300 }}
              />
            ) : (
              <div className="empty-state" style={{ padding: 30 }}>
                {running ? '⏳ rendering preview…' : 'no preview yet'}
              </div>
            )}
          </div>
        </div>

        {project.face_quality && ls !== 'failed' && (
          <div className="banner info" style={{ marginTop: 12, marginBottom: 0 }}>
            🧑 Face quality: {project.face_quality}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Actions</h3>
        <div className="row">
          <button
            className="btn primary"
            disabled={!ready || approve.loading || project.status === 'COMPLETED'}
            onClick={() => approve.run()}
          >
            ✅ Approve &amp; render final video
          </button>
          <button
            className="btn"
            disabled={retry.loading || running}
            onClick={() => retry.run()}
          >
            ↻ Retry lip-sync
          </button>
          <button
            className="btn"
            onClick={() => audioOnly.run()}
            disabled={audioOnly.loading || project.status === 'COMPLETED'}
            title="the audio-dubbed output is always preserved"
          >
            🎧 Continue with audio-only dubbing
          </button>
        </div>
        <div className="muted" style={{ marginTop: 10 }}>
          Lip-sync is an optional beta: one front-facing speaker, short clips.
          If it fails, nothing is lost — the audio-dubbed output stays
          available.
        </div>
      </div>

      {(approve.error || audioOnly.error || retry.error) && (
        <div className="banner error">{approve.error || audioOnly.error || retry.error}</div>
      )}
    </>
  )
}
