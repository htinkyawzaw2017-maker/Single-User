"""SRT / VTT subtitle export (Burmese & English)."""
from __future__ import annotations


def _fmt_ts_srt(seconds: float) -> str:
    ms_total = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_ts_vtt(seconds: float) -> str:
    return _fmt_ts_srt(seconds).replace(",", ".")


def build_srt(segments: list[dict], field: str = "target_text") -> str:
    """segments: [{start,end,<field>}] -> SRT string."""
    lines = []
    for i, seg in enumerate(segments, start=1):
        text = (seg.get(field) or seg.get("target_text") or "").strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(
            f"{_fmt_ts_srt(seg['start'])} --> {_fmt_ts_srt(seg['end'])}"
        )
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def build_vtt(segments: list[dict], field: str = "target_text") -> str:
    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, start=1):
        text = (seg.get(field) or seg.get("target_text") or "").strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(
            f"{_fmt_ts_vtt(seg['start'])} --> {_fmt_ts_vtt(seg['end'])}"
        )
        lines.append(text)
        lines.append("")
    return "\n".join(lines) + "\n"
