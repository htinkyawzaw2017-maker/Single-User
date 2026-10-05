"""Amazon Transcribe provider (opt-in, for AWS deployments).

Set TRANSCRIPTION_PROVIDER=aws. The source audio is uploaded to the output
bucket, a transcription job is started, polled, and its items are grouped
back into timestamped segments.

Burmese (my) is supported by Amazon Transcribe as of 2024+; English obviously
is. When the language is unsupported or the job fails the caller sees a clear
error and can retry.
"""
from __future__ import annotations

import time
import uuid

from ...config import settings
from ..storage import get_storage
from . import SegmentDraft


class AwsTranscriber:
    provider = "aws"

    LANGUAGE_CODES = {"en": "en-US", "my": "my"}  # Burmese if account supports

    def transcribe(self, audio_path: str, language: str,
                   hint: str = "") -> list[SegmentDraft]:
        import boto3

        client = boto3.client("transcribe", region_name=settings.aws_region)
        storage = get_storage()
        if storage.backend != "s3":
            raise RuntimeError("AWS Transcribe requires S3 storage backend")

        key = f"transcribe/{uuid.uuid4().hex}.wav"
        storage.put_file(audio_path, key)
        media_uri = storage.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": storage._bucket(key), "Key": key},
            ExpiresIn=3600,
        )

        job_name = f"sdm-{uuid.uuid4().hex[:12]}"
        client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": media_uri},
            MediaFormat="wav",
            LanguageCode=self.LANGUAGE_CODES.get(language, "en-US"),
            Settings={"ShowSpeakerLabels": True, "MaxSpeakerLabels": 2},
        )

        # poll (single-user MVP: synchronous polling is acceptable)
        deadline = time.time() + 900
        while time.time() < deadline:
            job = client.get_transcription_job(TranscriptionJobName=job_name)
            status = job["TranscriptionJob"]["TranscriptionJobStatus"]
            if status == "COMPLETED":
                break
            if status == "FAILED":
                raise RuntimeError(
                    f"Transcribe job failed: {job['TranscriptionJob'].get('FailureReason')}"
                )
            time.sleep(5)
        else:
            raise RuntimeError("Transcribe job timed out")

        import httpx

        url = job["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
        data = httpx.get(url, timeout=60).json()

        drafts: list[SegmentDraft] = []
        current: dict | None = None
        for item in data.get("results", {}).get("items", []):
            if item["type"] not in ("pronunciation",):
                continue
            start, end = float(item["start_time"]), float(item["end_time"])
            if current and start - current["end"] < 0.8:
                current["end"] = end
                current["text"] += item["alternatives"][0]["content"] + " "
            else:
                if current:
                    drafts.append(SegmentDraft(**current))
                current = {
                    "start": start,
                    "end": end,
                    "text": item["alternatives"][0]["content"] + " ",
                    "speaker": "SPEAKER_00",
                    "extra": {"provider": "aws"},
                }
        if current:
            drafts.append(SegmentDraft(**current))

        # apply speaker labels when present
        segs = data.get("results", {}).get("speaker_labels", {}).get("segments", [])
        if segs:
            for i, draft in enumerate(drafts):
                label = "SPEAKER_00"
                for seg in segs:
                    if float(seg["start_time"]) <= draft.start <= float(seg["end_time"]):
                        items = seg.get("items", [])
                        if items:
                            label = items[0].get("speaker_label", label)
                        break
                draft.speaker = label

        for d in drafts:
            d.text = d.text.strip()
            d.start, d.end = round(d.start, 3), round(d.end, 3)
        try:
            storage.delete(key)
        except Exception:
            pass
        return drafts
