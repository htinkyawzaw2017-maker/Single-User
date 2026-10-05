"""Media streaming (HTTP Range support for video seeking) + file downloads."""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Project
from ..services.storage import get_storage

router = APIRouter(tags=["media"])

MIME_OVERRIDES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".srt": "text/plain; charset=utf-8",
    ".vtt": "text/vtt; charset=utf-8",
}


def _mime_for(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in MIME_OVERRIDES:
        return MIME_OVERRIDES[ext]
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def _serve_local(path: str, request: Request, filename: str | None = None):
    if not Path(path).exists():
        raise HTTPException(404, "file not found")
    size = Path(path).stat().st_size
    mime = _mime_for(path)
    range_header = request.headers.get("range")

    if range_header:
        match = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if match:
            start_s, end_s = match.groups()
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
            start, end = max(0, start), min(end, size - 1)
            if start > end:
                raise HTTPException(416, "invalid range")

            def iterator():
                with open(path, "rb") as fh:
                    fh.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk = fh.read(min(1024 * 256, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            return StreamingResponse(
                iterator(),
                status_code=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(end - start + 1),
                    "Content-Disposition": f'inline; filename="{filename or Path(path).name}"',
                },
                media_type=mime,
            )

    return FileResponse(path, media_type=mime, filename=filename)


def serve_key(key: str, request: Request, download_name: str | None = None):
    """Serve a storage key (local file or presigned S3 redirect)."""
    storage = get_storage()
    if storage.backend == "local":
        local = storage.local_path(key)
        if not local:
            raise HTTPException(404, "file not found")
        return _serve_local(local, request, download_name)
    # S3: redirect to a time-limited presigned URL
    url = storage.presign_get(key, settings.s3_presign_expiry)
    return RedirectResponse(url)


@router.get("/api/storage/{key:path}")
def storage_file(key: str, request: Request):
    return serve_key(key, request)


def _project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    return project


@router.get("/api/projects/{project_id}/video")
def project_video(project_id: str, request: Request,
                  db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    if not project.source_video_s3_key:
        raise HTTPException(404, "no source video uploaded")
    return serve_key(project.source_video_s3_key, request,
                     project.source_video_filename)


@router.get("/api/projects/{project_id}/dub-audio")
def project_dub_audio(project_id: str, request: Request,
                      db: Session = Depends(get_db)):
    """Full-length dubbed mix (dub voices + quiet original background)."""
    from .. import runner

    project = _project_or_404(db, project_id)
    if not project.mix_audio_key or not get_storage().exists(project.mix_audio_key):
        if project.status in ("CREATED", "UPLOADED", "EXTRACTING_AUDIO",
                              "TRANSCRIBING", "TRANSLATING"):
            raise HTTPException(404, "dubbed audio not generated yet")
        # build on demand (user previewing before final render)
        runner._ensure_mix(db, project)
        db.refresh(project)
    if not project.mix_audio_key:
        raise HTTPException(404, "dubbed audio not available")
    return serve_key(project.mix_audio_key, request, "dubbed_mix.wav")


@router.get("/api/projects/{project_id}/lipsync-preview")
def lipsync_preview(project_id: str, request: Request,
                    db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    if not project.lipsync_preview_key:
        raise HTTPException(404, "no lip-sync preview available")
    return serve_key(project.lipsync_preview_key, request, "lipsync_preview.mp4")


@router.get("/api/segments/{segment_id}/audio")
def segment_audio(segment_id: str, request: Request,
                  db: Session = Depends(get_db)):
    from ..models import Segment

    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "segment not found")
    key = seg.aligned_audio_key or seg.audio_s3_key
    if not key:
        raise HTTPException(404, "no generated audio for this segment")
    return serve_key(key, request, f"segment_{seg.segment_index:04d}.wav")
