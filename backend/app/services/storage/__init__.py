"""Storage factory."""
from __future__ import annotations

from functools import lru_cache

from ...config import settings
from .base import Storage
from .local import LocalStorage


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    if settings.storage_is_s3:
        try:
            from .s3_backend import S3Storage

            print(f"[storage] S3 mode: in={settings.s3_input_bucket} "
                  f"out={settings.s3_output_bucket}")
            return S3Storage()
        except Exception as exc:
            print(f"[storage] S3 init failed ({exc}); falling back to local")
    print(f"[storage] local mode: {settings.data_dir / 'files'}")
    return LocalStorage()
