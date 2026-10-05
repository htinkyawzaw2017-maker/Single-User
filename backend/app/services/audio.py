"""Audio alignment + mixing helpers.

Dubbing rules implemented here (spec section 9):
  * generated voice stays inside the original dialogue time range
  * time-stretch is capped (MAX_SPEED_STRETCH, default 1.35)
  * when timing is still impossible the segment gets a warning — the user
    should shorten the text or increase speed; the pipeline never silently
    destroys audio
  * original background audio volume is user-controlled (project.bg_volume)
"""
from __future__ import annotations

import os
from pathlib import Path

from ..config import settings
from . import ffmpeg_env


class AlignmentWarning(Exception):
    """Segment audio does not fit its slot even after max stretch."""


def compute_alignment(slot_duration: float, generated_duration: float,
                      manual_speed: float = 1.0) -> dict:
    """Decide the stretch factor for a generated segment.

    Returns {auto_stretch, effective_speed, aligned_duration, fits, warning}.
    `manual_speed` is the user's per-segment speed preference (1.0 = natural).
    """
    effective = max(0.5, min(2.0, manual_speed or 1.0))
    est = generated_duration / effective if generated_duration else slot_duration
    if est <= slot_duration * 1.02:
        # fits already (tiny tolerance) — keep manual speed only
        auto_stretch = 1.0
        aligned = generated_duration / effective if generated_duration else 0.0
        return {
            "auto_stretch": auto_stretch,
            "effective_speed": effective,
            "aligned_duration": round(aligned, 3),
            "fits": True,
            "warning": None,
        }

    needed = est / slot_duration                    # > 1: must speed up
    cap = settings.max_speed_stretch
    if needed <= cap:
        auto_stretch = needed
        aligned = generated_duration / (effective * auto_stretch)
        return {
            "auto_stretch": round(auto_stretch, 4),
            "effective_speed": round(effective * auto_stretch, 4),
            "aligned_duration": round(aligned, 3),
            "fits": True,
            "warning": (
                f"stretched {int((auto_stretch - 1) * 100)}% to fit the "
                "original timing" if auto_stretch > 1.08 else None
            ),
        }

    auto_stretch = cap
    aligned = generated_duration / (effective * cap)
    return {
        "auto_stretch": cap,
        "effective_speed": round(effective * cap, 4),
        "aligned_duration": round(aligned, 3),
        "fits": False,
        "warning": (
            f"Generated voice is {aligned - slot_duration:+.1f}s vs the original "
            f"slot ({slot_duration:.1f}s) even after {int((cap - 1) * 100)}% "
            "speed-up. Shorten the text or increase speed."
        ),
    }


def align_segment_file(raw_wav: str, out_wav: str, auto_stretch: float,
                       manual_speed: float = 1.0) -> str:
    """Write the time-aligned WAV for a segment (stretch = auto × manual)."""
    factor = max(0.5, min(100.0, (auto_stretch or 1.0) * (manual_speed or 1.0)))
    ffmpeg_env.stretch_audio(raw_wav, out_wav, factor)
    return out_wav


def build_dubbed_track(segments: list[dict], total_duration: float,
                       out_wav: str, tmpdir: str) -> str:
    """Concatenate aligned segment audio at the right timeline positions.

    `segments`: [{start, end, local_audio (aligned wav path)}] sorted by start.
    Gaps are filled with silence; result length >= total_duration.
    """
    pieces: list[str] = []
    cursor = 0.0
    for seg in segments:
        start = max(0.0, seg["start"])
        if start > cursor + 0.01:
            gap_path = os.path.join(tmpdir, f"gap_{len(pieces)}.wav")
            ffmpeg_env.make_silence(gap_path, start - cursor)
            pieces.append(gap_path)
            cursor = start
        piece = os.path.join(tmpdir, f"seg_{len(pieces)}.wav")
        ffmpeg_env.convert_to_pcm(seg["local_audio"], piece)
        pieces.append(piece)
        cursor = max(cursor, start + ffmpeg_env.probe(piece)["duration"])

    if not pieces:  # nothing generated yet -> silence
        ffmpeg_env.make_silence(out_wav, max(1.0, total_duration))
        return out_wav

    if cursor < total_duration - 0.01:
        tail = os.path.join(tmpdir, "tail.wav")
        ffmpeg_env.make_silence(tail, total_duration - cursor)
        pieces.append(tail)

    ffmpeg_env.concat_wavs(pieces, out_wav)
    return out_wav


def mix_audio(original_audio: str | None, dubbed_track: str, out_wav: str,
              bg_volume: float, tmpdir: str) -> str:
    """Mix original background audio (volume=bg_volume) with the dubbed track."""
    if not original_audio:
        # no original audio at all — the dubbed track is the full mix
        ffmpeg_env.convert_to_pcm(dubbed_track, out_wav)
        return out_wav

    original_pcm = os.path.join(tmpdir, "orig_48k.wav")
    ffmpeg_env.convert_to_pcm(original_audio, original_pcm, channels=1)
    dubbed_pcm = os.path.join(tmpdir, "dub_48k.wav")
    ffmpeg_env.convert_to_pcm(dubbed_track, dubbed_pcm, channels=1)

    bg = max(0.0, min(1.0, bg_volume))
    filter_complex = (
        f"[0:a]volume={bg:.3f}[bg];"
        "[1:a]volume=1.0[dub];"
        "[dub][bg]amix=inputs=2:duration=longest:normalize=0[mix]"
    )
    ffmpeg_env.run_ffmpeg(
        ["-i", dubbed_pcm, "-i", original_pcm,
         "-filter_complex", filter_complex, "-map", "[mix]",
         "-acodec", "pcm_s16le", out_wav],
        label="mix",
    )
    return out_wav
