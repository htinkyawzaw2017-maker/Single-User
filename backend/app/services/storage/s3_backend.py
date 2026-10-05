"""Amazon S3 storage (AWS deployment mode).

  * uploads/*  -> INPUT bucket  (user's source videos)
  * everything else -> OUTPUT bucket (audio, exports, renders)

boto3 is imported lazily so local development never needs AWS credentials.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...config import settings
from .base import Storage


class S3Storage(Storage):
    backend = "s3"

    def __init__(self) -> None:
        import boto3  # lazy import

        self.region = settings.aws_region
        self.client = boto3.client("s3", region_name=self.region)
        self.input_bucket = settings.s3_input_bucket
        self.output_bucket = settings.s3_output_bucket

    # ------------------------------------------------------------- helpers
    def _bucket(self, key: str) -> str:
        return self.input_bucket if key.startswith("uploads/") else self.output_bucket

    # --------------------------------------------------------------- impl
    def put_bytes(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self._bucket(key), Key=key, Body=data)

    def put_file(self, local_path: str, key: str) -> None:
        self.client.upload_file(local_path, self._bucket(key), key)

    def get_bytes(self, key: str) -> bytes:
        resp = self.client.get_object(Bucket=self._bucket(key), Key=key)
        return resp["Body"].read()

    def download(self, key: str, dest_path: str) -> str:
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self._bucket(key), key, dest_path)
        return dest_path

    def local_path(self, key: str) -> Optional[str]:
        # S3 objects are streamed to a temp file on demand (see download())
        cached = Path(settings.data_dir / "tmp" / "s3cache" / key)
        if cached.exists():
            return str(cached)
        return None

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self._bucket(key), Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self._bucket(key), Key=key)

    def delete_prefix(self, prefix: str) -> None:
        bucket = self._bucket(prefix)
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(
                    Bucket=bucket, Delete={"Objects": objects}
                )

    def size(self, key: str) -> int:
        resp = self.client.head_object(Bucket=self._bucket(key), Key=key)
        return int(resp.get("ContentLength", 0))

    # ----------------------------------------------------------- presign
    def presign_put(self, key: str, content_type: str, expires: int) -> dict:
        url = self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket(key),
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires,
        )
        return {
            "mode": "s3",
            "url": url,
            "method": "PUT",
            "key": key,
            "headers": {"Content-Type": content_type},
            "expires_in": expires,
        }

    def presign_get(self, key: str, expires: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket(key), "Key": key},
            ExpiresIn=expires,
        )
