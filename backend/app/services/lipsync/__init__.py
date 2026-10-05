"""Lip-sync provider factory.

Lip-sync is an isolated, optional beta feature:
  * runs only when the project mode is `dialogue_lipsync`
  * validates face suitability before processing
  * produces a short 10–30s preview first
  * fails gracefully — audio-only dubbing always remains available
"""
from __future__ import annotations

from ...config import settings


class LipSyncError(RuntimeError):
    pass


class FaceQualityError(LipSyncError):
    """Face not suitable for lip-sync (side-facing, occluded, multiple faces)."""


def get_lipsync():
    if settings.lipsync_provider == "sagemaker" and settings.lipsync_endpoint_name:
        from .sagemaker import SageMakerLipSync

        return SageMakerLipSync()
    from .mock import MockLipSync

    return MockLipSync()
