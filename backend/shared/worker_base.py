"""Shared Redis queue consumer, subprocess runner with kill-group, and event publisher."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

import redis

from backend.shared.config import get_settings
from backend.shared.models import JobPayload


class WorkerCancelledError(RuntimeError):
    """Raised when a job is cancelled by the user."""


def publish_batch_event(r: redis.Redis, batch_id: str, event: str, data: dict) -> None:
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    r.publish(f"batch:{batch_id}:events", payload)


def update_job_record(r: redis.Redis, job_id: str, **updates: object) -> dict:
    key = f"job:{job_id}"
    raw = r.get(key)
    record = json.loads(raw) if raw else {"job_id": job_id}
    record.update(updates)
    ttl = r.ttl(key)
    if ttl and ttl > 0:
        r.setex(key, ttl, json.dumps(record, ensure_ascii=False))
    else:
        r.setex(key, get_settings().job_ttl_seconds, json.dumps(record, ensure_ascii=False))
    return record


def is_job_cancelled(r: redis.Redis, job_id: str) -> bool:
    return bool(r.exists(f"job:{job_id}:cancel"))


def run_subprocess_guarded(
    cmd: list[str],
    r: redis.Redis,
    job_id: str,
    timeout_sec: int,
    on_stdout_line: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """Run subprocess in its own process group with timeout and Redis cancel polling."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )

    stderr_chunks: list[str] = []

    def _drain_stderr() -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            stderr_chunks.append(line)

    def _drain_stdout() -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            if on_stdout_line is not None:
                on_stdout_line(line.rstrip("\r\n"))

    t_err = threading.Thread(target=_drain_stderr, daemon=True)
    t_out = threading.Thread(target=_drain_stdout, daemon=True)
    t_err.start()
    t_out.start()

    deadline = time.monotonic() + timeout_sec
    cancelled = False
    timed_out = False

    while proc.poll() is None:
        if is_job_cancelled(r, job_id):
            cancelled = True
            _terminate_process_group(proc)
            break
        if time.monotonic() > deadline:
            timed_out = True
            _terminate_process_group(proc)
            break
        time.sleep(0.25)

    t_err.join(timeout=2)
    t_out.join(timeout=2)

    if cancelled:
        raise WorkerCancelledError("Konvertierung durch Nutzer abgebrochen.")
    if timed_out:
        raise TimeoutError(f"Zeitlimit von {timeout_sec} Sekunden ueberschritten.")

    return proc.returncode or 0, "".join(stderr_chunks)[-2000:]


def _terminate_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except OSError:
            pass


def run_worker_loop(
    worker_name: str,
    queue_name: str,
    handler: Callable[[redis.Redis, JobPayload, dict], tuple[Path, bool, int | None]],
) -> None:
    """Blocking queue loop for media/docs workers."""
    settings = get_settings()
    r = redis.Redis.from_url(settings.redis_url, decode_responses=True)

    stop_event = threading.Event()

    def _heartbeat() -> None:
        while not stop_event.is_set():
            try:
                r.setex(f"worker:heartbeat:{worker_name}", 45, str(int(time.time())))
            except Exception:
                pass
            stop_event.wait(15)

    hb_thread = threading.Thread(target=_heartbeat, daemon=True)
    hb_thread.start()

    while not stop_event.is_set():
        try:
            item = r.brpop(queue_name, timeout=5)
        except redis.RedisError:
            time.sleep(2)
            continue

        if not item:
            continue

        _, raw_payload = item
        payload = JobPayload.model_validate_json(raw_payload)
        step = payload.pipeline[payload.step_index]
        step_pct_start = int((payload.step_index / max(1, len(payload.pipeline))) * 100)

        if is_job_cancelled(r, payload.job_id):
            update_job_record(r, payload.job_id, status="cancelled", phase="Abgebrochen")
            publish_batch_event(r, payload.batch_id, "job.cancelled", {"job_id": payload.job_id})
            continue

        update_job_record(
            r,
            payload.job_id,
            status="running",
            progress=max(5, step_pct_start),
            phase=f"Verarbeite ({step['engine']})",
        )
        publish_batch_event(
            r,
            payload.batch_id,
            "job.progress",
            {
                "job_id": payload.job_id,
                "status": "running",
                "progress": max(5, step_pct_start),
                "phase": f"Starte {step['dst'].upper()}-Erstellung",
            },
        )

        try:
            output_path, is_archive, page_count = handler(r, payload, step)

            # Multi-hop: hand off to next step if pipeline has remaining edges
            if payload.step_index + 1 < len(payload.pipeline):
                next_payload = payload.model_copy(
                    update={
                        "step_index": payload.step_index + 1,
                        "current_input_path": str(output_path),
                    }
                )
                next_worker = next_payload.pipeline[next_payload.step_index]["worker"]
                r.lpush(f"queue:{next_worker}", next_payload.model_dump_json())
                continue

            out_size = output_path.stat().st_size if output_path.exists() else 0
            orig_stem = Path(payload.original_filename).stem or "converted"
            out_ext = "zip" if is_archive else payload.target_format
            download_name = f"{orig_stem}.{out_ext}"

            update_job_record(
                r,
                payload.job_id,
                status="completed",
                progress=100,
                phase="Fertig",
                output_path=str(output_path),
                output_filename=download_name,
                output_size=out_size,
                is_archive=is_archive,
                page_count=page_count,
            )
            publish_batch_event(
                r,
                payload.batch_id,
                "job.completed",
                {
                    "job_id": payload.job_id,
                    "status": "completed",
                    "progress": 100,
                    "phase": "Fertig",
                    "output_filename": download_name,
                    "output_size": out_size,
                    "is_archive": is_archive,
                    "page_count": page_count,
                },
            )
        except WorkerCancelledError:
            update_job_record(r, payload.job_id, status="cancelled", phase="Abgebrochen")
            publish_batch_event(r, payload.batch_id, "job.cancelled", {"job_id": payload.job_id})
        except Exception as exc:
            msg = _friendly_error(exc)
            update_job_record(r, payload.job_id, status="failed", phase="Fehlgeschlagen", error_message=msg)
            publish_batch_event(
                r,
                payload.batch_id,
                "job.failed",
                {
                    "job_id": payload.job_id,
                    "status": "failed",
                    "phase": "Fehlgeschlagen",
                    "error_message": msg,
                },
            )


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if "password" in low or "encrypted" in low:
        return "Diese Datei ist passwortgeschuetzt oder verschluesselt und kann nicht verarbeitet werden."
    if isinstance(exc, TimeoutError):
        return "Die Verarbeitung hat das Zeitlimit ueberschritten. Bitte Datei verkleinern oder erneut versuchen."
    if len(text) > 220:
        return text[:220] + "..."
    return text or "Unbekannter Verarbeitungsfehler."
