import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { getConfig, setAccessKey, withKey } from '../api/client'
import type { AppConfig } from '../types'

interface AppCtx {
  projectId: string | null
  setProjectId: (id: string | null) => void
}

export const AppContext = createContext<AppCtx>({
  projectId: null,
  setProjectId: () => {},
})
export const useApp = () => useContext(AppContext)

/** Global app config (voices, languages, auth requirement). */
export const ConfigContext = createContext<AppConfig | null>(null)
export const useConfig = () => useContext(ConfigContext)

function AccessKeyPrompt({ onDone }: { onDone: () => void }) {
  const [value, setValue] = useState('')
  return (
    <div className="modal-backdrop">
      <div className="modal" style={{ width: 420 }}>
        <div className="modal-head">
          <h3>🔐 Access key required</h3>
        </div>
        <div className="modal-body">
          <div className="muted" style={{ marginBottom: 10 }}>
            This private tool is protected with a single-user access key
            (<span className="kbd">SINGLE_USER_ACCESS_KEY</span> on the server).
          </div>
          <div className="field">
            <label>Access key</label>
            <input
              type="password"
              value={value}
              autoFocus
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && value) {
                  setAccessKey(value)
                  onDone()
                }
              }}
              placeholder="paste your access key…"
            />
          </div>
        </div>
        <div className="modal-foot">
          <button
            className="btn primary"
            disabled={!value}
            onClick={() => {
              setAccessKey(value)
              onDone()
            }}
          >
            Unlock
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [needsKey, setNeedsKey] = useState(false)
  const [projectId, setProjectId] = useState<string | null>(null)

  useEffect(() => {
    getConfig()
      .then((c) => setConfig(c))
      .catch((e) => {
        if (e?.status === 401) setNeedsKey(true)
      })
  }, [])

  // track current project id from URL for the sidebar highlight
  useEffect(() => {
    const m = location.pathname.match(/^\/projects\/([^/]+)/)
    setProjectId(m ? m[1] : null)
  }, [location.pathname])

  return (
    <ConfigContext.Provider value={config}>
      <AppContext.Provider value={{ projectId, setProjectId }}>
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <div className="logo">🎬</div>
              <div>
                Dubbing Studio
                <small>EN ⇄ မြန်မာ · single user</small>
              </div>
            </div>
            <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              <span className="icon">🏠</span> Projects
            </NavLink>
            <NavLink to="/new" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              <span className="icon">➕</span> New project
            </NavLink>
            {projectId && (
              <>
                <div style={{ padding: '10px 12px 4px', fontSize: 11, color: 'var(--text-faint)' }}>
                  CURRENT PROJECT
                </div>
                <NavLink
                  to={`/projects/${projectId}/processing`}
                  className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                >
                  <span className="icon">⚙️</span> Processing
                </NavLink>
                <NavLink
                  to={`/projects/${projectId}/editor`}
                  className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                >
                  <span className="icon">✍️</span> Transcript editor
                </NavLink>
                <NavLink
                  to={`/projects/${projectId}/voice`}
                  className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                >
                  <span className="icon">🎧</span> Voice review
                </NavLink>
                <NavLink
                  to={`/projects/${projectId}/export`}
                  className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                >
                  <span className="icon">📦</span> Export
                </NavLink>
              </>
            )}
            <div className="spacer" />
            <div className="env-chip">
              {config
                ? `${config.app_env} · storage: ${config.upload_mode}`
                : 'connecting…'}
            </div>
          </aside>
          <main className="main">{children}</main>
        </div>
        {needsKey && (
          <AccessKeyPrompt
            onDone={() => {
              setNeedsKey(false)
              window.location.reload()
            }}
          />
        )}
        {/* expose helper for media URLs */}
        <span hidden>{typeof withKey}</span>
        <span hidden>{typeof navigate}</span>
      </AppContext.Provider>
    </ConfigContext.Provider>
  )
}
