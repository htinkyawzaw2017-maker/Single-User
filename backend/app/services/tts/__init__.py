"""Text-to-speech provider factory + voice catalog."""
from __future__ import annotations

from dataclasses import dataclass

from ...config import settings

# Voice catalog (single-user tool: fixed curated list).
# In mock mode each voice maps to a distinct tone profile. With the HTTP TTS
# adapter, `id` is forwarded to the provider so a real Burmese TTS service
# (e.g. a self-hosted MM-TTS or a commercial API) can map it to its own voice.
VOICES: list[dict] = [
    {"id": "my-female-01", "name": "မြမြအေး — Mya (F)", "language": "my",
     "gender": "female", "profile": {"base_hz": 235, "drift": 12, "rate": 1.0}},
    {"id": "my-female-02", "name": "ခင်ခင် — Khin (F, dramatic)",
     "language": "my", "gender": "female",
     "profile": {"base_hz": 220, "drift": 30, "rate": 0.95}},
    {"id": "my-male-01", "name": "ကိုသန်း — Ko Than (M)", "language": "my",
     "gender": "male", "profile": {"base_hz": 135, "drift": 10, "rate": 1.0}},
    {"id": "my-male-02", "name": "ကိုဝင်း — Ko Win (M, energetic)",
     "language": "my", "gender": "male",
     "profile": {"base_hz": 150, "drift": 26, "rate": 1.12}},
    {"id": "en-female-01", "name": "Emma (EN, F)", "language": "en",
     "gender": "female", "profile": {"base_hz": 230, "drift": 12, "rate": 1.0}},
    {"id": "en-female-02", "name": "Grace (EN, F, calm)", "language": "en",
     "gender": "female", "profile": {"base_hz": 210, "drift": 6, "rate": 0.92}},
    {"id": "en-male-01", "name": "David (EN, M)", "language": "en",
     "gender": "male", "profile": {"base_hz": 130, "drift": 10, "rate": 1.0}},
    {"id": "en-male-02", "name": "Ryan (EN, M, energetic)", "language": "en",
     "gender": "male", "profile": {"base_hz": 145, "drift": 24, "rate": 1.1}},
]

EMOTIONS = ["neutral", "happy", "sad", "dramatic", "calm", "energetic"]


def voice_catalog(language: str | None = None) -> list[dict]:
    if not language:
        return VOICES
    return [v for v in VOICES if v["language"] == language]


def default_voice_for(language: str, gender: str = "female") -> str:
    for v in VOICES:
        if v["language"] == language and v["gender"] == gender:
            return v["id"]
    for v in VOICES:
        if v["language"] == language:
            return v["id"]
    return VOICES[0]["id"]


def get_voice(voice_id: str) -> dict | None:
    return next((v for v in VOICES if v["id"] == voice_id), None)


@dataclass
class TtsResult:
    audio: bytes
    duration: float
    ext: str          # wav | mp3 ...
    provider: str


class TtsError(RuntimeError):
    pass


def get_tts():
    if settings.tts_provider == "http" and settings.tts_http_url:
        from .http_provider import HttpTts

        return HttpTts()
    from .mock import MockTts

    return MockTts()
