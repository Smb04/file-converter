"""Single-job cancel and download endpoints with X-Accel-Redirect and optional auto-delete."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from backend.api.auth_guard import require_authenticated_user
from backend.api.deps import get_buffer, get_redis, require_batch_access
from backend.shared.buffer_manager import sanitize_filename
from backend.shared.worker_base import publish_batch_event

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_authenticated_user)],
)


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    request: Request,
    r=Depends(get_redis),
) -> dict[str, object]:
    raw = r.get(f"job:{job_id}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job nicht gefunden.")
    job = json.loads(raw)
    require_batch_access(
        request,
        job["batch_id"],
        x_batch_token=request.headers.get("x-batch-token"),
        batch_token=request.cookies.get("batch_token"),
    )

    r.setex(f"job:{job_id}:cancel", 300, "1")
    job["status"] = "cancelled"
    job["phase"] = "Abbruch angefordert"
    ttl = r.ttl(f"job:{job_id}")
    r.setex(f"job:{job_id}", ttl if ttl and ttl > 0 else 300, json.dumps(job))
    publish_batch_event(r, job["batch_id"], "job.cancelled", {"job_id": job_id, "status": "cancelled"})
    return {"job_id": job_id, "status": "cancelled"}


@router.get("/{job_id}/download")
def download_job_output(
    job_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    auto_delete: bool = Query(default=False),
    r=Depends(get_redis),
    buf=Depends(get_buffer),
) -> Response:
    raw = r.get(f"job:{job_id}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job nicht gefunden oder bereits abgelaufen.")
    job = json.loads(raw)
    batch_id = job["batch_id"]

    require_batch_access(
        request,
        batch_id,
        x_batch_token=request.headers.get("x-batch-token"),
        batch_token=request.cookies.get("batch_token"),
    )

    if job.get("status") != "completed" or not job.get("output_path"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Datei ist noch nicht fertig konvertiert.")

    out_path = Path(job["output_path"])
    if not out_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ausgabedatei nicht mehr im Buffer.")

    safe_name = sanitize_filename(job.get("output_filename") or out_path.name)
    encoded_name = quote(safe_name)
    disposition = f"attachment; filename=\"{safe_name}\"; filename*=UTF-8''{encoded_name}"

    if auto_delete:
        def _cleanup_after_send() -> None:
            buf.delete_job_output_dir(batch_id, job_id)
            r.delete(f"job:{job_id}")
            publish_batch_event(r, batch_id, "job.deleted", {"job_id": job_id})

        background_tasks.add_task(_cleanup_after_send)
        return FileResponse(
            path=str(out_path),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": disposition,
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
            background=background_tasks,
        )

    # Zero-copy Nginx X-Accel-Redirect when proxied by gateway
    if request.headers.get("x-internal-redirect") == "1":
        rel = out_path.resolve().relative_to(buf.root.resolve()).as_posix()
        return Response(
            status_code=200,
            headers={
                "X-Accel-Redirect": f"/internal-buffer/{rel}",
                "Content-Disposition": disposition,
                "Content-Type": "application/octet-stream",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    return FileResponse(
        path=str(out_path),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
