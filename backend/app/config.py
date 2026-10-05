"""Application configuration.

All settings come from environment variables so the same code runs:
  * locally  (APP_ENV=local, SQLite + on-disk storage + mock providers)
  * on AWS   (APP_ENV=aws,  RDS PostgreSQL + S3 + real provider adapters)

Secrets (LLM/TTS API keys, DB password) can be pulled from AWS Secrets
Manager at startup when SECRETS_MANAGER_SECRET_ID is set. Keys are never
stored in frontend code.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    def __init__(self) -> None:
        # ---- general -----------------------------------------------------
        self.app_env: str = os.getenv("APP_ENV", "local")           # local | aws
        self.base_dir: Path = BACKEND_DIR
        self.data_dir: Path = Path(os.getenv("DATA_DIR", str(BACKEND_DIR / "data")))
        self.frontend_dist: str = os.getenv(
            "FRONTEND_DIST", str(BACKEND_DIR.parent / "frontend" / "dist")
        )

        # ---- database ------------------------------------------------------
        self.database_url: str = os.getenv(
            "DATABASE_URL", f"sqlite:///{self.data_dir / 'app.db'}"
        )

        # ---- storage -------------------------------------------------------
        # auto -> uses S3 when S3_INPUT_BUCKET is configured, else local disk
        self.storage_backend: str = os.getenv("STORAGE_BACKEND", "auto")  # auto|local|s3
        self.aws_region: str = os.getenv(
            "AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-southeast-1")
        )
        self.s3_input_bucket: str = os.getenv("S3_INPUT_BUCKET", "")
        self.s3_output_bucket: str = os.getenv("S3_OUTPUT_BUCKET", "") or self.s3_input_bucket
        self.s3_presign_expiry: int = int(os.getenv("S3_PRESIGN_EXPIRY", "3600"))

        # ---- provider selection ---------------------------------------------
        self.transcription_provider: str = os.getenv("TRANSCRIPTION_PROVIDER", "mock")  # mock|aws
        self.translation_provider: str = os.getenv("TRANSLATION_PROVIDER", "mock")      # mock|llm
        self.tts_provider: str = os.getenv("TTS_PROVIDER", "mock")                      # mock|http
        self.lipsync_provider: str = os.getenv("LIPSYNC_PROVIDER", "mock")              # mock|sagemaker

        # ---- LLM translation / rewrite (OpenAI-compatible API) ---------------
        self.llm_base_url: str = os.getenv("LLM_BASE_URL", "")
        self.llm_api_key: str = os.getenv("LLM_API_KEY", "")
        self.llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

        # ---- HTTP TTS provider adapter ---------------------------------------
        self.tts_http_url: str = os.getenv("TTS_HTTP_URL", "")
        self.tts_http_key: str = os.getenv("TTS_HTTP_KEY", "")
        self.tts_http_format: str = os.getenv("TTS_HTTP_FORMAT", "wav")

        # ---- SageMaker lip-sync endpoint (optional) ---------------------------
        self.lipsync_endpoint_name: str = os.getenv("LIPSYNC_ENDPOINT_NAME", "")

        # ---- AWS Secrets Manager ------------------------------------------------
        self.secrets_manager_id: str = os.getenv("SECRETS_MANAGER_SECRET_ID", "")

        # ---- single-user auth ------------------------------------------------
        self.access_key: str = os.getenv("SINGLE_USER_ACCESS_KEY", "")

        # ---- limits / tuning ---------------------------------------------------
        self.max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "2048"))
        # maximum allowed time-stretch of a generated voice (1.35 = up to 35% faster)
        self.max_speed_stretch: float = _env_float("MAX_SPEED_STRETCH", 1.35)
        self.default_bg_volume: float = _env_float("DEFAULT_BG_VOLUME", 0.15)
        self.lipsync_preview_min_s: float = _env_float("LIPSYNC_PREVIEW_MIN_S", 10.0)
        self.lipsync_preview_max_s: float = _env_float("LIPSYNC_PREVIEW_MAX_S", 30.0)

        # ---- helpers ---------------------------------------------------------
        self.demo_clip_path: str = os.getenv(
            "DEMO_CLIP_PATH", str(BACKEND_DIR / "assets" / "demo_clip.mp4")
        )
        self.font_path: str = os.getenv(
            "FONT_PATH", str(BACKEND_DIR / "assets" / "fonts" / "DejaVuSans.ttf")
        )
        self.mock_lipsync_fail: bool = _env_bool("MOCK_LIPSYNC_FAIL")

    # ---------------------------------------------------------------------
    @property
    def storage_is_s3(self) -> bool:
        if self.storage_backend == "local":
            return False
        if self.storage_backend == "s3":
            return True
        return bool(self.s3_input_bucket)

    @property
    def effective_transcription_provider(self) -> str:
        if self.transcription_provider == "aws":
            return "aws"
        return "mock"

    def load_secrets(self) -> dict:
        """Optionally merge config from AWS Secrets Manager (AWS deployment)."""
        if not (self.app_env == "aws" and self.secrets_manager_id):
            return {}
        try:
            import boto3  # guarded import

            client = boto3.client("secretsmanager", region_name=self.aws_region)
            secret = client.get_secret_value(SecretId=self.secrets_manager_id)
            data = json.loads(secret.get("SecretString", "{}"))
        except Exception as exc:  # pragma: no cover - depends on AWS creds
            print(f"[config] WARNING: could not load Secrets Manager value: {exc}")
            return {}
        # Merge known keys (never overwrite explicit env values).
        mapping = {
            "LLM_API_KEY": "llm_api_key",
            "LLM_BASE_URL": "llm_base_url",
            "TTS_HTTP_KEY": "tts_http_key",
            "TTS_HTTP_URL": "tts_http_url",
            "SINGLE_USER_ACCESS_KEY": "access_key",
        }
        for env_name, attr in mapping.items():
            if env_name in data and data[env_name] and not os.getenv(env_name):
                setattr(self, attr, str(data[env_name]))
        if "DATABASE_URL" in data and data["DATABASE_URL"] and not os.getenv("DATABASE_URL"):
            self.database_url = str(data["DATABASE_URL"])
        print(f"[config] loaded {len(data)} secret value(s) from Secrets Manager")
        return data

    def ensure_dirs(self) -> None:
        (self.data_dir / "files").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "tmp").mkdir(parents=True, exist_ok=True)

    def summary(self) -> dict:
        return {
            "app_env": self.app_env,
            "storage_backend": "s3" if self.storage_is_s3 else "local",
            "transcription_provider": self.effective_transcription_provider,
            "translation_provider": self.translation_provider,
            "tts_provider": self.tts_provider,
            "lipsync_provider": self.lipsync_provider,
        }


settings = Settings()
