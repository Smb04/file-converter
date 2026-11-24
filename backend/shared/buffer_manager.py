"""Ephemeral buffer manager, UUID path isolation, sanitization, and token security."""

from __future__ import annotations

import hmac
import os
import re
import secrets
import shutil
import time
from pathlib import Path

from backend.shared.config import Settings, get_settings

_SAFE_CHAR_RE = re.compile(r"[^A-Za-z0-9._\-() ]+")


def sanitize_filename(filename: str, fallback: str = "file") -> str:
    """Strip directory traversal, null bytes, and control characters from a display filename."""
    cleaned = filename.replace("\x00", "").replace("\\", "/")
    base = cleaned.rsplit("/", 1)[-1].strip().lstrip(".")
    base = _SAFE_CHAR_RE.sub("_", base).strip()
    if not base:
        return fallback
    # Limit filename length while preserving extension
    if len(base) > 120:
        stem, dot, ext = base.rpartition(".")
        if dot and len(ext) <= 12:
            base = f"{stem[:105]}.{ext}"
        else:
            base = base[:120]
    return base


def generate_batch_token() -> str:
    return secrets.token_urlsafe(32)


def verify_batch_token(expected: str | None, provided: str | None) -> bool:
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))


class BufferManager:
    """Manages short-lived batch and chunk upload directories under /buffer."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.buffer_dir
        self.batches_dir = self.root / "batches"
        self.uploads_dir = self.root / "uploads"

    def ensure_dirs(self) -> None:
        self.batches_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def get_buffer_usage_pct(self) -> float:
        self.ensure_dirs()
        usage = shutil.disk_usage(self.root)
        if usage.total <= 0:
            return 0.0
        return round((usage.used / usage.total) * 100.0, 2)

    def is_high_watermark(self) -> bool:
        return self.get_buffer_usage_pct() >= self.settings.buffer_high_watermark_pct

    def is_reject_threshold(self) -> bool:
        return self.get_buffer_usage_pct() >= self.settings.buffer_reject_pct

    def batch_dir(self, batch_id: str) -> Path:
        return self.batches_dir / self._validate_uuid_segment(batch_id)

    def batch_input_path(self, batch_id: str, file_id: str) -> Path:
        bdir = self.batch_dir(batch_id) / "in"
        bdir.mkdir(parents=True, exist_ok=True)
        return bdir / f"{self._validate_uuid_segment(file_id)}.bin"

    def job_output_dir(self, batch_id: str, job_id: str) -> Path:
        odir = self.batch_dir(batch_id) / "out" / self._validate_uuid_segment(job_id)
        odir.mkdir(parents=True, exist_ok=True)
        return odir

    def upload_dir(self, upload_id: str) -> Path:
        udir = self.uploads_dir / self._validate_uuid_segment(upload_id)
        udir.mkdir(parents=True, exist_ok=True)
        return udir

    def delete_batch_dir(self, batch_id: str) -> None:
        target = self.batch_dir(batch_id)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

    def delete_upload_dir(self, upload_id: str) -> None:
        target = self.uploads_dir / self._validate_uuid_segment(upload_id)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

    def delete_job_output_dir(self, batch_id: str, job_id: str) -> None:
        target = self.batch_dir(batch_id) / "out" / self._validate_uuid_segment(job_id)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

    def cleanup_orphaned_uploads(self, max_age_seconds: int = 1800) -> int:
        self.ensure_dirs()
        now = time.time()
        removed = 0
        for item in self.uploads_dir.iterdir():
            if not item.is_dir():
                continue
            try:
                if (now - item.stat().st_mtime) > max_age_seconds:
                    shutil.rmtree(item, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        return removed

    def list_batch_dirs_oldest_first(self) -> list[tuple[str, float]]:
        self.ensure_dirs()
        entries: list[tuple[str, float]] = []
        for item in self.batches_dir.iterdir():
            if item.is_dir():
                try:
                    entries.append((item.name, item.stat().st_mtime))
                except OSError:
                    continue
        entries.sort(key=lambda pair: pair[1])
        return entries

    @staticmethod
    def _validate_uuid_segment(segment: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", segment):
            raise ValueError(f"Invalid identifier segment: {segment!r}")
        return segment
