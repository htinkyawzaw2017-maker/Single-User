"""FFmpeg helpers.

Resolution order for the binary:
  1. FFMPEG_BIN env var
  2. system ffmpeg on PATH (Docker image / apt install)
  3. imageio-ffmpeg pip package (static build, used for local dev)

`ffprobe` is optional — when it is missing we fall back to parsing
`ffmpeg -i` stderr for duration / stream information.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..config import settings


class FFmpegError(RuntimeError):
    pass


def ffmpeg_path() -> Optional[str]:
    p = os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffprobe_path() -> Optional[str]:
    return os.getenv("FFPROBE_BIN") or shutil.which("ffprobe")


def has_ffmpeg() -> bool:
    return ffmpeg_path() is not None


def _binary(which: str) -> str:
    p = ffmpeg_path() if which == "ffmpeg" else ffprobe_path()
    if not p:
        raise FFmpegError(
            f"{which} not found. Install ffmpeg (apt-get install ffmpeg) or "
            "pip install imageio-ffmpeg."
        )
    return p


def run_ffmpeg(args: list[str], timeout: int = 1200,
               label: str = "ffmpeg") -> "subprocess.CompletedProcess[str]":
    """Run ffmpeg/ffprobe with -hide_banner, raising FFmpegError on failure."""
    cmd = [_binary("ffmpeg"), "-hide_banner", "-y", *args]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"{label} timed out after {timeout}s") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-1500:]
        raise FFmpegError(f"{label} failed (exit {proc.returncode}):\n{tail}")
    return proc


# --------------------------------------------------------------------- probe
_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+.*: Audio:")
_VIDEO_RE = re.compile(r"Stream #\d+:\d+.*: Video: (\w+).*?, (\d+)x(\d+)")


def probe(path: str) -> dict:
    """Return {duration, width, height, has_audio, has_video}."""
    if not Path(path).exists():
        raise FFmpegError(f"file not found: {path}")

    if ffprobe_path():
        try:
            proc = subprocess.run(
                [ffprobe_path(), "-v", "error", "-print_format", "json",
                 "-show_format", "-show_streams", path],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0:
                import json

                data = json.loads(proc.stdout or "{}")
                streams = data.get("streams", [])
                audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
                video = next((s for s in streams if s.get("codec_type") == "video"), None)
                duration = float(data.get("format", {}).get("duration") or 0)
                if not duration and audio:
                    duration = float(audio.get("duration") or 0)
                return {
                    "duration": duration,
                    "width": int((video or {}).get("width") or 0),
                    "height": int((video or {}).get("height") or 0),
                    "has_audio": audio is not None,
                    "has_video": video is not None,
                }
        except Exception:
            pass  # fall back to ffmpeg parsing

    proc = subprocess.run(
        [_binary("ffmpeg"), "-hide_banner", "-i", path],
        capture_output=True, text=True, timeout=60,
    )
    err = proc.stderr or ""
    dur_match = _DUR_RE.search(err)
    if not dur_match:
        raise FFmpegError(f"could not read duration of {path}")
    h, m, s = dur_match.groups()
    duration = int(h) * 3600 + int(m) * 60 + float(s)
    vmatch = _VIDEO_RE.search(err)
    return {
        "duration": duration,
        "width": int(vmatch.group(2)) if vmatch else 0,
        "height": int(vmatch.group(3)) if vmatch else 0,
        "has_audio": bool(_AUDIO_RE.search(err)),
        "has_video": vmatch is not None,
    }


def audio_duration(path: str) -> float:
    return probe(path)["duration"]


# ------------------------------------------------------------------ helpers
def extract_audio(video: str, out_wav: str, sample_rate: int = 48000,
                  mono: bool = False) -> str:
    """Extract the audio track as PCM WAV."""
    channels = "1" if mono else "2"
    run_ffmpeg(
        ["-i", video, "-vn", "-acodec", "pcm_s16le",
         "-ar", str(sample_rate), "-ac", channels, out_wav],
        label="audio extraction",
    )
    return out_wav


def make_silence(out_wav: str, seconds: float, sample_rate: int = 48000,
                 channels: int = 1) -> str:
    run_ffmpeg(
        ["-f", "lavfi", "-i",
         f"anullsrc=r={sample_rate}:cl=mono" if channels == 1
         else f"anullsrc=r={sample_rate}:cl=stereo",
         "-t", f"{max(0.0, seconds):.3f}", "-acodec", "pcm_s16le", out_wav],
        label="silence generation",
    )
    return out_wav


def convert_to_pcm(in_path: str, out_wav: str, sample_rate: int = 48000,
                   channels: int = 1) -> str:
    run_ffmpeg(
        ["-i", in_path, "-vn", "-acodec", "pcm_s16le", "-ar", str(sample_rate),
         "-ac", str(channels), out_wav],
        label="pcm conversion",
    )
    return out_wav


def atempo_filter(factor: float) -> str:
    """atempo accepts 0.5–100 in modern ffmpeg; older builds need chaining."""
    factor = max(0.5, min(100.0, factor))
    if 0.5 <= factor <= 2.0:
        return f"atempo={factor:.4f}"
    parts = []
    remaining = factor
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.4f}")
    return ",".join(parts)


def stretch_audio(in_path: str, out_wav: str, factor: float) -> str:
    """Time-stretch audio by `factor` (1.25 = 25% faster/shorter)."""
    if abs(factor - 1.0) < 0.01:
        shutil.copyfile(in_path, out_wav)
        return out_wav
    run_ffmpeg(
        ["-i", in_path, "-filter:a", atempo_filter(factor),
         "-acodec", "pcm_s16le", out_wav],
        label="time-stretch",
    )
    return out_wav


def concat_wavs(paths: list[str], out_wav: str) -> str:
    """Concatenate PCM WAV files (same rate/channels) via the concat demuxer."""
    if not paths:
        raise FFmpegError("nothing to concatenate")
    list_file = str(Path(out_wav).with_suffix(".txt"))
    with open(list_file, "w", encoding="utf-8") as fh:
        for p in paths:
            fh.write(f"file '{p}'\n")
    run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", list_file,
         "-acodec", "pcm_s16le", out_wav],
        label="concat",
    )
    os.remove(list_file)
    return out_wav


def silence_regions(path: str, noise_db: float = -35.0,
                    min_silence: float = 0.35) -> list[tuple[float, float]]:
    """Detect non-silent (speech) regions using the silencedetect filter."""
    proc = subprocess.run(
        [_binary("ffmpeg"), "-hide_banner", "-i", path,
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=600,
    )
    err = proc.stderr or ""
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", err)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", err)]
    total = probe(path)["duration"]

    silences: list[tuple[float, float]] = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else total
        silences.append((s, e))

    speech: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in silences:
        if s - cursor >= min_silence:
            speech.append((cursor, s))
        cursor = max(cursor, e)
    if total - cursor >= min_silence:
        speech.append((cursor, total))
    return speech


def has_filter(name: str) -> bool:
    """Check whether the ffmpeg build supports a given filter (e.g. subtitles)."""
    p = ffmpeg_path()
    if not p:
        return False
    proc = subprocess.run([p, "-hide_banner", "-filters"],
                          capture_output=True, text=True, timeout=60)
    return re.search(rf"\s{name}\s", proc.stdout or "") is not None


def workdir(prefix: str) -> str:
    d = settings.data_dir / "tmp" / f"{prefix}_{os.getpid()}_{os.urandom(4).hex()}"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)
