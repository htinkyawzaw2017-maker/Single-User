import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  deleteProject,
  listProjects,
  projectAction,
} from '../api/client'
import {
  LANG_FLAG,
  LANG_LABEL,
  MODE_LABEL,
  fmtDate,
  pageForStatus,
  useAction,
  usePoll,
} from '../hooks'
import type { ProjectSummary } from '../types'
import { ProjectStatusBadge } from '../components/StatusBadge'
import ConfirmDialog from '../components/ConfirmDialog'

export default function Dashboard() {
  const navigate = useNavigate()
  const [tick, setTick] = useState(0)
  const projects = usePoll<ProjectSummary[]>(
    () => listProjects(),
    4000,
    true,
  )
  const [toDelete, setToDelete] = useState<ProjectSummary | null>(null)

  const del = useAction(async (id: string) => {
    await deleteProject(id)
    setToDelete(null)
    setTick((t) => t + 1)
  })

  const cancel = useAction(async (id: string) => {
    await projectAction(id, 'cancel')
    setTick((t) => t + 1)
  })

  void tick // re-render helper

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>🎬 Dubbing projects</h1>
          <div className="sub">
            Private single-user workspace — upload, transcribe, translate,
            dub and export Burmese ⇄ English videos.
          </div>
        </div>
        <Link to="/new" className="btn primary">＋ Create new project</Link>
      </div>

      {projects && projects.length === 0 && (
        <div className="empty-state">
          <div className="big">🎞</div>
          <h3>No projects yet</h3>
          <p>
            Create your first project, upload a movie clip, and let the
            pipeline transcribe &amp; translate it.
          </p>
          <Link to="/new" className="btn primary">Create new project</Link>
        </div>
      )}

      <div className="project-grid">
        {(projects || []).map((p) => {
          const page = pageForStatus(p.status, p.mode)
          return (
            <div className="card project-card" key={p.id}>
              <div className="title-row">
                <h3 title={p.name}>{p.name}</h3>
                <ProjectStatusBadge status={p.status} />
              </div>
              <div className="meta">
                <span className="badge neutral">
                  {LANG_FLAG[p.source_language]} {LANG_LABEL[p.source_language]}
                  &nbsp;→&nbsp;
                  {LANG_FLAG[p.target_language]} {LANG_LABEL[p.target_language]}
                </span>
                <span className="badge neutral">{MODE_LABEL[p.mode] || p.mode}</span>
              </div>
              {p.error_message && (
                <div className="banner error" style={{ marginBottom: 0, fontSize: 12 }}>
                  ⚠ {p.error_message.slice(0, 140)}
                </div>
              )}
              <div className="stats">
                <span>🧩 {p.segment_count} segments</span>
                <span>✓ {p.approved_count} approved</span>
                <span>🕒 {fmtDate(p.updated_at)}</span>
              </div>
              <div className="actions">
                <button
                  className="btn primary"
                  onClick={() => navigate(`/projects/${p.id}/${page}`)}
                >
                  Continue →
                </button>
                {['CREATED', 'UPLOADED', 'EXTRACTING_AUDIO', 'TRANSCRIBING',
                  'TRANSLATING', 'GENERATING_VOICE', 'ALIGNING_TIMING',
                  'LIP_SYNCING', 'RENDERING', 'FAILED'].includes(p.status) && (
                  <button
                    className="btn"
                    title="cancel processing"
                    onClick={() => cancel.run(p.id)}
                  >
                    ⏹
                  </button>
                )}
                <button
                  className="btn danger"
                  title="delete project"
                  onClick={() => setToDelete(p)}
                >
                  🗑
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {toDelete && (
        <ConfirmDialog
          title="Delete project?"
          danger
          confirmLabel="Delete forever"
          message={
            <>
              <b>{toDelete.name}</b> and all its segments, generated audio and
              exports will be removed from storage. This cannot be undone.
            </>
          }
          onCancel={() => setToDelete(null)}
          onConfirm={() => del.run(toDelete.id)}
        />
      )}
    </div>
  )
}
