"""Mock lip-sync worker.

Generates a real 10–30s preview clip with ffmpeg (original video window +
dubbed audio) so the review page and approval flow work end-to-end, but the
mouth movement is NOT actually re-animated — that requires a GPU model
(Wav2Lip / SadTalker style, see sagemaker.py). The UI labels this clearly.

Face quality check is heuristic in mock mode; set MOCK_LIPSYNC_FAIL=1 to
exercise the graceful-failure path (face unsuitable → warning → continue
with audio-only dubbing).
"""
from __future__ import annotations

from ...config import settings
from .. import ffmpeg_env
from . import FaceQualityError


class MockLipSync:
    provider = "mock"

    def check_face(self, video_path: str, start: float, end: float) -> dict:
        """Heuristic suitability check. Raises FaceQualityError when unusable."""
        if settings.mock_lipsync_fail:
            raise FaceQualityError(
                "Face check failed: side-facing / occluded face detected "
                "(mock provider). Continue with audio-only dubbing or retry."
            )
        window = end - start
        notes = []
        quality = "good"
        if window > settings.lipsync_preview_max_s:
            quality = "warning"
            notes.append("window longer than recommended preview length")
        if window < settings.lipsync_preview_min_s:
            quality = "warning"
            notes.append("window shorter than recommended preview length")
        return {
            "quality": quality,
            "message": (
                "Mock face check passed. Real deployments should use a GPU "
                "face-detection worker (SageMaker) to validate front-facing, "
                "unoccluded single-speaker shots."
                + (" Notes: " + "; ".join(notes) if notes else "")
            ),
        }

    def render_preview(self, video_path: str, start: float, end: float,
                       dubbed_audio_path: str, out_path: str) -> str:
        """Build the preview clip: [start,end] of video + dubbed audio."""
        ffmpeg_env.run_ffmpeg(
            ["-ss", f"{max(0.0, start):.3f}", "-to", f"{end:.3f}",
             "-i", video_path, "-i", dubbed_audio_path,
             "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-b:a", "160k",
             "-shortest", "-movflags", "+faststart", out_path],
            label="lip-sync preview render",
        )
        return out_path
