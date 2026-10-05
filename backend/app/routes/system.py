"""System endpoints: health, config, voices."""
from __future__ import annotations

import os

from fastapi import APIRouter

from ..config import settings
from ..schemas import ConfigOut
from ..services import ffmpeg_env
from ..services.tts import EMOTIONS, VOICES

router = APIRouter(tags=["system"])

LANGUAGES = [
    {"code": "en", "label": "English"},
    {"code": "my", "label": "မြန်မာ (Burmese)"},
]
MODES = [
    {"code": "recap_narration",
     "label": "Recap narration",
     "description": "Scene-level narration voice-over. No lip-sync."},
    {"code": "dialogue_dubbing",
     "label": "Dialogue dubbing",
     "description": "Segment-by-segment dialogue dubbing with timing alignment."},
    {"code": "dialogue_lipsync",
     "label": "Dialogue dubbing + lip-sync",
     "description": "Dialogue dubbing plus optional lip-sync preview for short "
                    "front-facing single-speaker clips (beta)."},
]
VOICE_STYLES = ["natural", "dramatic", "calm", "energetic"]


@router.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "ffmpeg": ffmpeg_env.has_ffmpeg(),
        "providers": settings.summary(),
        "time": __import__("time").time(),
    }


@router.get("/api/config", response_model=ConfigOut)
def app_config() -> ConfigOut:
    return ConfigOut(
        app_env=settings.app_env,
        auth_required=bool(settings.access_key),
        upload_mode="s3" if settings.storage_is_s3 else "local",
        max_upload_mb=settings.max_upload_mb,
        languages=LANGUAGES,
        modes=MODES,
        voice_styles=VOICE_STYLES,
        emotions=EMOTIONS,
        voices=VOICES,
        providers=settings.summary(),
        demo_clip_available=os.path.exists(settings.demo_clip_path),
        ffmpeg_available=ffmpeg_env.has_ffmpeg(),
    )


@router.get("/api/voices")
def voices() -> list[dict]:
    return VOICES
