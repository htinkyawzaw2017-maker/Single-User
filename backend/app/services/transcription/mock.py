"""Mock / offline transcription.

Uses ffmpeg silencedetect to find real speech windows in the extracted audio,
then produces timestamped segments with placeholder text. The user edits all
text in the review editor anyway — this keeps the tool fully functional
offline while Amazon Transcribe (see aws_transcribe.py) is an opt-in provider
for AWS deployments.
"""
from __future__ import annotations

from .. import ffmpeg_env
from . import SegmentDraft

_PLACEHOLDER = {
    "en": "Original dialogue — edit this mock transcript line.",
    "my": "မူရင်းစကားပိုဒ် — mock transcript ကို ဖြည့်စွက်တည်းဖြတ်ပါ။",
}


class MockTranscriber:
    provider = "mock"

    def transcribe(self, audio_path: str, language: str,
                   hint: str = "") -> list[SegmentDraft]:
        try:
            regions = ffmpeg_env.silence_regions(audio_path)
        except Exception:
            regions = []

        if not regions:
            # no audio / nothing detected: synthesize a plausible timeline
            try:
                duration = ffmpeg_env.probe(audio_path)["duration"] or 60.0
            except Exception:
                duration = 60.0
            step = 6.0
            regions = [
                (i * step, min((i + 1) * step - 0.5, duration))
                for i in range(max(1, int(duration // step)))
            ]

        drafts: list[SegmentDraft] = []
        speaker = "SPEAKER_00"
        last_end = 0.0
        for i, (start, end) in enumerate(regions[:400]):
            # simple speaker diarization heuristic: long gaps imply turn changes
            if start - last_end > 1.6:
                speaker = "SPEAKER_01" if speaker == "SPEAKER_00" else "SPEAKER_00"
            last_end = end
            drafts.append(
                SegmentDraft(
                    start=round(start, 3),
                    end=round(end, 3),
                    text=_PLACEHOLDER.get(language, _PLACEHOLDER["en"]),
                    speaker=speaker,
                    confidence=0.60,
                    extra={"provider": "mock"},
                )
            )
        return drafts
