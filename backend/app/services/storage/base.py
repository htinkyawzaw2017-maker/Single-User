"""Storage abstraction — S3 in AWS mode, local data directory in dev mode."""
from __future__ import annotations

import abc
from typing import Optional


class Storage(abc.ABC):
    backend: str = "base"

    @abc.abstractmethod
    def put_bytes(self, key: str, data: bytes) -> None: ...

    @abc.abstractmethod
    def put_file(self, local_path: str, key: str) -> None: ...

    @abc.abstractmethod
    def get_bytes(self, key: str) -> bytes: ...

    @abc.abstractmethod
    def download(self, key: str, dest_path: str) -> str:
        """Ensure a local copy exists at dest_path (no-op for local backend)."""

    @abc.abstractmethod
    def local_path(self, key: str) -> Optional[str]:
        """Direct local filesystem path when available (for ffmpeg)."""

    @abc.abstractmethod
    def exists(self, key: str) -> bool: ...

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...

    @abc.abstractmethod
    def delete_prefix(self, prefix: str) -> None: ...

    @abc.abstractmethod
    def presign_put(self, key: str, content_type: str,
                    expires: int) -> dict: ...

    @abc.abstractmethod
    def presign_get(self, key: str, expires: int) -> str: ...

    @abc.abstractmethod
    def size(self, key: str) -> int: ...
