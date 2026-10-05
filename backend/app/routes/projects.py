"""Project CRUD + lifecycle actions."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import runner, states
from ..db import get_db
from ..models import Job, Project, Segment, new_id, utcnow
from ..schemas import (
    ProjectCreate,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
    UploadComplete,
    UploadRequest,
    UploadTicket,
)
from ..services.storage import get_storage

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    return project


def project_detail(db: Session, project: Project) -> Project:
    # refresh relationships (they may have been updated by worker threads)
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectSummary])
def list_projects(db: Session = Depends(get_db)):
    projects = (
        db.query(Project).order_by(Project.updated_at.desc()).all()
    )
    out = []
    for p in projects:
        seg_count = (
            db.query(func.count(Segment.id))
            .filter(Segment.project_id == p.id)
            .scalar() or 0
        )
        approved = (
            db.query(func.count(Segment.id))
            .filter(Segment.project_id == p.id, Segment.approved.is_(True))
            .scalar() or 0
        )
        item = ProjectSummary.model_validate(p)
        item.segment_count = seg_count
        item.approved_count = approved
        out.append(item)
    return out


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    if body.source_language == body.target_language:
        raise HTTPException(422, "source and target languages must differ")
    if body.mode == "recap_narration":
        # lip-sync is meaningless for narration mode
        pass
    project = Project(
        id=new_id(),
        name=body.name.strip(),
        source_language=body.source_language,
        target_language=body.target_language,
        mode=body.mode,
        voice_style=body.voice_style or "natural",
        instructions=body.instructions or "",
        bg_volume=0.15,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    return _project_or_404(db, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate,
                   db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    changed_mix = False
    if body.name is not None:
        project.name = body.name.strip()
    if body.bg_volume is not None:
        project.bg_volume = body.bg_volume
        changed_mix = True
    if body.watermark_preview is not None:
        project.watermark_preview = body.watermark_preview
    if body.voice_style is not None:
        project.voice_style = body.voice_style
    if body.instructions is not None:
        project.instructions = body.instructions
    if changed_mix:
        project.audio_version += 1  # invalidate cached mix
    project.touch()
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    storage = get_storage()
    try:
        storage.delete_prefix(f"projects/{project.id}/")
        storage.delete_prefix(f"uploads/{project.id}/")
    except Exception:
        pass
    db.delete(project)
    db.commit()


# ------------------------------------------------------------------ uploads
@router.post("/{project_id}/upload-url", response_model=UploadTicket)
def create_upload_url(project_id: str, body: UploadRequest,
                      db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    if project.status != states.CREATED:
        raise HTTPException(409, f"project already has a video (status {project.status})")
    safe = re.sub(r"[^\w.\-]+", "_", body.filename) or "source.mp4"
    if not re.search(r"\.\w{2,4}$", safe):
        safe += ".mp4"
    key = f"uploads/{project.id}/{safe}"
    ticket = get_storage().presign_put(
        key, body.content_type or "video/mp4", settings_presign_expiry()
    )
    return UploadTicket(**ticket)


def settings_presign_expiry() -> int:
    from ..config import settings

    return settings.s3_presign_expiry


@router.post("/{project_id}/upload-complete", response_model=ProjectOut)
def upload_complete(project_id: str, body: UploadComplete,
                    db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    if project.status not in (states.CREATED, states.UPLOADED, states.FAILED):
        raise HTTPException(409, f"cannot upload in status {project.status}")
    storage = get_storage()
    if not storage.exists(body.key):
        raise HTTPException(400, "uploaded file not found in storage — "
                                 "did the upload finish?")
    project.source_video_s3_key = body.key
    project.source_video_filename = body.filename or body.key.split("/")[-1]
    project.status = states.UPLOADED
    project.error_message = None
    project.touch()
    # create the pipeline job rows (pending) for the processing page
    for step, _ in states.PIPELINE_STEPS:
        job = (
            db.query(Job)
            .filter(Job.project_id == project.id, Job.job_type == step)
            .first()
        )
        if not job:
            db.add(Job(id=new_id(), project_id=project.id, job_type=step,
                       status="pending", payload={}))
    db.commit()
    runner.start_pipeline(project.id, "validate")
    db.refresh(project)
    return project


@router.post("/{project_id}/use-demo", response_model=ProjectOut)
def use_demo_video(project_id: str, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    if project.status not in (states.CREATED, states.FAILED):
        raise HTTPException(409, f"cannot attach demo clip in status {project.status}")
    for step, _ in states.PIPELINE_STEPS:
        job = (
            db.query(Job)
            .filter(Job.project_id == project.id, Job.job_type == step)
            .first()
        )
        if not job:
            db.add(Job(id=new_id(), project_id=project.id, job_type=step,
                       status="pending", payload={}))
    db.commit()
    runner.seed_demo_project(project.id)
    db.expire_all()
    return _project_or_404(db, project_id)


# ------------------------------------------------------------------ actions
def _require_status(project: Project, allowed: list[str]) -> None:
    if project.status not in allowed:
        raise HTTPException(
            409,
            f"action not allowed in status {project.status} "
            f"(expected one of {', '.join(allowed)})",
        )


@router.post("/{project_id}/actions/review-complete", response_model=ProjectOut)
def action_review_complete(project_id: str, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    _require_status(project, [states.AWAITING_USER_REVIEW, states.FAILED])
    if not project.segments:
        raise HTTPException(409, "no segments to voice — run transcription first")
    runner.start_pipeline(project.id, "generate_voice")
    db.expire_all()
    return _project_or_404(db, project_id)


@router.post("/{project_id}/actions/generate-all-voices", response_model=ProjectOut)
def action_generate_all(project_id: str, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    _require_status(project, [
        states.AWAITING_USER_REVIEW, states.AWAITING_VOICE_APPROVAL,
        states.GENERATING_VOICE, states.ALIGNING_TIMING, states.FAILED,
    ])
    runner.start_pipeline(project.id, "generate_voice", force_all=True)
    db.expire_all()
    return _project_or_404(db, project_id)


@router.post("/{project_id}/actions/voice-complete", response_model=ProjectOut)
def action_voice_complete(project_id: str, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    _require_status(project, [states.AWAITING_VOICE_APPROVAL, states.FAILED])
    step = "lip_sync" if project.lipsync_enabled else "render"
    runner.start_pipeline(project.id, step)
    db.expire_all()
    return _project_or_404(db, project_id)


@router.post("/{project_id}/actions/lipsync-approve", response_model=ProjectOut)
def action_lipsync_approve(project_id: str, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    _require_status(project, [states.LIP_SYNCING, states.FAILED])
    if project.lipsync_status != "preview_ready":
        raise HTTPException(409, f"lip-sync preview not ready ({project.lipsync_status})")
    runner.start_pipeline(project.id, "render")
    db.expire_all()
    return _project_or_404(db, project_id)


@router.post("/{project_id}/actions/lipsync-audio-only", response_model=ProjectOut)
def action_lipsync_audio_only(project_id: str, db: Session = Depends(get_db)):
    """Continue with audio-only dubbing when lip-sync fails or looks bad."""
    project = _project_or_404(db, project_id)
    _require_status(project, [states.LIP_SYNCING, states.FAILED])
    project.lipsync_status = "skipped"
    project.touch()
    db.commit()
    runner.start_pipeline(project.id, "render")
    db.expire_all()
    return _project_or_404(db, project_id)


@router.post("/{project_id}/actions/lipsync-retry", response_model=ProjectOut)
def action_lipsync_retry(project_id: str, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    _require_status(project, [states.LIP_SYNCING, states.FAILED])
    runner.start_pipeline(project.id, "lip_sync")
    db.expire_all()
    return _project_or_404(db, project_id)


@router.post("/{project_id}/actions/cancel", response_model=ProjectOut)
def action_cancel(project_id: str, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    if project.status in states.RUNNING_STATUSES or project.status == states.FAILED:
        project.status = states.CANCELLED
        project.error_message = None
        project.touch()
        db.commit()
        for job in db.query(Job).filter(
            Job.project_id == project.id, Job.status.in_(["pending", "running"])
        ):
            job.status = "cancelled"
            job.completed_at = utcnow()
        db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/actions/restart-pipeline", response_model=ProjectOut)
def action_restart_pipeline(project_id: str, db: Session = Depends(get_db)):
    """After CANCELLED/FAILED: resume from the first incomplete step."""
    project = _project_or_404(db, project_id)
    _require_status(project, [states.CANCELLED])
    # find first non-completed step
    start = "validate"
    for step in states.STEP_ORDER:
        job = (
            db.query(Job)
            .filter(Job.project_id == project.id, Job.job_type == step)
            .first()
        )
        if not job or job.status != "completed":
            start = step
            break
    if start == "validate" and not project.source_video_s3_key:
        project.status = states.CREATED
        db.commit()
        db.refresh(project)
        return project
    runner.start_pipeline(project.id, start)
    db.expire_all()
    return _project_or_404(db, project_id)
