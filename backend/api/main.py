"""FastAPI entrypoint with Redis pool, lifespan, and ephemeral garbage collector."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers import batches, capabilities, jobs, uploads
from backend.shared.buffer_manager import BufferManager
from backend.shared.config import Settings, get_settings

logger = logging.getLogger("converter.api")


async def _gc_loop(app: FastAPI, settings: Settings) -> None:
    """Periodically sweep expired batches, orphaned chunk dirs, and high-watermark LRU."""
    while True:
        try:
            await asyncio.sleep(settings.gc_interval_sec)
            run_gc_cycle(app.state.redis, app.state.buffer, settings)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("GC cycle warning: %s", exc)


def run_gc_cycle(r: Any, buf: BufferManager, settings: Settings) -> dict[str, int]:
    """Execute one synchronous GC pass (also callable directly from tests)."""
    orphaned = buf.cleanup_orphaned_uploads(max_age_seconds=settings.job_ttl_seconds)
    expired_batches = 0
    evicted_lru = 0

    for batch_id, _mtime in buf.list_batch_dirs_oldest_first():
        if not r.exists(f"batch:{batch_id}"):
            buf.delete_batch_dir(batch_id)
            expired_batches += 1

    # High-watermark LRU eviction: delete oldest completed batches above 80%
    if buf.is_high_watermark():
        for batch_id, _mtime in buf.list_batch_dirs_oldest_first():
            if not buf.is_high_watermark():
                break
            raw = r.get(f"batch:{batch_id}")
            if not raw:
                buf.delete_batch_dir(batch_id)
                continue
            batch = json.loads(raw)
            job_ids = batch.get("job_ids", [])
            if not job_ids:
                continue
            all_finished = all(
                (json.loads(r.get(f"job:{jid}") or "{}").get("status") in {"completed", "failed", "cancelled"})
                for jid in job_ids
            )
            if all_finished:
                for jid in job_ids:
                    r.delete(f"job:{jid}")
                r.delete(f"batch:{batch_id}")
                buf.delete_batch_dir(batch_id)
                evicted_lru += 1

    return {"orphaned_uploads": orphaned, "expired_batches": expired_batches, "evicted_lru": evicted_lru}


def create_app(redis_client: Any = None, buffer_manager: BufferManager | None = None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.buffer = buffer_manager or BufferManager(settings)
        app.state.buffer.ensure_dirs()
        app.state.redis = redis_client or redis.Redis.from_url(settings.redis_url, decode_responses=True)
        gc_task = asyncio.create_task(_gc_loop(app, settings))
        try:
            yield
        finally:
            gc_task.cancel()
            try:
                await gc_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(
        title="Ephemeral File Converter API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(capabilities.router)
    app.include_router(batches.router)
    app.include_router(uploads.router)
    app.include_router(jobs.router)
    return app


app = create_app()
