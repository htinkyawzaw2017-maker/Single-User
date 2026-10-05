"""Project / job state machine.

    CREATED
      ↓ (video uploaded)
    UPLOADED
      ↓ validate
    EXTRACTING_AUDIO
      ↓
    TRANSCRIBING
      ↓
    TRANSLATING
      ↓
    AWAITING_USER_REVIEW          ← user edits transcript / translation
      ↓
    GENERATING_VOICE
      ↓
    ALIGNING_TIMING
      ↓
    AWAITING_VOICE_APPROVAL       ← user reviews voices, adjusts speed
      ↓
    LIP_SYNCING (only when enabled)
      ↓
    RENDERING
      ↓
    COMPLETED

Any running state may go to FAILED (retryable) or CANCELLED.
The pipeline never restarts the whole project for one bad segment —
segments are regenerated individually.
"""
from __future__ import annotations

CREATED = "CREATED"
UPLOADED = "UPLOADED"
EXTRACTING_AUDIO = "EXTRACTING_AUDIO"
TRANSCRIBING = "TRANSCRIBING"
TRANSLATING = "TRANSLATING"
AWAITING_USER_REVIEW = "AWAITING_USER_REVIEW"
GENERATING_VOICE = "GENERATING_VOICE"
ALIGNING_TIMING = "ALIGNING_TIMING"
AWAITING_VOICE_APPROVAL = "AWAITING_VOICE_APPROVAL"
LIP_SYNCING = "LIP_SYNCING"
RENDERING = "RENDERING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"

ALL_STATUSES = [
    CREATED, UPLOADED, EXTRACTING_AUDIO, TRANSCRIBING, TRANSLATING,
    AWAITING_USER_REVIEW, GENERATING_VOICE, ALIGNING_TIMING,
    AWAITING_VOICE_APPROVAL, LIP_SYNCING, RENDERING, COMPLETED,
    FAILED, CANCELLED,
]

RUNNING_STATUSES = {
    UPLOADED, EXTRACTING_AUDIO, TRANSCRIBING, TRANSLATING,
    GENERATING_VOICE, ALIGNING_TIMING, LIP_SYNCING, RENDERING,
}

# Pipeline steps in execution order. Each step maps to a Job row and to the
# project status used while the step is running.
PIPELINE_STEPS = [
    ("validate", UPLOADED),
    ("extract_audio", EXTRACTING_AUDIO),
    ("transcribe", TRANSCRIBING),
    ("translate", TRANSLATING),
    ("generate_voice", GENERATING_VOICE),
    ("align_timing", ALIGNING_TIMING),
    ("lip_sync", LIP_SYNCING),
    ("render", RENDERING),
]
STEP_ORDER = [s for s, _ in PIPELINE_STEPS]
STEP_RUNNING_STATUS = dict(PIPELINE_STEPS)

# Steps the pipeline runs automatically right after upload
AUTO_STEPS = ["validate", "extract_audio", "transcribe", "translate"]

# Human readable labels (used by the frontend too)
STEP_LABELS = {
    "validate": "Validate input",
    "extract_audio": "Extract audio",
    "transcribe": "Transcribe",
    "translate": "Translate / rewrite",
    "generate_voice": "Generate voice",
    "align_timing": "Align timing",
    "lip_sync": "Lip-sync",
    "render": "Render output",
}


class StepPause(Exception):
    """Raised when the pipeline reaches a user-review checkpoint."""

    def __init__(self, status: str, message: str = ""):
        super().__init__(message or status)
        self.status = status
        self.message = message


class StepCancelled(Exception):
    """Raised when the user cancels the project mid-pipeline."""


def user_page_for_status(status: str, mode: str) -> str:
    """Which frontend page to show for a given project status."""
    if status in (CREATED,):
        return "setup"
    if status in (AWAITING_USER_REVIEW,):
        return "editor"
    if status in (GENERATING_VOICE, ALIGNING_TIMING):
        return "processing"
    if status == AWAITING_VOICE_APPROVAL:
        return "voice"
    if status == LIP_SYNCING:
        return "lipsync" if mode == "dialogue_lipsync" else "processing"
    if status == COMPLETED:
        return "export"
    return "processing"
