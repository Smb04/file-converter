"""Central runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    redis_url: str
    buffer_dir: Path
    job_ttl_seconds: int
    max_file_bytes: int
    max_batch_bytes: int
    buffer_high_watermark_pct: float
    buffer_reject_pct: float
    image_timeout_sec: int
    doc_timeout_sec: int
    video_timeout_sec: int
    enable_hw_accel: bool
    allowed_origins: list[str]
    gc_interval_sec: int
    chunk_size_default: int
    vaapi_device: str = "/dev/dri/renderD128"
    auth_data_dir: Path = Path("/auth-data")
    local_admin_cidrs: tuple[str, ...] = (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
    session_ttl_seconds: int = 86400
    session_remember_ttl_seconds: int = 2592000
    login_max_attempts: int = 5
    login_lockout_seconds: int = 900


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    origins_raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
    origins = [o.strip() for o in origins_raw.split(",") if o.strip()] or ["*"]
    cidrs_raw = os.getenv(
        "LOCAL_ADMIN_CIDRS",
        "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,::1/128,fc00::/7,fe80::/10",
    ).strip()
    cidrs = tuple(c.strip() for c in cidrs_raw.split(",") if c.strip())
    return Settings(
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        buffer_dir=Path(os.getenv("BUFFER_DIR", "/buffer")),
        job_ttl_seconds=int(os.getenv("JOB_TTL_SECONDS", "1200")),
        max_file_bytes=int(os.getenv("MAX_FILE_BYTES", str(500 * 1024 * 1024))),
        max_batch_bytes=int(os.getenv("MAX_BATCH_BYTES", str(1024 * 1024 * 1024))),
        buffer_high_watermark_pct=float(os.getenv("BUFFER_HIGH_WATERMARK_PCT", "80")),
        buffer_reject_pct=float(os.getenv("BUFFER_REJECT_PCT", "90")),
        image_timeout_sec=int(os.getenv("IMAGE_TIMEOUT_SEC", "30")),
        doc_timeout_sec=int(os.getenv("DOC_TIMEOUT_SEC", "60")),
        video_timeout_sec=int(os.getenv("VIDEO_TIMEOUT_SEC", "900")),
        enable_hw_accel=_env_bool("ENABLE_HW_ACCEL", False),
        allowed_origins=origins,
        gc_interval_sec=int(os.getenv("GC_INTERVAL_SEC", "60")),
        chunk_size_default=int(os.getenv("CHUNK_SIZE_BYTES", str(5 * 1024 * 1024))),
        vaapi_device=os.getenv("VAAPI_DEVICE", "/dev/dri/renderD128"),
        auth_data_dir=Path(os.getenv("AUTH_DATA_DIR", "/auth-data")),
        local_admin_cidrs=cidrs,
        session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "86400")),
        session_remember_ttl_seconds=int(os.getenv("SESSION_REMEMBER_TTL_SECONDS", "2592000")),
        login_max_attempts=int(os.getenv("LOGIN_MAX_ATTEMPTS", "5")),
        login_lockout_seconds=int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900")),
    )
