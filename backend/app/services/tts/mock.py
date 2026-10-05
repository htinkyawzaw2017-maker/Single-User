"""Mock TTS — pure-Python WAV synthesizer (no external services).

Produces a distinct tone sequence per voice so that the full dubbing pipeline
(voice generation, timing alignment, mixing, export) can be demonstrated
offline. Speech duration is estimated from syllable counts, so the timing
behavior (segments that are too long / need stretching) is realistic.

For real Burmese/English voices use the HTTP TTS adapter
(TTS_PROVIDER=http + TTS_HTTP_URL) pointing at a real TTS service.
"""
from __future__ import annotations

import io
import math
import random
import re
import struct
import wave

from . import VOICES, TtsError, TtsResult, get_voice

SAMPLE_RATE = 22050

MY_CONSONANT = re.compile(r"[\u1000-\u1021]")
MY_VOWEL = re.compile(r"[\u1024-\u1027\u1029\u102A]")
EN_VOWELGROUP = re.compile(r"[aeiouy]+", re.IGNORECASE)


def estimate_syllables(text: str, language: str) -> int:
    text = (text or "").strip()
    if not text:
        return 1
    if language == "my":
        n = len(MY_CONSONANT.findall(text)) + len(MY_VOWEL.findall(text))
        return max(1, n)
    n = len(EN_VOWELGROUP.findall(text))
    return max(1, n)


def estimate_duration(text: str, language: str, rate: float = 1.0) -> float:
    """Rough spoken duration in seconds."""
    per_syllable = 0.26 if language == "my" else 0.22
    return max(0.35, estimate_syllables(text, language) * per_syllable / max(0.5, rate))


_EMOTION_PARAMS = {
    "neutral": {"pitch_mul": 1.0, "drift_mul": 1.0, "rate_mul": 1.0},
    "happy": {"pitch_mul": 1.12, "drift_mul": 1.6, "rate_mul": 1.05},
    "sad": {"pitch_mul": 0.88, "drift_mul": 0.6, "rate_mul": 0.9},
    "dramatic": {"pitch_mul": 0.95, "drift_mul": 2.0, "rate_mul": 0.92},
    "calm": {"pitch_mul": 0.96, "drift_mul": 0.5, "rate_mul": 0.9},
    "energetic": {"pitch_mul": 1.15, "drift_mul": 1.8, "rate_mul": 1.15},
}


class MockTts:
    provider = "mock"

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0,
                   language: str = "my",
                   emotion: str = "neutral") -> TtsResult:
        voice = get_voice(voice_id)
        if not voice:
            # unknown voice id (e.g. from an HTTP catalog): fall back gracefully
            voice = VOICES[0]
        if not (text or "").strip():
            raise TtsError("empty text")

        profile = voice.get("profile", {"base_hz": 200, "drift": 10, "rate": 1.0})
        emo = _EMOTION_PARAMS.get(emotion, _EMOTION_PARAMS["neutral"])
        rng = random.Random(hash((text, voice_id, emotion)) & 0xFFFFFFFF)

        base_hz = profile["base_hz"] * emo["pitch_mul"]
        drift = profile["drift"] * emo["drift_mul"]
        rate = profile["rate"] * emo["rate_mul"] * max(0.5, speed)

        syllables = estimate_syllables(text, language)
        duration = estimate_duration(text, language, rate)
        syl_dur = duration / syllables

        n_samples = int(duration * SAMPLE_RATE) + SAMPLE_RATE // 10
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            cursor = 0
            for i in range(syllables):
                # start time of this syllable
                t0 = i * syl_dur
                freq = base_hz + rng.uniform(-drift, drift)
                syl_len = syl_dur * rng.uniform(0.72, 0.98)
                while cursor < int((t0 + syl_len) * SAMPLE_RATE):
                    t = cursor / SAMPLE_RATE - t0
                    env = max(0.0, math.sin(math.pi * min(1.0, t / max(1e-4, syl_len)))) ** 0.7
                    # two harmonics for a slightly voice-like timbre
                    s = (
                        math.sin(2 * math.pi * freq * t)
                        + 0.35 * math.sin(2 * math.pi * freq * 2 * t)
                        + 0.15 * math.sin(2 * math.pi * freq * 3 * t)
                    )
                    val = 0.30 * env * s
                    wav.writeframes(struct.pack("<h", int(val * 32767)))
                    cursor += 1
            # trailing pad
            for _ in range(SAMPLE_RATE // 20):
                wav.writeframes(struct.pack("<h", 0))

        return TtsResult(
            audio=buf.getvalue(),
            duration=round(duration + 0.05, 3),
            ext="wav",
            provider="mock",
        )
