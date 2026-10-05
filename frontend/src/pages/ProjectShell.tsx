import { createContext, useContext, useCallback, useState } from 'react'
import {
  Navigate,
  Route,
  Routes,
  NavLink,
  useParams,
} from 'react-router-dom'
import { getProject } from '../api/client'
import { LANG_FLAG, LANG_LABEL, MODE_LABEL, pageForStatus, usePoll } from '../hooks'
import type { Project } from '../types'
import { ProjectStatusBadge } from '../components/StatusBadge'
import Processing from './Processing'
import Editor from './Editor'
import VoiceReview from './VoiceReview'
import LipSyncReview from './LipSyncReview'
import ExportPage from './ExportPage'
import NewProject from './NewProject'

/** Per-project context: live project + manual refresh. */
export const ProjectContext = createContext<{
  project: Project | null
  refresh: () => void
}>({ project: null, refresh: () => {} })

export const useProject = () => useContext(ProjectContext)

const TABS = [
  { slug: 'processing', label: 'Processing', icon: '⚙️' },
  { slug: 'editor', label: 'Editor', icon: '✍️' },
  { slug: 'voice', label: 'Voice review', icon: '🎧' },
  { slug: 'lipsync', label: 'Lip-sync', icon: '👄' },
  { slug: 'export', label: 'Export', icon: '📦' },
]

export default function ProjectShell() {
  const { id } = useParams<{ id: string }>()
  const [nonce, setNonce] = useState(0)
  const refresh = useCallback(() => setNonce((n) => n + 1), [])

  const project = usePoll<Project>(
    () => getProject(id!),
    2500,
    !!id,
    nonce,
  )

  if (!project) {
    return (
      <div className="page">
        <div className="card muted">Loading project…</div>
      </div>
    )
  }

  const target = pageForStatus(project.status, project.mode)

  return (
    <ProjectContext.Provider value={{ project, refresh }}>
      <div className="page">
        <div className="page-header">
          <div>
            <h1>{project.name}</h1>
            <div className="sub">
              {LANG_FLAG[project.source_language]} {LANG_LABEL[project.source_language]}
              &nbsp;→&nbsp;
              {LANG_FLAG[project.target_language]} {LANG_LABEL[project.target_language]}
              &nbsp;·&nbsp;{MODE_LABEL[project.mode]}
              {project.video_duration
                ? ` · ${project.video_duration.toFixed(1)}s source`
                : ''}
            </div>
          </div>
          <ProjectStatusBadge status={project.status} />
        </div>

        {project.status === 'FAILED' && project.error_message && (
          <div className="banner error">
            <b>⚠ Failed:</b> {project.error_message}
            <span className="faint">
              {' '}
              — open the failed step’s logs on the Processing tab to retry.
            </span>
          </div>
        )}

        <div className="tabs">
          {TABS.filter((t) => t.slug !== 'lipsync' || project.mode === 'dialogue_lipsync').map(
            (t) => (
              <NavLink
                key={t.slug}
                to={`/projects/${project.id}/${t.slug}`}
                className={({ isActive }) => `tab${isActive ? ' active' : ''}`}
              >
                <span>{t.icon}</span> {t.label}
                {t.slug === target && <span className="badge info">you are here</span>}
              </NavLink>
            ),
          )}
        </div>

        <Routes>
          <Route index element={<Navigate to={target} replace />} />
          <Route path="processing" element={<Processing />} />
          <Route path="setup" element={<NewProject existingId={project.id} />} />
          <Route path="editor" element={<Editor />} />
          <Route path="voice" element={<VoiceReview />} />
          <Route path="lipsync" element={<LipSyncReview />} />
          <Route path="export" element={<ExportPage />} />
          <Route path="*" element={<Navigate to={target} replace />} />
        </Routes>
      </div>
    </ProjectContext.Provider>
  )
}
