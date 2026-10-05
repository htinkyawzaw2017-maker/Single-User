"""Local filesystem storage (development mode).

Files live under DATA_DIR/files/<key> — mirrors the S3 key layout so switching
to S3 for AWS deployment changes nothing else in the codebase.
"""
from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Optional

from ...config import settings
from .base import Storage

# in-memory registry of one-time upload tokens (single-user app)
_UPLOAD_TOKENS: dict[str, tuple[str, float]] = {}


class LocalStorage(Storage):
    backend = "local"

    def __init__(self) -> None:
        self.root = settings.data_dir / "files"
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- helpers
    def _path(self, key: str) -> Path:
        key = key.lstrip("/").replace("..", "_")
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError(f"illegal storage key: {key}")
        return p

    # --------------------------------------------------------------- impl
    def put_bytes(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def put_file(self, local_path: str, key: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(Path(local_path).read_bytes())

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def download(self, key: str, dest_path: str) -> str:
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        if Path(dest_path).resolve() != self._path(key).resolve():
            Path(dest_path).write_bytes(self.get_bytes(key))
        return dest_path

    def local_path(self, key: str) -> Optional[str]:
        p = self._path(key)
        return str(p) if p.exists() else None

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def delete_prefix(self, prefix: str) -> None:
        base = self._path(prefix.rstrip("/") + "/")
        if base.exists():
            import shutil

            shutil.rmtree(base, ignore_errors=True)

    def size(self, key: str) -> int:
        p = self._path(key)
        return p.stat().st_size if p.exists() else 0

    # ----------------------------------------------------------- presign
    def presign_put(self, key: str, content_type: str, expires: int) -> dict:
        token = secrets.token_urlsafe(24)
        _UPLOAD_TOKENS[token] = (key, time.time() + expires)
        # purge expired tokens
        now = time.time()
        for t in [t for t, (_, exp) in _UPLOAD_TOKENS.items() if exp < now]:
            _UPLOAD_TOKENS.pop(t, None)
        return {
            "mode": "local",
            "url": f"/api/uploads/put/{token}",
            "method": "PUT",
            "key": key,
            "headers": {"Content-Type": content_type},
            "expires_in": expires,
        }

    @staticmethod
    def consume_token(token: str) -> Optional[str]:
        entry = _UPLOAD_TOKENS.pop(token, None)
        if not entry:
            return None
        key, expires = entry
        return key if time.time() <= expires else None

    def presign_get(self, key: str, expires: int) -> str:
        return f"/api/storage/{key}"
