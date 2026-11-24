"""Document worker handling LibreOffice, Poppler, Ghostscript, Pandoc, and structured data."""

from __future__ import annotations

import multiprocessing
import os
import shutil
import zipfile
from pathlib import Path

from backend.shared.config import get_settings
from backend.shared.data_converter import convert_structured_data
from backend.shared.models import ConversionOptions, JobPayload
from backend.shared.worker_base import (
    publish_batch_event,
    run_subprocess_guarded,
    run_worker_loop,
    update_job_record,
)


def _step_output_path(payload: JobPayload, step: dict) -> Path:
    out_dir = Path(payload.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"step_{payload.step_index}.{step['dst']}"


def _run_libreoffice(r, payload: JobPayload, src: Path, dst: Path, dst_fmt: str) -> None:
    lo_profile = Path(f"/tmp/lo-profile-{payload.job_id}")
    lo_work_out = Path(f"/tmp/lo-out-{payload.job_id}")
    lo_profile.mkdir(parents=True, exist_ok=True)
    lo_work_out.mkdir(parents=True, exist_ok=True)

    # LibreOffice requires explicit extension on input file to detect filters reliably
    staged_in = lo_work_out / f"input.{payload.pipeline[payload.step_index]['src']}"
    shutil.copy2(src, staged_in)

    cmd = [
        "soffice",
        f"-env:UserInstallation=file://{lo_profile}",
        "--headless",
        "--invisible",
        "--norestore",
        "--nodefault",
        "--nolockcheck",
        "--convert-to",
        dst_fmt,
        "--outdir",
        str(lo_work_out),
        str(staged_in),
    ]
    try:
        rc, err = run_subprocess_guarded(cmd, r, payload.job_id, get_settings().doc_timeout_sec)
        if rc != 0:
            raise RuntimeError(f"LibreOffice Konvertierung fehlgeschlagen: {err}")
        produced = lo_work_out / f"input.{dst_fmt}"
        if not produced.exists():
            candidates = list(lo_work_out.glob(f"*.{dst_fmt}"))
            if not candidates:
                raise RuntimeError("LibreOffice hat keine Ausgabedatei erzeugt.")
            produced = candidates[0]
        shutil.move(str(produced), str(dst))
    finally:
        shutil.rmtree(lo_profile, ignore_errors=True)
        shutil.rmtree(lo_work_out, ignore_errors=True)


def _run_poppler_pdftoppm(
    r, payload: JobPayload, src: Path, dst: Path, dst_fmt: str, opts: ConversionOptions
) -> tuple[Path, bool, int]:
    pages_dir = Path(payload.output_dir) / f"pages_{payload.step_index}"
    pages_dir.mkdir(parents=True, exist_ok=True)

    fmt_flag = {"png": "-png", "jpg": "-jpeg", "tiff": "-tiff"}.get(dst_fmt, "-png")
    cmd = ["pdftoppm", fmt_flag, "-r", str(opts.dpi)]
    if opts.page_range:
        parts = [p.strip() for p in opts.page_range.split("-") if p.strip().isdigit()]
        if len(parts) == 2:
            cmd.extend(["-f", parts[0], "-l", parts[1]])
    cmd.extend([str(src), str(pages_dir / "page")])

    rc, err = run_subprocess_guarded(cmd, r, payload.job_id, get_settings().doc_timeout_sec)
    if rc != 0:
        raise RuntimeError(f"PDF-Seitenexport fehlgeschlagen: {err}")

    files = sorted(pages_dir.iterdir())
    if not files:
        raise RuntimeError("Keine PDF-Seiten gefunden.")

    if len(files) == 1:
        shutil.move(str(files[0]), str(dst))
        shutil.rmtree(pages_dir, ignore_errors=True)
        return dst, False, 1

    # Multi-page export -> bundle into ZIP archive
    zip_path = dst.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for page_file in files:
            zf.write(page_file, arcname=page_file.name)
    shutil.rmtree(pages_dir, ignore_errors=True)
    return zip_path, True, len(files)


def _run_poppler_pdftotext(r, payload: JobPayload, src: Path, dst: Path) -> None:
    cmd = ["pdftotext", "-enc", "UTF-8", str(src), str(dst)]
    rc, err = run_subprocess_guarded(cmd, r, payload.job_id, get_settings().doc_timeout_sec)
    if rc != 0:
        raise RuntimeError(f"Textextraktion aus PDF fehlgeschlagen: {err}")


def _run_ghostscript_compress(r, payload: JobPayload, src: Path, dst: Path, opts: ConversionOptions) -> None:
    preset = {"screen": "/screen", "ebook": "/ebook", "prepress": "/prepress"}.get(opts.pdf_quality, "/ebook")
    cmd = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={preset}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={dst}",
        str(src),
    ]
    rc, err = run_subprocess_guarded(cmd, r, payload.job_id, get_settings().doc_timeout_sec)
    if rc != 0:
        raise RuntimeError(f"PDF-Komprimierung fehlgeschlagen: {err}")


def _run_pandoc(r, payload: JobPayload, src: Path, dst: Path, src_fmt: str, dst_fmt: str) -> None:
    from_fmt = {"md": "markdown", "txt": "plain"}.get(src_fmt, src_fmt)
    to_fmt = {"md": "markdown", "txt": "plain"}.get(dst_fmt, dst_fmt)
    cmd = ["pandoc", "--sandbox=true", "-f", from_fmt, "-t", to_fmt, "-o", str(dst), str(src)]
    rc, err = run_subprocess_guarded(cmd, r, payload.job_id, get_settings().doc_timeout_sec)
    if rc != 0:
        raise RuntimeError(f"Pandoc Konvertierung fehlgeschlagen: {err}")


def handle_docs_job(r, payload: JobPayload, step: dict) -> tuple[Path, bool, int | None]:
    src = Path(payload.current_input_path)
    dst = _step_output_path(payload, step)
    engine = step["engine"]
    src_fmt = step["src"]
    dst_fmt = step["dst"]
    opts = payload.options

    update_job_record(r, payload.job_id, progress=35, phase=f"Verarbeite {src_fmt.upper()} -> {dst_fmt.upper()}")
    publish_batch_event(
        r,
        payload.batch_id,
        "job.progress",
        {"job_id": payload.job_id, "status": "running", "progress": 35, "phase": f"Verarbeite ({engine})"},
    )

    if engine == "data_converter":
        convert_structured_data(src, src_fmt, dst, dst_fmt)
        return dst, False, None
    if engine == "libreoffice":
        _run_libreoffice(r, payload, src, dst, dst_fmt)
        return dst, False, None
    if engine == "poppler_pdftoppm":
        return _run_poppler_pdftoppm(r, payload, src, dst, dst_fmt, opts)
    if engine == "poppler_pdftotext":
        _run_poppler_pdftotext(r, payload, src, dst)
        return dst, False, None
    if engine == "ghostscript_compress":
        _run_ghostscript_compress(r, payload, src, dst, opts)
        return dst, False, None
    if engine == "pandoc":
        _run_pandoc(r, payload, src, dst, src_fmt, dst_fmt)
        return dst, False, None

    raise ValueError(f"Unbekannte Dokumenten-Engine: {engine}")


def _worker_process() -> None:
    run_worker_loop("docs", "queue:docs", handle_docs_job)


def main() -> None:
    concurrency = max(1, int(os.getenv("WORKER_CONCURRENCY", "2")))
    if concurrency == 1:
        _worker_process()
        return
    procs = [multiprocessing.Process(target=_worker_process, daemon=False) for _ in range(concurrency)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()


if __name__ == "__main__":
    main()
