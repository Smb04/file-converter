"""Batch lifecycle, conversion dispatch, SSE streaming, streaming ZIP, and instant purge."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from zipstream import ZipStream

from backend.api.deps import get_buffer, get_redis, require_batch_access
from backend.shared.buffer_manager import generate_batch_token, sanitize_filename
from backend.shared.config import get_settings
from backend.shared.conversion_graph import find_conversion_path
from backend.shared.formats import ALREADY_COMPRESSED_FORMATS, normalize_format
from backend.shared.models import (
    BatchCreateResponse,
    ConvertRequest,
    ConvertResponse,
    JobPayload,
    JobSummary,
)

router = APIRouter(prefix="/api/v1/batches", tags=["batches"])


@router.post("", response_model=BatchCreateResponse, status_code=status.HTTP_201_CREATED)
def create_batch(response: Response, r=Depends(get_redis), buf=Depends(get_buffer)) -> BatchCreateResponse:
    settings = get_settings()
    if buf.is_reject_threshold():
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="Buffer-Speicher voll. Bitte einen Moment warten.",
            headers={"Retry-After": "30"},
        )

    batch_id = uuid.uuid4().hex
    token = generate_batch_token()
    now = time.time()
    expires_at = now + settings.job_ttl_seconds

    buf.batch_dir(batch_id).mkdir(parents=True, exist_ok=True)
    record = {
        "batch_id": batch_id,
        "token": token,
        "created_at": now,
        "expires_at": expires_at,
        "files": {},
        "job_ids": [],
    }
    r.setex(f"batch:{batch_id}", settings.job_ttl_seconds, json.dumps(record))

    response.set_cookie(
        key="batch_token",
        value=token,
        max_age=settings.job_ttl_seconds,
        httponly=True,
        samesite="strict",
    )
    return BatchCreateResponse(
        batch_id=batch_id,
        batch_token=token,
        expires_at=expires_at,
        ttl_seconds=settings.job_ttl_seconds,
    )


@router.get("/{batch_id}")
def get_batch_status(batch_id: str, batch: dict = Depends(require_batch_access), r=Depends(get_redis)) -> dict:
    jobs: list[dict] = []
    for jid in batch.get("job_ids", []):
        raw_job = r.get(f"job:{jid}")
        if raw_job:
            jobs.append(json.loads(raw_job))
    return {
        "batch_id": batch_id,
        "expires_at": batch.get("expires_at"),
        "files": list(batch.get("files", {}).values()),
        "jobs": jobs,
    }


@router.post("/{batch_id}/convert", response_model=ConvertResponse)
def start_conversion(
    batch_id: str,
    payload: ConvertRequest,
    batch: dict = Depends(require_batch_access),
    r=Depends(get_redis),
    buf=Depends(get_buffer),
) -> ConvertResponse:
    settings = get_settings()
    files_map = batch.get("files", {})
    summaries: list[JobSummary] = []

    if payload.merge_mode == "images_to_pdf":
        file_ids = payload.ordered_file_ids or [item.file_id for item in payload.items]
        if not file_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Dateien zum Zusammenfuehren angegeben.")
        input_paths: list[str] = []
        for fid in file_ids:
            finfo = files_map.get(fid)
            if not finfo:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Datei {fid} nicht im Batch.")
            if finfo["category"] != "image":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Bilder koennen zu einem PDF kombiniert werden.")
            input_paths.append(finfo["input_path"])

        job_id = uuid.uuid4().hex
        odir = buf.job_output_dir(batch_id, job_id)
        job_payload = JobPayload(
            job_id=job_id,
            batch_id=batch_id,
            file_ids=file_ids,
            input_paths=input_paths,
            original_filename="merged_images.pdf",
            source_format="png",
            target_format="pdf",
            pipeline=[{"src": "png", "dst": "pdf", "engine": "img2pdf_merge", "worker": "media"}],
            current_input_path=input_paths[0],
            output_dir=str(odir),
            options=payload.merge_options,
            merge_mode="images_to_pdf",
        )
        _enqueue_job(r, batch, job_payload, settings.job_ttl_seconds)
        summaries.append(
            JobSummary(
                job_id=job_id,
                file_id=file_ids[0],
                source_format="images",
                target_format="pdf",
                status="queued",
                progress=0,
                phase="In Warteschlange",
            )
        )
    else:
        if not payload.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Konvertierungsauftraege angegeben.")
        for item in payload.items:
            finfo = files_map.get(item.file_id)
            if not finfo:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Datei {item.file_id} nicht gefunden.")
            src_fmt = finfo["detected_format"]
            dst_fmt = normalize_format(item.target_format)
            try:
                edges = find_conversion_path(src_fmt, dst_fmt)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

            job_id = uuid.uuid4().hex
            odir = buf.job_output_dir(batch_id, job_id)
            pipeline_dicts = [
                {"src": e.src, "dst": e.dst, "engine": e.engine, "worker": e.worker}
                for e in edges
            ]
            job_payload = JobPayload(
                job_id=job_id,
                batch_id=batch_id,
                file_ids=[item.file_id],
                input_paths=[finfo["input_path"]],
                original_filename=finfo["filename"],
                source_format=src_fmt,
                target_format=dst_fmt,
                pipeline=pipeline_dicts,
                current_input_path=finfo["input_path"],
                output_dir=str(odir),
                options=item.options,
            )
            _enqueue_job(r, batch, job_payload, settings.job_ttl_seconds)
            summaries.append(
                JobSummary(
                    job_id=job_id,
                    file_id=item.file_id,
                    source_format=src_fmt,
                    target_format=dst_fmt,
                    status="queued",
                    progress=0,
                    phase="In Warteschlange",
                )
            )

    r.setex(f"batch:{batch_id}", settings.job_ttl_seconds, json.dumps(batch))
    return ConvertResponse(batch_id=batch_id, jobs=summaries)


def _enqueue_job(r, batch: dict, payload: JobPayload, ttl: int) -> None:
    record = {
        "job_id": payload.job_id,
        "batch_id": payload.batch_id,
        "file_id": payload.file_ids[0] if payload.file_ids else None,
        "source_format": payload.source_format,
        "target_format": payload.target_format,
        "status": "queued",
        "progress": 0,
        "phase": "In Warteschlange",
        "output_path": None,
        "output_filename": None,
        "output_size": None,
        "is_archive": False,
        "page_count": None,
        "error_message": None,
    }
    r.setex(f"job:{payload.job_id}", ttl, json.dumps(record))
    batch.setdefault("job_ids", []).append(payload.job_id)
    first_worker = payload.pipeline[0]["worker"]
    r.lpush(f"queue:{first_worker}", payload.model_dump_json())


@router.get("/{batch_id}/events")
async def stream_batch_events(
    batch_id: str,
    request: Request,
    batch: dict = Depends(require_batch_access),
    r=Depends(get_redis),
) -> StreamingResponse:
    pubsub = r.pubsub()
    pubsub.subscribe(f"batch:{batch_id}:events")

    async def event_generator():
        try:
            # Send initial snapshot so clients immediately sync after reconnect
            yield f"event: batch.snapshot\ndata: {json.dumps({'batch_id': batch_id, 'expires_at': batch.get('expires_at')})}\n\n"
            last_keepalive = time.monotonic()
            while True:
                if await request.is_disconnected():
                    break
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
                if msg and msg.get("type") == "message":
                    parsed = json.loads(msg["data"])
                    ev_name = parsed.get("event", "message")
                    ev_data = json.dumps(parsed.get("data", {}), ensure_ascii=False)
                    yield f"event: {ev_name}\ndata: {ev_data}\n\n"
                    last_keepalive = time.monotonic()
                else:
                    if time.monotonic() - last_keepalive >= 15.0:
                        yield ": keepalive\n\n"
                        last_keepalive = time.monotonic()
                    await asyncio.sleep(0.15)
        finally:
            try:
                pubsub.unsubscribe()
                pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{batch_id}/download.zip")
def download_batch_zip(
    batch_id: str,
    batch: dict = Depends(require_batch_access),
    r=Depends(get_redis),
) -> StreamingResponse:
    zs = ZipStream()
    added_names: set[str] = set()
    file_count = 0

    for jid in batch.get("job_ids", []):
        raw_job = r.get(f"job:{jid}")
        if not raw_job:
            continue
        job = json.loads(raw_job)
        if job.get("status") != "completed" or not job.get("output_path"):
            continue

        out_path = Path(job["output_path"])
        if not out_path.exists():
            continue

        # If a 1-to-N job generated a directory of pages or a zip, stream individual files cleanly
        if out_path.is_file() and out_path.suffix.lower() == ".zip" and job.get("is_archive"):
            stem = Path(job.get("output_filename") or "pages").stem
            with zipfile.ZipFile(out_path, "r") as sub_zf:
                for member in sub_zf.infolist():
                    if member.is_dir():
                        continue
                    arc_name = _unique_arcname(f"{stem}/{sanitize_filename(member.filename)}", added_names)
                    data = sub_zf.read(member.filename)
                    zs.add(data, arcname=arc_name)
                    file_count += 1
        elif out_path.is_file():
            arc_name = _unique_arcname(sanitize_filename(job.get("output_filename") or out_path.name), added_names)
            ext = out_path.suffix.lower().lstrip(".")
            compress_type = zipfile.ZIP_STORED if ext in ALREADY_COMPRESSED_FORMATS else zipfile.ZIP_DEFLATED
            zs.add_path(str(out_path), arcname=arc_name, compress_type=compress_type)
            file_count += 1

    if file_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keine fertigen Dateien fuer den ZIP-Download vorhanden.")

    return StreamingResponse(
        zs,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="converted-{batch_id[:8]}.zip"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


def _unique_arcname(candidate: str, seen: set[str]) -> str:
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    p = Path(candidate)
    idx = 2
    while True:
        alt = str(p.with_name(f"{p.stem}_{idx}{p.suffix}"))
        if alt not in seen:
            seen.add(alt)
            return alt
        idx += 1


@router.delete("/{batch_id}", status_code=status.HTTP_200_OK)
@router.post("/{batch_id}/dispose", status_code=status.HTTP_200_OK)
def purge_batch(
    batch_id: str,
    batch: dict = Depends(require_batch_access),
    r=Depends(get_redis),
    buf=Depends(get_buffer),
) -> dict[str, object]:
    for jid in batch.get("job_ids", []):
        r.setex(f"job:{jid}:cancel", 120, "1")
        r.delete(f"job:{jid}")
    r.delete(f"batch:{batch_id}")
    buf.delete_batch_dir(batch_id)
    return {"deleted": True, "batch_id": batch_id}
