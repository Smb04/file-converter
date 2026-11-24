"""Media worker handling images (libvips, resvg, libraw, ImageMagick, img2pdf) and audio/video (FFmpeg)."""

from __future__ import annotations

import multiprocessing
import os
import subprocess
import time
from functools import lru_cache
from pathlib import Path

try:
    import img2pdf
except ImportError:  # pragma: no cover
    img2pdf = None  # type: ignore

try:
    import pyvips
except (ImportError, OSError):  # pragma: no cover
    pyvips = None  # type: ignore

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

from backend.shared.config import get_settings
from backend.shared.models import ConversionOptions, JobPayload
from backend.shared.worker_base import (
    WorkerCancelledError,
    publish_batch_event,
    run_subprocess_guarded,
    run_worker_loop,
    update_job_record,
)


def _step_output_path(payload: JobPayload, step: dict) -> Path:
    out_dir = Path(payload.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"step_{payload.step_index}.{step['dst']}"


def _convert_libvips(src: Path, dst: Path, dst_fmt: str, opts: ConversionOptions) -> None:
    img = pyvips.Image.new_from_file(str(src), access="sequential")

    # Apply EXIF auto-rotation
    try:
        img = img.autorot()
    except Exception:
        pass

    if opts.max_width or opts.max_height:
        tw = opts.max_width or 16000
        th = opts.max_height or 16000
        scale = min(tw / max(1, img.width), th / max(1, img.height), 1.0)
        if scale < 1.0:
            img = img.resize(scale)

    # Flatten alpha when target does not support transparency
    if dst_fmt in {"jpg", "bmp"} and img.hasalpha():
        bg = _hex_to_rgb(opts.background_color)
        img = img.flatten(background=bg)

    if dst_fmt == "jpg":
        img.jpegsave(str(dst), Q=opts.quality, strip=opts.strip_metadata)
    elif dst_fmt == "png":
        img.pngsave(str(dst), compression=6, strip=opts.strip_metadata)
    elif dst_fmt == "webp":
        img.webpsave(str(dst), Q=opts.quality, strip=opts.strip_metadata)
    elif dst_fmt in {"avif", "heic"}:
        compression = "av1" if dst_fmt == "avif" else "hevc"
        img.heifsave(str(dst), Q=opts.quality, compression=compression, strip=opts.strip_metadata)
    elif dst_fmt == "jxl":
        img.jxlsave(str(dst), Q=opts.quality)
    elif dst_fmt == "tiff":
        img.tiffsave(str(dst), compression="deflate", strip=opts.strip_metadata)
    elif dst_fmt == "gif":
        img.gifsave(str(dst))
    elif dst_fmt == "bmp":
        with Image.open(src) as pil_img:
            if pil_img.mode in {"RGBA", "LA", "P"}:
                bg_img = Image.new("RGB", pil_img.size, _hex_to_rgb(opts.background_color))
                rgba = pil_img.convert("RGBA")
                bg_img.paste(rgba, mask=rgba.split()[3])
                bg_img.save(dst, format="BMP")
            else:
                pil_img.convert("RGB").save(dst, format="BMP")
    else:
        img.write_to_file(str(dst))


def _hex_to_rgb(hex_color: str) -> list[int]:
    cleaned = hex_color.strip().lstrip("#")
    if len(cleaned) != 6:
        return [255, 255, 255]
    try:
        return [int(cleaned[i : i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return [255, 255, 255]


def _convert_svg_to_png(r, payload: JobPayload, src: Path, dst: Path, opts: ConversionOptions) -> None:
    cmd = ["rsvg-convert", "--dpi-x", str(opts.dpi), "--dpi-y", str(opts.dpi)]
    if opts.max_width:
        cmd.extend(["--width", str(opts.max_width)])
    if opts.max_height:
        cmd.extend(["--height", str(opts.max_height)])
    cmd.extend(["-o", str(dst), str(src)])
    rc, err = run_subprocess_guarded(cmd, r, payload.job_id, get_settings().image_timeout_sec)
    if rc != 0:
        raise RuntimeError(f"SVG-Rasterisierung fehlgeschlagen: {err}")


def _convert_to_ico(src: Path, dst: Path) -> None:
    with Image.open(src) as img:
        rgba = img.convert("RGBA")
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        rgba.save(dst, format="ICO", sizes=sizes)


def _convert_raw_to_raster(r, payload: JobPayload, src: Path, dst: Path, dst_fmt: str, opts: ConversionOptions) -> None:
    ppm_tmp = dst.with_suffix(".ppm")
    cmd = ["dcraw_emu", "-w", "-Z", str(ppm_tmp), str(src)]
    rc, err = run_subprocess_guarded(cmd, r, payload.job_id, get_settings().image_timeout_sec)
    if rc != 0 or not ppm_tmp.exists():
        raise RuntimeError(f"Kamera-RAW Dekodierung fehlgeschlagen: {err}")
    try:
        _convert_libvips(ppm_tmp, dst, dst_fmt, opts)
    finally:
        ppm_tmp.unlink(missing_ok=True)


def _convert_images_to_pdf(input_paths: list[Path], dst: Path, opts: ConversionOptions) -> None:
    normalized_paths: list[Path] = []
    temp_files: list[Path] = []
    try:
        for idx, p in enumerate(input_paths):
            with Image.open(p) as im:
                if im.format in {"JPEG", "PNG", "TIFF"} and im.mode in {"RGB", "L"} and not opts.strip_metadata:
                    normalized_paths.append(p)
                else:
                    clean_path = dst.with_name(f"_pdf_in_{idx}.png")
                    if im.mode in {"RGBA", "LA", "P"}:
                        bg = Image.new("RGB", im.size, _hex_to_rgb(opts.background_color))
                        rgba = im.convert("RGBA")
                        bg.paste(rgba, mask=rgba.split()[3])
                        bg.save(clean_path, format="PNG")
                    else:
                        im.convert("RGB").save(clean_path, format="PNG")
                    normalized_paths.append(clean_path)
                    temp_files.append(clean_path)

        with dst.open("wb") as fh:
            fh.write(img2pdf.convert([str(p) for p in normalized_paths]))
    finally:
        for tf in temp_files:
            tf.unlink(missing_ok=True)


def _probe_duration_us(src: Path) -> int:
    try:
        res = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(src),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        sec = float(res.stdout.strip())
        return max(1, int(sec * 1_000_000))
    except Exception:
        return 0


def _vaapi_device_path() -> Path:
    return Path(get_settings().vaapi_device)


def _hw_vaapi_available(opts: ConversionOptions) -> bool:
    settings = get_settings()
    return settings.enable_hw_accel and opts.use_hw_accel and _vaapi_device_path().exists()


@lru_cache(maxsize=1)
def _get_supported_vaapi_encoders() -> frozenset[str]:
    candidates = {"h264_vaapi", "hevc_vaapi", "vp9_vaapi", "av1_vaapi"}
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        found = {enc for enc in candidates if enc in res.stdout}
        return frozenset(found)
    except Exception:
        return frozenset()


def _select_vaapi_encoder(
    dst_fmt: str, video_codec: str, available: frozenset[str]
) -> str | None:
    if dst_fmt == "webm":
        if video_codec == "av1" and "av1_vaapi" in available:
            return "av1_vaapi"
        if "vp9_vaapi" in available:
            return "vp9_vaapi"
        return None
    if dst_fmt in {"mp4", "mkv", "mov"}:
        if video_codec == "av1" and "av1_vaapi" in available:
            return "av1_vaapi"
        if video_codec == "h265" and "hevc_vaapi" in available:
            return "hevc_vaapi"
        if video_codec in {"auto", "h264"} and "h264_vaapi" in available:
            return "h264_vaapi"
    return None


def _build_video_cmd(
    src: Path,
    dst: Path,
    dst_fmt: str,
    opts: ConversionOptions,
    vaapi_encoder: str | None,
    vaapi_device: str,
) -> list[str]:
    crf_map = {"small": "28", "balanced": "23", "high": "18"}
    vaapi_q_map = {"small": "30", "balanced": "24", "high": "19"}
    crf = crf_map.get(opts.video_preset, "23")
    vaapi_q = vaapi_q_map.get(opts.video_preset, "24")

    cmd = ["ffmpeg", "-y", "-protocol_whitelist", "file,pipe"]
    if vaapi_encoder:
        cmd.extend(["-vaapi_device", vaapi_device])

    cmd.extend(["-i", str(src)])

    scale_height = {"1080p": "1080", "720p": "720", "480p": "480"}.get(opts.video_resolution)
    if vaapi_encoder:
        vf = "format=nv12,hwupload" + (f",scale_vaapi=-2:{scale_height}" if scale_height else "")
        cmd.extend(["-vf", vf, "-c:v", vaapi_encoder, "-global_quality", vaapi_q])
    else:
        if scale_height:
            cmd.extend(["-vf", f"scale=-2:{scale_height}"])
        if dst_fmt == "webm":
            vcodec = "libaom-av1" if opts.video_codec == "av1" else "libvpx-vp9"
            cmd.extend(["-c:v", vcodec, "-crf", crf, "-b:v", "0"])
        elif opts.video_codec == "h265":
            cmd.extend(["-c:v", "libx265", "-crf", crf, "-preset", "medium"])
        elif opts.video_codec == "av1":
            cmd.extend(["-c:v", "libaom-av1", "-crf", crf, "-cpu-used", "6"])
        else:
            cmd.extend(["-c:v", "libx264", "-crf", crf, "-preset", "medium", "-pix_fmt", "yuv420p"])

    if opts.mute_audio:
        cmd.append("-an")
    elif dst_fmt == "webm":
        cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
    else:
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])

    if dst_fmt == "mp4":
        cmd.extend(["-movflags", "+faststart"])

    cmd.extend(["-progress", "pipe:1", "-nostats", str(dst)])
    return cmd


def _run_ffmpeg_with_progress(
    r,
    payload: JobPayload,
    cmd: list[str],
    duration_us: int,
    timeout_sec: int,
    phase_label: str,
) -> None:
    last_emit = 0.0

    def _on_line(line: str) -> None:
        nonlocal last_emit
        if duration_us <= 0 or not line.startswith("out_time_us="):
            return
        try:
            out_us = int(line.split("=", 1)[1])
        except ValueError:
            return
        now = time.monotonic()
        if now - last_emit < 0.5:
            return
        last_emit = now
        pct = min(98, max(5, int((out_us / duration_us) * 100)))
        update_job_record(r, payload.job_id, progress=pct, phase=phase_label)
        publish_batch_event(
            r,
            payload.batch_id,
            "job.progress",
            {"job_id": payload.job_id, "status": "running", "progress": pct, "phase": phase_label},
        )

    rc, err = run_subprocess_guarded(cmd, r, payload.job_id, timeout_sec, on_stdout_line=_on_line)
    if rc != 0:
        raise RuntimeError(f"FFmpeg Fehler: {err}")


def _convert_audio(r, payload: JobPayload, src: Path, dst: Path, dst_fmt: str, opts: ConversionOptions) -> None:
    duration_us = _probe_duration_us(src)
    cmd = [
        "ffmpeg",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(src),
        "-vn",
    ]
    if opts.normalize_audio:
        cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
    if opts.sample_rate:
        cmd.extend(["-ar", str(opts.sample_rate)])
    if opts.channels:
        cmd.extend(["-ac", str(opts.channels)])

    codec_args = {
        "mp3": ["-c:a", "libmp3lame", "-b:a", opts.audio_bitrate],
        "m4a": ["-c:a", "aac", "-b:a", opts.audio_bitrate],
        "ogg": ["-c:a", "libvorbis", "-b:a", opts.audio_bitrate],
        "opus": ["-c:a", "libopus", "-b:a", opts.audio_bitrate],
        "flac": ["-c:a", "flac"],
        "wav": ["-c:a", "pcm_s16le"],
        "aiff": ["-c:a", "pcm_s16be"],
        "alac": ["-c:a", "alac", "-f", "ipod"],
    }.get(dst_fmt, ["-b:a", opts.audio_bitrate])
    cmd.extend(codec_args)
    cmd.extend(["-progress", "pipe:1", "-nostats", str(dst)])
    _run_ffmpeg_with_progress(r, payload, cmd, duration_us, get_settings().video_timeout_sec, "Kodiere Audio")


def _convert_video(r, payload: JobPayload, src: Path, dst: Path, dst_fmt: str, opts: ConversionOptions) -> None:
    duration_us = _probe_duration_us(src)
    timeout_sec = get_settings().video_timeout_sec
    vaapi_device = str(_vaapi_device_path())

    vaapi_encoder: str | None = None
    if _hw_vaapi_available(opts):
        vaapi_encoder = _select_vaapi_encoder(dst_fmt, opts.video_codec, _get_supported_vaapi_encoders())

    if vaapi_encoder:
        hw_cmd = _build_video_cmd(src, dst, dst_fmt, opts, vaapi_encoder, vaapi_device)
        try:
            _run_ffmpeg_with_progress(
                r, payload, hw_cmd, duration_us, timeout_sec, f"Transkodiere Video (GPU: {vaapi_encoder})"
            )
            return
        except (WorkerCancelledError, TimeoutError):
            raise
        except RuntimeError:
            dst.unlink(missing_ok=True)
            update_job_record(
                r, payload.job_id, progress=5, phase="Hardware-Encoding nicht kompatibel – nutze CPU-Fallback"
            )
            publish_batch_event(
                r,
                payload.batch_id,
                "job.progress",
                {
                    "job_id": payload.job_id,
                    "status": "running",
                    "progress": 5,
                    "phase": "Hardware-Encoding nicht kompatibel – nutze CPU-Fallback",
                },
            )

    cpu_cmd = _build_video_cmd(src, dst, dst_fmt, opts, None, vaapi_device)
    _run_ffmpeg_with_progress(r, payload, cpu_cmd, duration_us, timeout_sec, "Transkodiere Video")


def _convert_video_to_gif(r, payload: JobPayload, src: Path, dst: Path, opts: ConversionOptions) -> None:
    duration_us = _probe_duration_us(src)
    width = opts.max_width or 640
    cmd = [
        "ffmpeg",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(src),
        "-vf",
        f"fps=15,scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        "-loop",
        "0",
        "-progress",
        "pipe:1",
        "-nostats",
        str(dst),
    ]
    _run_ffmpeg_with_progress(r, payload, cmd, duration_us, get_settings().video_timeout_sec, "Erzeuge animiertes GIF")


def handle_media_job(r, payload: JobPayload, step: dict) -> tuple[Path, bool, int | None]:
    src = Path(payload.current_input_path)
    dst = _step_output_path(payload, step)
    engine = step["engine"]
    dst_fmt = step["dst"]
    opts = payload.options

    if engine == "img2pdf_merge":
        _convert_images_to_pdf([Path(p) for p in payload.input_paths], dst, opts)
        return dst, False, len(payload.input_paths)
    if engine == "img2pdf":
        _convert_images_to_pdf([src], dst, opts)
        return dst, False, 1
    if engine == "libvips":
        _convert_libvips(src, dst, dst_fmt, opts)
        return dst, False, None
    if engine == "resvg":
        _convert_svg_to_png(r, payload, src, dst, opts)
        return dst, False, None
    if engine == "svg_to_ico":
        png_tmp = dst.with_suffix(".tmp.png")
        _convert_svg_to_png(r, payload, src, png_tmp, opts)
        try:
            _convert_to_ico(png_tmp, dst)
        finally:
            png_tmp.unlink(missing_ok=True)
        return dst, False, None
    if engine == "pillow_ico":
        _convert_to_ico(src, dst)
        return dst, False, None
    if engine == "libraw":
        _convert_raw_to_raster(r, payload, src, dst, dst_fmt, opts)
        return dst, False, None
    if engine == "imagemagick":
        cmd = ["convert", str(src), str(dst)]
        rc, err = run_subprocess_guarded(cmd, r, payload.job_id, get_settings().image_timeout_sec)
        if rc != 0:
            raise RuntimeError(f"ImageMagick Konvertierung fehlgeschlagen: {err}")
        return dst, False, None
    if engine in {"ffmpeg_audio", "ffmpeg_extract_audio"}:
        _convert_audio(r, payload, src, dst, dst_fmt, opts)
        return dst, False, None
    if engine == "ffmpeg_video":
        _convert_video(r, payload, src, dst, dst_fmt, opts)
        return dst, False, None
    if engine == "ffmpeg_gif":
        _convert_video_to_gif(r, payload, src, dst, opts)
        return dst, False, None

    raise ValueError(f"Unbekannte Media-Engine: {engine}")


def _worker_process() -> None:
    run_worker_loop("media", "queue:media", handle_media_job)


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
