"""Transcription provider factory."""
from __future__ import annotations

from dataclasses import dataclass, field

from ...config import settings


@dataclass
class SegmentDraft:
    """A timestamped transcript segment produced by a transcription provider."""
    start: float
    end: float
    text: str
    speaker: str = "SPEAKER_00"
    confidence: float = 1.0
    extra: dict = field(default_factory=dict)


def get_transcriber():
    from .mock import MockTranscriber

    if settings.effective_transcription_provider == "aws":
        try:
            from .aws_transcribe import AwsTranscriber

            return AwsTranscriber()
        except Exception as exc:
            print(f"[transcription] AWS Transcribe unavailable ({exc}); using mock")
    return MockTranscriber()
