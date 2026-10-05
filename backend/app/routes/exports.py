"""Export endpoints — MP4, audio tracks, subtitles."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import runner, states
from ..db import get_db
from ..models import Job, Project, Segment, new_id
from ..schemas import EXPORT_KINDS, ExportItem
from ..services.storage import get_storage

router = APIRouter(prefix="/api/projects/{project_id}/exports", tags=["exports"])

LABELS = {
    "final_mp4": ("Final MP4 (dubbed)", "video"),
    "final_mp4_720p": ("720p preview MP4", "video"),
    "final_mp4_subs": ("Final MP4 (burned-in subtitles)", "video"),
    "audio_wav": ("Dubbed audio — WAV", "audio"),
    "audio_mp3": ("Dubbed audio — MP3", "audio"),
    "dual_audio_mp4": ("MP4 with selectable audio tracks", "video"),
    "srt_source": ("Subtitles (source language) — SRT", "subtitles"),
    "srt_target": ("Subtitles (target language) — SRT", "subtitles"),
    "vtt_source": ("Subtitles (source language) — VTT", "subtitles"),
    "vtt_target": ("Subtitles (target language) — VTT", "subtitles"),
}
INSTANT_KINDS = {"srt_source", "srt_target", "vtt_source", "vtt_target"}


def _output_key(project: Project, kind: str) -> str | None:
    storage = get_storage()
    prefix = f"projects/{project.id}/output/"
    candidates = {
        "final_mp4": ["final_1080.mp4"],
        "final_mp4_720p": (
            ["final_720p_preview_wm.mp4", "final_720p_preview.mp4"]
            if project.watermark_preview else
            ["final_720p_preview.mp4", "final_720p_preview_wm.mp4"]
        ),
        "final_mp4_subs": [f"final_subs_{project.target_language}.mp4"],
        "audio_wav": ["dubbed_audio.wav"],
        "audio_mp3": ["dubbed_audio.mp3"],
        "dual_audio_mp4": ["final_dual_audio.mp4"],
        "srt_source": [f"subs_{project.source_language}.srt"],
        "srt_target": [f"subs_{project.target_language}.srt"],
        "vtt_source": [f"subs_{project.source_language}.vtt"],
        "vtt_target": [f"subs_{project.target_language}.vtt"],
    }.get(kind, [])
    for name in candidates:
        if storage.exists(prefix + name):
            return prefix + name
    return None


def start_export_job(db: Session, project: Project, kind: str,
                     reuse_job: Job | None = None) -> Job:
    job_type = f"export:{kind}"
    job = reuse_job
    if not job:
        job = (
            db.query(Job)
            .filter(Job.project_id == project.id, Job.job_type == job_type)
            .first()
        )
    if not job:
        job = Job(id=new_id(), project_id=project.id, job_type=job_type,
                  status="pending", payload={"kind": kind})
        db.add(job)
    job.status = "pending"
    job.progress = 0
    job.error_message = None
    job.log = ""
    job.started_at = None
    job.completed_at = None
    job.retry_count = (job.retry_count or 0) + (0 if reuse_job else 0)
    db.commit()
    runner.enqueue(runner.run_export, project.id, kind, job.id)
    return job


def _export_item(db: Session, project: Project, kind: str) -> ExportItem:
    label, group = LABELS[kind]
    key = _output_key(project, kind)
    job = (
        db.query(Job)
        .filter(Job.project_id == project.id, Job.job_type == f"export:{kind}")
        .first()
    )
    ready_for_render = project.status in (
        states.AWAITING_VOICE_APPROVAL, states.LIP_SYNCING, states.COMPLETED
    )
    return ExportItem(
        kind=kind,
        label=label,
        group=group,
        instant=kind in INSTANT_KINDS,
        available=bool(key),
        url=f"/api/storage/{key}" if key else None,
        job_id=job.id if job else None,
        job_status=job.status if job else None,
        note=None if (ready_for_render or kind in INSTANT_KINDS)
        else "available after voice generation",
    )


@router.get("", response_model=list[ExportItem])
def list_exports(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    return [_export_item(db, project, kind) for kind in EXPORT_KINDS]


@router.post("/{kind}", response_model=ExportItem)
def create_export(project_id: str, kind: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if kind not in EXPORT_KINDS:
        raise HTTPException(404, f"unknown export kind: {kind}")
    if kind not in INSTANT_KINDS:
        if project.status not in (
            states.AWAITING_VOICE_APPROVAL, states.LIP_SYNCING, states.COMPLETED
        ):
            raise HTTPException(
                409, "exports unlock after voice generation & timing alignment"
            )
        has_audio = (
            db.query(Segment)
            .filter(Segment.project_id == project.id,
                    Segment.aligned_audio_key.isnot(None))
            .count()
        ) > 0
        if not has_audio:
            raise HTTPException(409, "no generated segment audio to export")

    if _output_key(project, kind):
        return _export_item(db, project, kind)

    start_export_job(db, project, kind)
    return _export_item(db, project, kind)
