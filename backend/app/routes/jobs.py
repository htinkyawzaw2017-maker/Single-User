"""Job status, logs, retry."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import runner, states
from ..db import get_db
from ..models import Job, Project
from ..schemas import JobOut

router = APIRouter(tags=["jobs"])


@router.get("/api/projects/{project_id}/jobs", response_model=list[JobOut])
def list_jobs(project_id: str, db: Session = Depends(get_db)):
    return (
        db.query(Job)
        .filter(Job.project_id == project_id)
        .order_by(Job.created_at)
        .all()
    )


@router.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.post("/api/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    project = db.get(Project, job.project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if project.status == states.CANCELLED:
        raise HTTPException(409, "project is cancelled — restart the pipeline first")

    base_type = job.job_type.split(":", 1)[0]
    job.retry_count = (job.retry_count or 0) + 1
    job.status = "pending"
    job.progress = 0
    job.error_message = None
    job.log = ""
    job.started_at = None
    job.completed_at = None
    db.commit()

    if job.job_type in states.STEP_ORDER:
        runner.start_pipeline(project.id, job.job_type)
    elif base_type == "segment_voice":
        segment_id = job.payload.get("segment_id") if job.payload else None
        segment_id = segment_id or job.job_type.split(":", 1)[1]
        runner.enqueue(runner.regenerate_segment_voice, segment_id, job.id)
    elif base_type == "export":
        from .exports import start_export_job

        start_export_job(db, project, job.job_type.split(":", 1)[1], reuse_job=job)
    else:
        raise HTTPException(400, f"cannot retry job of type {job.job_type}")

    db.refresh(job)
    return job
