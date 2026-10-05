"""Final composition: video rendering, watermark, burned-in subtitles,
dual-audio exports."""
from __future__ import annotations

import os
from pathlib import Path

from ..config import settings
from . import ffmpeg_env


class RenderError(RuntimeError):
    pass


def render_video(video_path: str, audio_path: str, out_path: str, *,
                 height: int | None = None,
                 watermark: bool = False,
                 burn_srt: str | None = None,
                 extra_audio: str | None = None,
                 label: str = "render",
                 notes: list[str] | None = None) -> str:
    """Compose final MP4.

    * height: scale output (e.g. 720 for preview). None keeps source size.
    * watermark: draws a "PREVIEW" watermark (preview exports only).
    * burn_srt: path to an .srt file burned into the picture (needs libass).
    * extra_audio: adds the original audio as a second selectable track.
    """
    notes = notes if notes is not None else []
    args: list[str] = ["-i", video_path, "-i", audio_path]
    if extra_audio:
        args += ["-i", extra_audio]

    vf_parts: list[str] = []
    if height:
        vf_parts.append(f"scale=-2:'min({height},ih)'")
    if watermark:
        if ffmpeg_env.has_filter("drawtext"):
            font = settings.font_path
            if font and Path(font).exists():
                vf_parts.append(
                    "drawtext=fontfile='" + font.replace(":", r"\:")
                    + "':text='PREVIEW':fontcolor=white@0.6:fontsize=h/24:"
                      "x=(w-text_w)/2:y=(h-text_h)*0.92"
                )
            else:
                notes.append(
                    "watermark skipped: no font file found at FONT_PATH"
                )
        else:
            notes.append(
                "watermark skipped: ffmpeg build has no drawtext filter "
                "(production Docker image includes it)"
            )
    if burn_srt:
        if not ffmpeg_env.has_filter("subtitles"):
            raise RenderError(
                "This ffmpeg build has no libass 'subtitles' filter — use the "
                "SRT/VTT sidecar files or an ffmpeg built with libass."
            )
        safe = burn_srt.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        vf_parts.append(f"subtitles='{safe}'")

    if vf_parts:
        args += ["-vf", ",".join(vf_parts)]

    # streams: video from input 0, main audio (dubbed mix) from input 1,
    # optional original audio from input 2
    args += ["-map", "0:v:0", "-map", "1:a:0"]
    if extra_audio:
        args += ["-map", "2:a:0", "-c:a:1", "aac", "-b:a:2", "192k",
                 "-metadata:s:a:1", "title=Original audio",
                 "-disposition:a:0", "default", "-disposition:a:1", "none"]

    args += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        out_path,
    ]
    ffmpeg_env.run_ffmpeg(args, label=label, timeout=3600)
    return out_path


def export_audio(mixed_wav: str, out_path: str, fmt: str = "mp3") -> str:
    codec = {"mp3": "libmp3lame", "wav": "pcm_s16le", "aac": "aac"}.get(fmt, "libmp3lame")
    args = ["-i", mixed_wav, "-acodec", codec]
    if fmt == "wav":
        args += ["-ar", "48000"]
    else:
        args += ["-b:a", "192k"]
    args.append(out_path)
    ffmpeg_env.run_ffmpeg(args, label=f"audio export ({fmt})")
    return out_path
