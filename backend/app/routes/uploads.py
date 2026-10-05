"""Upload endpoints — presigned URL flow.

Local mode: the browser PUTs the raw file bytes to this backend, which writes
them into the storage layer (same key layout as S3).
AWS mode:  the presigned URL points straight at S3, so this endpoint is unused.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from ..services.storage import get_storage
from ..services.storage.local import LocalStorage

router = APIRouter(tags=["uploads"])

CHUNK = 1024 * 512


@router.put("/api/uploads/put/{token}")
async def direct_upload(token: str, request: Request):
    key = LocalStorage.consume_token(token)
    if not key:
        raise HTTPException(400, "upload token invalid or expired")
    storage = get_storage()
    if storage.backend != "local":
        raise HTTPException(409, "direct upload only available in local mode")
    path = storage._path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(path, "wb") as fh:
        async for chunk in request.stream():
            if chunk:
                fh.write(chunk)
                size += len(chunk)
    if size == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "empty upload body")
    return {"key": key, "size": size}
