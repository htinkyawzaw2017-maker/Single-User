import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  completeUpload,
  createProject,
  getProject,
  requestUploadUrl,
  updateProject,
  uploadFile,
  useDemoClip,
} from '../api/client'
import { useAction } from '../hooks'
import { useConfig } from '../components/Layout'
import type { Language, Mode, Project } from '../types'

/**
 * New project form:
 * name · upload · source/target language · mode · voice style · instructions.
 * When `existingId` is set, continues setup for an already-created project.
 */
export default function NewProject({ existingId }: { existingId?: string }) {
  const config = useConfig()
  const navigate = useNavigate()
  const { id: routeId } = useParams()
  const projectId = existingId || routeId

  const [name, setName] = useState('')
  const [source, setSource] = useState<Language>('en')
  const [target, setTarget] = useState<Language>('my')
  const [mode, setMode] = useState<Mode>('dialogue_dubbing')
  const [style, setStyle] = useState('natural')
  const [instructions, setInstructions] = useState('')

  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [project, setProject] = useState<Project | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  // load existing project for continuation
  useEffect(() => {
    if (!projectId) return
    getProject(projectId).then((p) => {
      setProject(p)
      setName(p.name)
      setSource(p.source_language)
      setTarget(p.target_language)
      setMode(p.mode)
      setStyle(p.voice_style)
      setInstructions(p.instructions)
    }).catch(() => {})
  }, [projectId])

  const create = useAction(async () => {
    if (!name.trim()) throw new Error('project name is required')
    if (source === target) throw new Error('source and target languages must differ')
    const p = await createProject({
      name: name.trim(),
      source_language: source,
      target_language: target,
      mode,
      voice_style: style,
      instructions,
    })
    setProject(p)
    return p
  })

  const startUpload = useAction(async (p: Project) => {
    if (!file) throw new Error('choose a video file first')
    if (file.size > (config?.max_upload_mb || 2048) * 1024 * 1024) {
      throw new Error(`file exceeds the ${config?.max_upload_mb}MB limit`)
    }
    const ticket = await requestUploadUrl(
      p.id,
      file.name,
      file.type || 'video/mp4',
      file.size,
    )
    setUploadPct(0)
    await uploadFile(ticket, file, ({ loaded, total }) =>
      setUploadPct(total ? Math.round((loaded / total) * 100) : 0),
    )
    await completeUpload(p.id, ticket.key, file.name)
    setUploadPct(100)
    navigate(`/projects/${p.id}/processing`)
  })

  const useDemo = useAction(async (p: Project) => {
    await useDemoClip(p.id)
    navigate(`/projects/${p.id}/processing`)
  })

  const submit = async () => {
    let p = project
    if (!p) p = await create.run()
    else {
      // update existing project settings
      p = await updateProject(p.id, { name: name.trim(), voice_style: style, instructions })
    }
    if (p) await startUpload.run(p)
  }

  const submitDemo = async () => {
    let p = project
    if (!p) p = await create.run()
    if (p) await useDemo.run(p)
  }

  const uploading = uploadPct !== null && uploadPct < 100
  const busy = create.loading || startUpload.loading || useDemo.loading

  return (
    <div className="page" style={{ maxWidth: 780 }}>
      <div className="page-header">
        <div>
          <h1>{projectId ? '⚙️ Finish project setup' : '➕ New dubbing project'}</h1>
          <div className="sub">
            Upload a movie clip or recap video, pick languages and mode —
            the pipeline handles the rest.
          </div>
        </div>
      </div>

      <div className="card">
        <div className="field">
          <label>Project name</label>
          <input
            type="text"
            value={name}
            placeholder="e.g. Action movie recap — episode 12"
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="form-grid">
          <div className="field">
            <label>Source language</label>
            <select
              value={source}
              disabled={!!project}
              onChange={(e) => setSource(e.target.value as Language)}
            >
              {(config?.languages || []).map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Target language</label>
            <select
              value={target}
              disabled={!!project}
              onChange={(e) => setTarget(e.target.value as Language)}
            >
              {(config?.languages || [])
                .filter((l) => l.code !== source)
                .map((l) => (
                  <option key={l.code} value={l.code}>{l.label}</option>
                ))}
            </select>
            <span className="help">
              English ⇄ Burmese{project ? ' — locked after creation' : ''}
            </span>
          </div>
        </div>

        <div className="field">
          <label>Mode</label>
          <div className="mode-picker">
            {(config?.modes || []).map((m) => (
              <div
                key={m.code}
                className={`mode-card${mode === m.code ? ' selected' : ''}${project ? ' disabled' : ''}`}
                style={project ? { opacity: 0.55, cursor: 'not-allowed' } : undefined}
                onClick={() => !project && setMode(m.code)}
              >
                <div className="t">{m.label}</div>
                <div className="d">{m.description}</div>
              </div>
            ))}
          </div>
          {mode === 'dialogue_lipsync' && (
            <span className="help">
              ⚠ Beta: lip-sync runs a 10–30s preview first and needs a single
              front-facing speaker. Audio-only dubbing always remains available.
            </span>
          )}
        </div>

        <div className="form-grid">
          <div className="field">
            <label>Voice style</label>
            <select value={style} onChange={(e) => setStyle(e.target.value)}>
              {(config?.voice_styles || ['natural']).map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Upload video</label>
            <div
              className={`dropzone${dragOver ? ' drag' : ''}`}
              style={{ padding: '20px 14px' }}
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                const f = e.dataTransfer.files?.[0]
                if (f) setFile(f)
              }}
            >
              {file ? (
                <div>
                  <b>{file.name}</b>
                  <div className="faint">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
                </div>
              ) : (
                <div>
                  <div className="big">📼</div>
                  Drop a video here or <u>click to browse</u>
                  <div className="faint" style={{ fontSize: 11 }}>
                    mp4 / mkv / mov · up to {config?.max_upload_mb || 2048} MB
                  </div>
                </div>
              )}
            </div>
            <input
              ref={fileInput}
              type="file"
              accept="video/*"
              hidden
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </div>
        </div>

        <div className="field">
          <label>Instructions for the AI rewrite (optional)</label>
          <textarea
            rows={3}
            value={instructions}
            placeholder="e.g. Use casual spoken Burmese, keep character names in English, shorten long lines to fit the timing…"
            onChange={(e) => setInstructions(e.target.value)}
          />
        </div>

        {uploadPct !== null && (
          <div className="stack" style={{ marginBottom: 14 }}>
            <div className="row between">
              <span className="muted">
                {uploading ? 'Uploading…' : 'Upload complete ✓'}
              </span>
              <span className="muted">{uploadPct}%</span>
            </div>
            <div className="progressbar">
              <div className="fill" style={{ width: `${uploadPct}%` }} />
            </div>
          </div>
        )}

        {(create.error || startUpload.error) && (
          <div className="banner error">
            ⚠ {create.error || startUpload.error}
          </div>
        )}

        <div className="row">
          <button className="btn primary" onClick={submit} disabled={busy || uploading}>
            {busy ? '⏳ Working…' : projectId ? 'Save & upload' : 'Create & upload'}
          </button>
          {config?.demo_clip_available && (
            <button className="btn" onClick={submitDemo} disabled={busy || uploading}>
              🧪 Use bundled demo clip
            </button>
          )}
          <span className="faint" style={{ fontSize: 11.5 }}>
            files go to cloud storage (S3 in AWS mode), never the app server
          </span>
        </div>
      </div>
    </div>
  )
}
