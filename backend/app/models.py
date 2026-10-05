"""Database models — projects, segments, jobs (see spec section 7)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=new_id)
    name = Column(String(200), nullable=False)
    source_language = Column(String(10), nullable=False, default="en")   # en | my
    target_language = Column(String(10), nullable=False, default="my")   # my | en
    mode = Column(String(30), nullable=False, default="dialogue_dubbing")
    # recap_narration | dialogue_dubbing | dialogue_lipsync
    voice_style = Column(String(30), default="natural")
    instructions = Column(Text, default="")

    status = Column(String(40), default="CREATED", index=True)
    source_video_s3_key = Column(String(500))
    mix_audio_key = Column(String(500))       # cached full dubbed mix
    mix_audio_version = Column(Integer, default=-1)
    source_video_filename = Column(String(300))
    video_duration = Column(Float)
    video_width = Column(Integer)
    video_height = Column(Integer)
    video_has_audio = Column(Boolean, default=True)
    output_video_s3_key = Column(String(500))
    error_message = Column(Text)
    bg_volume = Column(Float, default=0.15)       # original background audio volume
    audio_version = Column(Integer, default=0)    # bumped when dubbed mix becomes stale
    watermark_preview = Column(Boolean, default=True)

    # lip-sync (optional beta feature)
    lipsync_status = Column(String(30), default="not_started")
    # not_started | running | preview_ready | failed | approved | skipped
    lipsync_preview_key = Column(String(500))
    lipsync_window_start = Column(Float)
    lipsync_window_end = Column(Float)
    face_quality = Column(String(300))

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    segments = relationship(
        "Segment",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Segment.segment_index",
    )
    jobs = relationship(
        "Job", back_populates="project", cascade="all, delete-orphan"
    )

    # ------------------------------------------------------------------
    @property
    def lipsync_enabled(self) -> bool:
        return self.mode == "dialogue_lipsync"

    def touch(self) -> None:
        self.updated_at = utcnow()


class Segment(Base):
    __tablename__ = "segments"

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    segment_index = Column(Integer, nullable=False)
    speaker_id = Column(String(80), default="SPEAKER_00")

    start_time = Column(Float, nullable=False, default=0.0)
    end_time = Column(Float, nullable=False, default=1.0)
    source_text = Column(Text, default="")
    target_text = Column(Text, default="")

    voice_id = Column(String(80))
    audio_s3_key = Column(String(500))       # raw generated voice (unstretched)
    aligned_audio_key = Column(String(500))  # time-aligned voice
    audio_duration = Column(Float)           # raw generated duration
    aligned_duration = Column(Float)
    speed_factor = Column(Float, default=1.0)  # manual speed (user slider)
    auto_stretch = Column(Float, default=1.0)  # auto stretch applied at align
    status = Column(String(30), default="draft")
    # draft | translated | pending | generating | generated | aligned
    # too_long | failed | approved
    approved = Column(Boolean, default=False)
    emotion = Column(String(30), default="neutral")
    warning = Column(Text)
    error_message = Column(Text)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="segments")

    # ------------------------------------------------------------------
    @property
    def slot_duration(self) -> float:
        return max(0.05, (self.end_time or 0) - (self.start_time or 0))

    @property
    def duration_diff(self) -> float | None:
        if self.aligned_duration is None:
            return None
        return round(self.aligned_duration - self.slot_duration, 3)

    def to_log(self) -> str:
        return (
            f"#{self.segment_index} {self.speaker_id} "
            f"[{self.start_time:.2f}-{self.end_time:.2f}] "
            f"status={self.status} voice={self.voice_id}"
        )


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=new_id)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    job_type = Column(String(60), nullable=False)
    # pipeline steps (validate, extract_audio, transcribe, translate,
    # generate_voice, align_timing, lip_sync, render) or
    # segment_voice:<segment_id> / export:<kind>
    status = Column(String(20), default="pending", index=True)
    # pending | running | completed | failed | cancelled
    progress = Column(Integer, default=0)
    payload = Column(JSON)
    log = Column(Text, default="")
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="jobs")

    # ------------------------------------------------------------------
    def append_log(self, line: str) -> None:
        stamp = utcnow().strftime("%H:%M:%S")
        self.log = (self.log or "") + f"[{stamp}] {line}\n"
        # keep the log bounded
        if len(self.log) > 60_000:
            self.log = "...\n" + self.log[-59_000:]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "job_type": self.job_type,
            "status": self.status,
            "progress": self.progress,
            "log": self.log or "",
            "payload": self.payload,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
