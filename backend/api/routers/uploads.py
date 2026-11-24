"""Chunked upload endpoints with magic-byte verification and watermark protection."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.auth_guard import require_authenticated_user
from backend.api.deps import get_buffer, get_redis, require_batch_access
from backend.shared.buffer_manager import sanitize_filename
from backend.shared.config import get_settings
from backend.shared.conversion_graph import get_valid_targets
from backend.shared.formats import FORMAT_SPECS
from backend.shared.magic_detect import detect_format
from backend.shared.models import UploadCompleteResponse, UploadInitRequest, UploadInitResponse

router = APIRouter(
    prefix="/api/v1/uploads",
    tags=["uploads"],
    dependencies=[Depends(require_authenticated_user)],
)


@router.post("/init", response_model=UploadInitResponse)
async def init_upload(
    payload: UploadInitRequest,
    request: Request,
    r=Depends(get_redis),
    buf=Depends(get_buffer),
) -> UploadInitResponse:
    settings = get_settings()
    batch = require_batch_access(
        request,
        payload.batch_id,
        x_batch_token=request.headers.get("x-batch-token"),
        batch_token=request.cookies.get("batch_token"),
    )

    if buf.is_reject_threshold():
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="Der temporaere Arbeitsspeicher ist aktuell ausgelastet. Bitte in Kuerze erneut versuchen.",
            headers={"Retry-After": "30"},
        )

    if payload.size > settings.max_file_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Datei ueberschreitet das Einzeldatei-Limit ({settings.max_file_bytes // (1024 * 1024)} MB).",
        )

    current_batch_bytes = sum(int(f.get("size", 0)) for f in batch.get("files", {}).values())
    if current_batch_bytes + payload.size > settings.max_batch_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Batch ueberschreitet das Gesamtlimit ({settings.max_batch_bytes // (1024 * 1024)} MB).",
        )

    upload_id = uuid.uuid4().hex
    buf.upload_dir(upload_id)
    meta = {
        "upload_id": upload_id,
        "batch_id": payload.batch_id,
        "filename": sanitize_filename(payload.filename),
        "size": payload.size,
        "chunk_size": payload.chunk_size,
        "total_chunks": payload.total_chunks,
        "received": [],
    }
    r.setex(f"upload:{upload_id}", settings.job_ttl_seconds, json.dumps(meta))
    return UploadInitResponse(
        upload_id=upload_id,
        chunk_size=payload.chunk_size,
        total_chunks=payload.total_chunks,
    )


@router.put("/{upload_id}/chunks/{index}")
async def upload_chunk(
    upload_id: str,
    index: int,
    request: Request,
    r=Depends(get_redis),
    buf=Depends(get_buffer),
) -> dict[str, object]:
    raw = r.get(f"upload:{upload_id}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload-Session nicht gefunden.")
    meta = json.loads(raw)

    require_batch_access(
        request,
        meta["batch_id"],
        x_batch_token=request.headers.get("x-batch-token"),
        batch_token=request.cookies.get("batch_token"),
    )

    if index < 0 or index >= meta["total_chunks"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungueltiger Chunk-Index.")

    body = await request.body()
    if len(body) > meta["chunk_size"] + 4096:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Chunk groesser als vereinbart.")

    chunk_path = buf.upload_dir(upload_id) / f"{index:06d}.part"
    chunk_path.write_bytes(body)

    if index not in meta["received"]:
        meta["received"].append(index)
        r.setex(f"upload:{upload_id}", get_settings().job_ttl_seconds, json.dumps(meta))

    return {"upload_id": upload_id, "index": index, "received_count": len(meta["received"])}


@router.post("/{upload_id}/complete", response_model=UploadCompleteResponse)
def complete_upload(
    upload_id: str,
    request: Request,
    r=Depends(get_redis),
    buf=Depends(get_buffer),
) -> UploadCompleteResponse:
    settings = get_settings()
    raw = r.get(f"upload:{upload_id}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload-Session abgelaufen.")
    meta = json.loads(raw)
    batch_id = meta["batch_id"]

    batch = require_batch_access(
        request,
        batch_id,
        x_batch_token=request.headers.get("x-batch-token"),
        batch_token=request.cookies.get("batch_token"),
    )

    udir = buf.upload_dir(upload_id)
    expected = set(range(meta["total_chunks"]))
    parts = [udir / f"{i:06d}.part" for i in range(meta["total_chunks"])]
    missing = [i for i, p in enumerate(parts) if not p.exists()]
    if missing or len(expected) != meta["total_chunks"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Es fehlen Chunks fuer die Zusammenfuehrung: {missing[:5]}",
        )

    file_id = uuid.uuid4().hex
    dest_path = buf.batch_input_path(batch_id, file_id)
    total_written = 0
    with dest_path.open("wb") as out_fh:
        for part in parts:
            data = part.read_bytes()
            total_written += len(data)
            out_fh.write(data)

    buf.delete_upload_dir(upload_id)
    r.delete(f"upload:{upload_id}")

    try:
        detected = detect_format(dest_path, meta["filename"])
    except ValueError as exc:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))

    spec = FORMAT_SPECS.get(detected)
    valid_targets = get_valid_targets(detected)
    if not spec or not valid_targets:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Erkanntes Format '{detected}' wird fuer die Konvertierung nicht unterstuetzt.",
        )

    default_target = spec.default_target if spec.default_target in valid_targets else valid_targets[0]
    batch.setdefault("files", {})[file_id] = {
        "file_id": file_id,
        "filename": meta["filename"],
        "size": total_written,
        "detected_format": detected,
        "category": spec.category,
        "input_path": str(dest_path),
    }

    ttl = r.ttl(f"batch:{batch_id}")
    r.setex(f"batch:{batch_id}", ttl if ttl and ttl > 0 else settings.job_ttl_seconds, json.dumps(batch))

    return UploadCompleteResponse(
        file_id=file_id,
        filename=meta["filename"],
        size=total_written,
        detected_format=detected,
        category=spec.category,
        valid_targets=valid_targets,
        default_target=default_target,
    )
