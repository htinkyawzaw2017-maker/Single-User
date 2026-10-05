import { projectAction } from '../api/client'
import { RUNNING_STATUSES, useAction } from '../hooks'
import Pipeline from '../components/Pipeline'
import { useProject } from './ProjectShell'

/**
 * Processing page: live pipeline progress with per-step status,
 * logs, retry and cancel. Auto-redirects to the right page when
 * the pipeline reaches a user-review checkpoint.
 */
export default function Processing() {
  const { project, refresh } = useProject()

  const cancel = useAction(async () => {
    await projectAction(project!.id, 'cancel')
    refresh()
  })

  const restart = useAction(async () => {
    await projectAction(project!.id, 'restart-pipeline')
    refresh()
  })

  const demo = useAction(async () => {
    await projectAction(project!.id, 'use-demo')
    refresh()
  })

  if (!project) return null

  const running = RUNNING_STATUSES.includes(project.status)
  const needsVideo = !project.source_video_s3_key

  return (
    <>
      {needsVideo && (
        <div className="banner info">
          📼 This project has no video yet.{' '}
          {demo.loading ? (
            'attaching demo clip…'
          ) : (
            <button className="btn small" onClick={() => demo.run()}>
              attach the bundled demo clip
            </button>
          )}{' '}
          or open <b>Setup</b> — hmm, use the tabs above after uploading.
        </div>
      )}

      {project.status === 'CANCELLED' && (
        <div className="banner warn">
          ⏹ Processing was cancelled.
          <button className="btn small" onClick={() => restart.run()} disabled={restart.loading}>
            Resume pipeline
          </button>
        </div>
      )}

      {running && (
        <div className="banner info">
          <span className="spinner" />
          Processing runs on the server — you can close this browser safely.
          Status survives refreshes.
          <button
            className="btn small"
            style={{ marginLeft: 'auto' }}
            onClick={() => cancel.run()}
            disabled={cancel.loading}
          >
            Cancel processing
          </button>
        </div>
      )}

      {project.status === 'AWAITING_USER_REVIEW' && (
        <div className="banner ok">
          ✅ Transcript &amp; translation are ready for your review.
          Open the <b>Editor</b> tab to fix text, then generate voices.
        </div>
      )}
      {project.status === 'AWAITING_VOICE_APPROVAL' && (
        <div className="banner ok">
          🎧 Voices are generated and time-aligned. Open the{' '}
          <b>Voice review</b> tab, then continue to render.
        </div>
      )}
      {project.status === 'COMPLETED' && (
        <div className="banner ok">
          🎉 Rendering finished! Open the <b>Export</b> tab to download MP4,
          audio and subtitles.
        </div>
      )}

      <Pipeline project={project} onRefresh={refresh} />

      <div className="card" style={{ marginTop: 16 }}>
        <h3>ℹ️ How retries work</h3>
        <div className="muted">
          A failed step can be retried on its own — the pipeline never
          restarts the whole project. One failed segment doesn’t block the
          others: regenerate individual segments from the editor or voice
          review tabs. Every step keeps a full log you can open inline.
        </div>
      </div>
    </>
  )
}
