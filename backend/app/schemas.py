"""Pydantic request / response schemas."""
from __future__ import annotations

from typing import Any, Literal, Optional

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _dt(v):
    return v.isoformat() if isinstance(v, datetime) else v

Language = Literal["en", "my"]
Mode = Literal["recap_narration", "dialogue_dubbing", "dialogue_lipsync"]


# ---------------------------------------------------------------- projects
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_language: Language = "en"
    target_language: Language = "my"
    mode: Mode = "dialogue_dubbing"
    voice_style: str = "natural"
    instructions: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    bg_volume: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    watermark_preview: Optional[bool] = None
    voice_style: Optional[str] = None
    instructions: Optional[str] = None


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    segment_index: int
    speaker_id: str
    start_time: float
    end_time: float
    source_text: str
    target_text: str
    voice_id: Optional[str] = None
    audio_s3_key: Optional[str] = None
    aligned_audio_key: Optional[str] = None
    audio_duration: Optional[float] = None
    aligned_duration: Optional[float] = None
    speed_factor: float = 1.0
    auto_stretch: float = 1.0
    status: str
    approved: bool
    emotion: str
    warning: Optional[str] = None
    error_message: Optional[str] = None
    slot_duration: float
    duration_diff: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_serializer("created_at", "updated_at")
    def _ser_dt(self, v):
        return _dt(v)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    job_type: str
    status: str
    progress: int
    log: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None

    @field_serializer("started_at", "completed_at", "created_at")
    def _ser_dt(self, v):
        return _dt(v)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_language: str
    target_language: str
    mode: str
    voice_style: str
    instructions: str
    status: str
    source_video_s3_key: Optional[str] = None
    source_video_filename: Optional[str] = None
    video_duration: Optional[float] = None
    video_width: Optional[int] = None
    video_height: Optional[int] = None
    video_has_audio: bool = True
    output_video_s3_key: Optional[str] = None
    error_message: Optional[str] = None
    bg_volume: float
    audio_version: int
    watermark_preview: bool
    lipsync_status: str
    lipsync_preview_key: Optional[str] = None
    lipsync_window_start: Optional[float] = None
    lipsync_window_end: Optional[float] = None
    face_quality: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    segments: list[SegmentOut] = []
    jobs: list[JobOut] = []

    @field_serializer("created_at", "updated_at")
    def _ser_dt(self, v):
        return _dt(v)


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_language: str
    target_language: str
    mode: str
    status: str
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    segment_count: int = 0
    approved_count: int = 0

    @field_serializer("created_at", "updated_at")
    def _ser_dt(self, v):
        return _dt(v)


# ---------------------------------------------------------------- segments
class SegmentUpdate(BaseModel):
    speaker_id: Optional[str] = Field(default=None, max_length=80)
    start_time: Optional[float] = Field(default=None, ge=0.0)
    end_time: Optional[float] = Field(default=None, ge=0.0)
    source_text: Optional[str] = None
    target_text: Optional[str] = None
    voice_id: Optional[str] = None
    speed_factor: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    emotion: Optional[str] = None
    approved: Optional[bool] = None


# ---------------------------------------------------------------- uploads
class UploadRequest(BaseModel):
    filename: str
    content_type: str = "video/mp4"
    size: int = 0


class UploadTicket(BaseModel):
    mode: Literal["local", "s3"]
    url: str
    method: str = "PUT"
    key: str
    headers: dict[str, str] = {}
    expires_in: int = 3600


class UploadComplete(BaseModel):
    key: str
    filename: Optional[str] = None


# ---------------------------------------------------------------- exports
EXPORT_KINDS = [
    "final_mp4",
    "final_mp4_720p",
    "final_mp4_subs",
    "audio_wav",
    "audio_mp3",
    "dual_audio_mp4",
    "srt_source",
    "srt_target",
    "vtt_source",
    "vtt_target",
]


class ExportItem(BaseModel):
    kind: str
    label: str
    group: str
    instant: bool = False
    available: bool = False
    url: Optional[str] = None
    job_id: Optional[str] = None
    job_status: Optional[str] = None
    note: Optional[str] = None


class ConfigOut(BaseModel):
    app_name: str = "Burmese/English Movie Dubbing Tool"
    app_env: str
    auth_required: bool
    upload_mode: str
    max_upload_mb: int
    languages: list[dict[str, str]]
    modes: list[dict[str, str]]
    voice_styles: list[str]
    emotions: list[str]
    voices: list[dict[str, Any]]
    providers: dict[str, str]
    demo_clip_available: bool
    ffmpeg_available: bool
