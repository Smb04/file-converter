"""FastAPI dependencies for Redis, BufferManager, and constant-time batch authorization."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Cookie, Header, HTTPException, Request, status

from backend.shared.buffer_manager import BufferManager, verify_batch_token


def get_redis(request: Request) -> Any:
    return request.app.state.redis


def get_buffer(request: Request) -> BufferManager:
    return request.app.state.buffer


def require_batch_access(
    request: Request,
    batch_id: str,
    x_batch_token: str | None = Header(default=None),
    batch_token: str | None = Cookie(default=None),
) -> dict[str, Any]:
    r = get_redis(request)
    raw = r.get(f"batch:{batch_id}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch nicht gefunden oder bereits abgelaufen.")

    batch = json.loads(raw)
    provided = x_batch_token or batch_token or request.query_params.get("token")
    if not verify_batch_token(batch.get("token"), provided):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ungueltiges oder fehlendes Batch-Token.")

    return batch
