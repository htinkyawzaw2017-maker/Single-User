import { useState } from 'react'
import { getJob } from '../api/client'
import type { Job } from '../types'

/** Button + modal that fetches and shows a job's log. */
export default function LogViewer({
  jobId,
  title,
}: {
  jobId: string
  title?: string
}) {
  const [job, setJob] = useState<Job | null>(null)
  const [open, setOpen] = useState(false)

  const open_ = async () => {
    setOpen(true)
    try {
      setJob(await getJob(jobId))
    } catch {
      setJob(null)
    }
  }

  return (
    <>
      <button className="btn small ghost" onClick={open_} title="view logs">
        📄 Logs
      </button>
      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h3>{title || 'Job logs'}</h3>
              <div className="row">
                <span className="faint mono">{jobId.slice(0, 12)}</span>
                <button className="icon-btn" onClick={() => setOpen(false)}>✕</button>
              </div>
            </div>
            <div className="modal-body">
              {job?.error_message && (
                <div className="banner error" style={{ whiteSpace: 'pre-wrap' }}>
                  ⚠ {job.error_message}
                </div>
              )}
              <pre className="log">{job?.log || 'no logs yet'}</pre>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
