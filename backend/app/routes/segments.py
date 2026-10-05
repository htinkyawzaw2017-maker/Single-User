"""Segment editing + per-segment voice generation."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import runner
from ..db import get_db
from ..models import Job, Project, Segment, new_id, utcnow
from ..schemas import SegmentUpdate
from ..services import ffmpeg_env
from ..services.audio import align_segment_file, compute_alignment
from ..services.storage import get_storage

router = APIRouter(tags=["segments"])


def _segment_or_404(db: Session, segment_id: str) -> Segment:
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "segment not found")
    return seg


def _local_copy(key: str, dest: str) -> str:
    storage = get_storage()
    p = storage.local_path(key)
    if p:
        return p
    return storage.download(key, dest)


@router.patch("/api/segments/{segment_id}")
def update_segment(segment_id: str, body: SegmentUpdate,
                   db: Session = Depends(get_db)):
    seg = _segment_or_404(db, segment_id)
    project = db.get(Project, seg.project_id)
    invalidate_audio = False
    realign = False

    if body.speaker_id is not None:
        seg.speaker_id = body.speaker_id.strip() or "SPEAKER_00"
    if body.start_time is not None:
        seg.start_time = body.start_time
        realign = True
    if body.end_time is not None:
        if body.end_time <= seg.start_time:
            raise HTTPException(422, "end_time must be greater than start_time")
        seg.end_time = body.end_time
        realign = True
    if body.source_text is not None:
        seg.source_text = body.source_text
    if body.target_text is not None:
        if seg.target_text != body.target_text:
            seg.target_text = body.target_text
            invalidate_audio = True  # text changed -> voice must be regenerated
    if body.voice_id is not None:
        if seg.voice_id != body.voice_id:
            seg.voice_id = body.voice_id
            invalidate_audio = True
    if body.emotion is not None:
        if seg.emotion != body.emotion:
            seg.emotion = body.emotion
            invalidate_audio = True
    if body.speed_factor is not None:
        if abs((seg.speed_factor or 1.0) - body.speed_factor) > 0.001:
            seg.speed_factor = body.speed_factor
            realign = True
    if body.approved is not None:
        seg.approved = body.approved

    if invalidate_audio:
        seg.audio_s3_key = None
        seg.aligned_audio_key = None
        seg.audio_duration = None
        seg.aligned_duration = None
        seg.warning = None
        seg.status = "translated" if seg.target_text else "draft"

    if realign and seg.audio_s3_key and not invalidate_audio:
        # re-run timing alignment for this segment inline (fast ffmpeg op)
        try:
            alignment = compute_alignment(
                seg.slot_duration, seg.audio_duration or 0.0,
                seg.speed_factor or 1.0,
            )
            tmp = ffmpeg_env.workdir(f"edit_{seg.id[:6]}")
            raw_local = _local_copy(
                seg.audio_s3_key, os.path.join(tmp, "raw")
            )
            aligned_key = (
                f"projects/{seg.project_id}/audio/"
                f"aligned_{seg.segment_index:04d}.wav"
            )
            aligned_local = os.path.join(tmp, "aligned.wav")
            align_segment_file(raw_local, aligned_local,
                               alignment["auto_stretch"], seg.speed_factor or 1.0)
            get_storage().put_file(aligned_local, aligned_key)
            seg.aligned_audio_key = aligned_key
            seg.aligned_duration = round(
                ffmpeg_env.probe(aligned_local)["duration"], 3
            )
            seg.auto_stretch = alignment["auto_stretch"]
            seg.status = "aligned" if alignment["fits"] else "too_long"
            seg.warning = alignment["warning"]
        except Exception as exc:
            seg.warning = f"re-alignment failed: {exc}"

    seg.updated_at = utcnow()
    if project:
        project.audio_version += 1  # mixed track is stale now
        project.touch()
    db.commit()
    db.refresh(seg)
    return seg


@router.post("/api/segments/{segment_id}/voice")
def regenerate_voice(segment_id: str, db: Session = Depends(get_db)):
    """Generate or regenerate the voice of exactly ONE segment."""
    seg = _segment_or_404(db, segment_id)
    if seg.status == "generating":
        raise HTTPException(409, "segment is already generating")
    if not (seg.target_text or "").strip() and not (seg.source_text or "").strip():
        raise HTTPException(422, "segment has no text — write the target text first")

    job_type = f"segment_voice:{seg.id}"
    job = (
        db.query(Job)
        .filter(Job.project_id == seg.project_id, Job.job_type == job_type)
        .first()
    )
    if not job:
        job = Job(id=new_id(), project_id=seg.project_id, job_type=job_type,
                  status="pending", payload={"segment_id": seg.id})
        db.add(job)
    job.status = "pending"
    job.progress = 0
    job.error_message = None
    job.log = ""
    job.retry_count = (job.retry_count or 0) + 1
    job.started_at = None
    job.completed_at = None
    seg.status = "pending"
    seg.error_message = None
    db.commit()

    runner.enqueue(runner.regenerate_segment_voice, seg.id, job.id)
    return {"job_id": job.id, "segment_id": seg.id}


@router.post("/api/segments/{segment_id}/approve")
def approve_segment(segment_id: str, approved: bool = True,
                    db: Session = Depends(get_db)):
    seg = _segment_or_404(db, segment_id)
    if approved and seg.status not in ("aligned", "too_long"):
        raise HTTPException(
            409, "generate the voice first — approve is only available for "
                 "segments with aligned audio"
        )
    seg.approved = approved
    db.commit()
    db.refresh(seg)
    return seg
