"""HTTP TTS provider adapter.

Plug in ANY text-to-speech service that can accept a simple JSON request —
for example a self-hosted Burmese TTS model, or a commercial multilingual TTS.
API keys stay on the server (env var or Secrets Manager), never in the
frontend.

Configure:
  TTS_PROVIDER=http
  TTS_HTTP_URL=https://your-tts.example.com/synthesize
  TTS_HTTP_KEY=...           (sent as Authorization: Bearer <key>)
  TTS_HTTP_FORMAT=wav        (expected audio container)

Expected request/response contract:

  POST <TTS_HTTP_URL>
  {
    "text": "...",
    "voice_id": "my-female-01",
    "speed": 1.0,
    "language": "my",
    "emotion": "neutral"
  }

  <- 200 OK, body = audio bytes (wav/mp3/ogg), Content-Type respected
"""
from __future__ import annotations

import httpx

from ...config import settings
from .. import ffmpeg_env
from . import TtsError, TtsResult


class HttpTts:
    provider = "http"

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0,
                   language: str = "my",
                   emotion: str = "neutral") -> TtsResult:
        if not settings.tts_http_url:
            raise TtsError("TTS_HTTP_URL is not configured")
        headers = {}
        if settings.tts_http_key:
            headers["Authorization"] = f"Bearer {settings.tts_http_key}"
        try:
            resp = httpx.post(
                settings.tts_http_url,
                headers=headers,
                json={
                    "text": text,
                    "voice_id": voice_id,
                    "speed": speed,
                    "language": language,
                    "emotion": emotion,
                },
                timeout=300,
            )
        except Exception as exc:
            raise TtsError(f"TTS request failed: {exc}") from exc
        if resp.status_code != 200:
            raise TtsError(
                f"TTS returned HTTP {resp.status_code}: {resp.text[:300]}"
            )
        audio = resp.content
        ext = settings.tts_http_format or "wav"
        # measure duration via ffmpeg
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as fh:
            fh.write(audio)
            tmp = fh.name
        try:
            duration = ffmpeg_env.audio_duration(tmp)
        except Exception:
            duration = 0.0
        finally:
            os.unlink(tmp)
        return TtsResult(audio=audio, duration=duration, ext=ext, provider="http")
