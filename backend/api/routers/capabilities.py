"""Healthcheck and format capabilities endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.api.deps import get_buffer, get_redis
from backend.shared.config import get_settings
from backend.shared.conversion_graph import export_capabilities

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    r = get_redis(request)
    buf = get_buffer(request)
    redis_ok = False
    try:
        redis_ok = bool(r.ping())
    except Exception:
        redis_ok = False

    usage_pct = buf.get_buffer_usage_pct()
    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": redis_ok,
        "buffer_usage_pct": usage_pct,
        "workers": {
            "media": bool(r.exists("worker:heartbeat:media")) if redis_ok else False,
            "docs": bool(r.exists("worker:heartbeat:docs")) if redis_ok else False,
        },
    }


@router.get("/capabilities")
def capabilities() -> dict[str, object]:
    settings = get_settings()
    return export_capabilities(
        {
            "max_file_bytes": settings.max_file_bytes,
            "max_batch_bytes": settings.max_batch_bytes,
            "ttl_seconds": settings.job_ttl_seconds,
            "chunk_size_default": settings.chunk_size_default,
            "hw_accel_enabled": settings.enable_hw_accel,
        }
    )
