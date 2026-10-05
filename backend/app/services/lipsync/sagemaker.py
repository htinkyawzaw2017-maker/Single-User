"""SageMaker asynchronous lip-sync endpoint adapter (production path).

Deploy a GPU model (e.g. Wav2Lip) as an Async Inference endpoint, then set:

  LIPSYNC_PROVIDER=sagemaker
  LIPSYNC_ENDPOINT_NAME=my-wav2lip-endpoint

Expected payload: {"video_s3_uri": ..., "audio_s3_uri": ..., "start": ...,
"end": ...}; the endpoint writes the lip-synced result back to S3 and this
adapter downloads it. All AWS credentials come from the task role — no keys
in code.
"""
from __future__ import annotations

import time

from ...config import settings
from ..storage import get_storage
from . import FaceQualityError, LipSyncError


class SageMakerLipSync:
    provider = "sagemaker"

    def __init__(self) -> None:
        import boto3  # lazy

        self.client = boto3.client("sagemaker-runtime", region_name=settings.aws_region)
        self.sm = boto3.client("sagemaker", region_name=settings.aws_region)
        self.storage = get_storage()

    def check_face(self, video_path: str, start: float, end: float) -> dict:
        """Ask the endpoint's /check route (or a lightweight face detector)."""
        try:
            import boto3 as b

            rek = b.client("rekognition", region_name=settings.aws_region)
            with open(video_path, "rb") as fh:
                # sample a frame in the middle of the window via ffmpeg
                from .. import ffmpeg_env

                import subprocess, tempfile, os

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as jf:
                    jpg = jf.name
                subprocess.run(
                    [ffmpeg_env.ffmpeg_path(), "-y", "-ss",
                     f"{(start + end) / 2:.2f}", "-i", video_path,
                     "-frames:v", "1", "-q:v", "3", jpg],
                    capture_output=True, timeout=60,
                )
                with open(jpg, "rb") as fh:
                    faces = rek.detect_faces(Image={"Bytes": fh.read()},
                                             Attributes=["POSE"])["FaceDetails"]
                os.unlink(jpg)
            if not faces:
                raise FaceQualityError("No face detected in the clip window.")
            if len(faces) > 1:
                raise FaceQualityError(
                    f"{len(faces)} faces detected — MVP lip-sync supports one "
                    "main front-facing speaker only."
                )
            pose = faces[0]["Pose"]
            yaw, pitch = abs(pose["Yaw"]), abs(pose["Pitch"])
            if yaw > 35 or pitch > 25:
                raise FaceQualityError(
                    f"Face angle too extreme (yaw={yaw:.0f}°, pitch={pitch:.0f}°). "
                    "Use a more front-facing shot."
                )
            return {"quality": "good", "message": "Front-facing single face detected."}
        except FaceQualityError:
            raise
        except Exception as exc:
            return {"quality": "warning", f"message": f"Face check skipped: {exc}"}

    def render_preview(self, video_path: str, start: float, end: float,
                       dubbed_audio_path: str, out_path: str) -> str:
        video_key = f"lipsync/jobs/{int(time.time())}_in.mp4"
        audio_key = f"lipsync/jobs/{int(time.time())}_in.wav"
        self.storage.put_file(video_path, video_key)
        self.storage.put_file(dubbed_audio_path, audio_key)
        payload = {
            "video_s3_key": video_key,
            "audio_s3_key": audio_key,
            "start": start,
            "end": end,
        }
        resp = self.client.invoke_endpoint_async(
            EndpointName=settings.lipsync_endpoint_name,
            InputLocation="s3://placeholder",  # replaced by real deployment
            ContentType="application/json",
        )
        output_location = resp.get("OutputLocation", "")
        if not output_location:
            raise LipSyncError("Async endpoint did not return an output location")
        # poll + download omitted for brevity — wired in production deploy
        raise LipSyncError(
            "SageMaker lip-sync adapter is a reference stub — wire the polling "
            "and result download to your endpoint contract, or use mock provider."
        )
