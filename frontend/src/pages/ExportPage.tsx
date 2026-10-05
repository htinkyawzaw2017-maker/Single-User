import { useState } from 'react'
import { createExport, listExports, updateProject, withKey } from '../api/client'
import { useAction, usePoll } from '../hooks'
import { useProject } from './ProjectShell'
import type { ExportItem } from '../types'

const GROUP_ICONS: Record<string, string> = {
  video: '🎬',
  audio: '🎵',
  subtitles: '💬',
}

/**
 * Export page (spec 4.7): final MP4, burned-in subtitles, audio tracks,
 * SRT/VTT in both languages, 720p preview with watermark toggle.
 */
export default function ExportPage() {
  const { project, refresh } = useProject()
  const [busy, setBusy] = useState<string | null>(null)

  const exports = usePoll<ExportItem[]>(
    () => listExports(project!.id),
    3000,
    !!project,
  )

  const watermark = useAction(async (value: boolean) => {
    await updateProject(project!.id, { watermark_preview: value })
    refresh()
  })

  const render = async (kind: string) => {
    setBusy(kind)
    try {
      await createExport(project!.id, kind)
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  if (!project) return null

  const groups = ['video', 'audio', 'subtitles'] as const

  return (
    <>
      <div className="banner info">
        📦 Files are stored in cloud storage (S3 in AWS mode) — download links
        stay valid. Preview export is 720p
        <label className="row" style={{ gap: 6, marginLeft: 10, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={project.watermark_preview}
            onChange={(e) => watermark.run(e.target.checked)}
          />
          add “PREVIEW” watermark
        </label>
      </div>

      {project.status !== 'COMPLETED' && (
        <div className="banner warn">
          ⚠ The project is not fully rendered yet ({project.status}) — subtitle
          files may be available, video/audio exports unlock after voice
          generation.
        </div>
      )}

      {project.output_video_s3_key && (
        <div className="card">
          <h3>🎥 Final dubbed video preview</h3>
          <video
            controls
            src={withKey(`/api/storage/${project.output_video_s3_key}`)}
            style={{ maxHeight: 420 }}
          />
        </div>
      )}

      {groups.map((group) => (
        <div key={group} style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 13, color: 'var(--text-dim)', margin: '0 0 10px' }}>
            {GROUP_ICONS[group]} {group.toUpperCase()}
          </h3>
          <div className="export-grid">
            {(exports || [])
              .filter((e) => e.group === group)
              .map((e) => (
                <div className="card export-card" key={e.kind}>
                  <div className="head">
                    <span className="badge neutral">{GROUP_ICONS[e.group]}</span>
                    <b style={{ fontSize: 13.5 }}>{e.label}</b>
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {e.available
                      ? '✓ ready to download'
                      : e.job_status === 'running'
                        ? '⏳ rendering…'
                        : e.job_status === 'failed'
                          ? '⚠ render failed — see Processing logs'
                          : e.note || 'not rendered yet'}
                  </div>
                  <div className="actions">
                    {e.available && e.url && (
                      <a
                        className="btn ok"
                        href={withKey(e.url)}
                        download
                        target="_blank"
                        rel="noreferrer"
                      >
                        ⬇ Download
                      </a>
                    )}
                    {!e.available && (
                      <button
                        className="btn"
                        disabled={
                          busy === e.kind ||
                          e.job_status === 'running' ||
                          e.job_status === 'pending'
                        }
                        onClick={() => render(e.kind)}
                      >
                        {busy === e.kind || e.job_status === 'running' ? '⏳ Rendering…' : '⚙ Render'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
          </div>
        </div>
      ))}

      <div className="card" style={{ marginTop: 18 }}>
        <h3>ℹ️ Notes</h3>
        <ul className="muted" style={{ margin: 0, paddingLeft: 18 }}>
          <li>
            <b>Final MP4</b> keeps the original resolution (up to 1080p) with
            the dubbed audio mixed over a quieter original track.
          </li>
          <li>
            <b>Dual audio MP4</b> includes both the dubbed and the original
            audio as selectable tracks (players like VLC/mpv can switch).
          </li>
          <li>
            <b>Subtitles</b>: SRT + VTT generated from your edited segments in
            both the source and the target language (English &amp; Burmese).
          </li>
          <li>Burned-in subtitle rendering requires an ffmpeg build with libass.</li>
        </ul>
      </div>
    </>
  )
}
