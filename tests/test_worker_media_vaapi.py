from pathlib import Path
from unittest.mock import patch

import pytest

from backend.shared.models import ConversionOptions, JobPayload
from backend.shared.worker_base import WorkerCancelledError
from backend.worker_media import worker as media_worker
from tests.fake_redis import FakeRedis


def test_select_vaapi_encoder_supports_arc_codecs():
    available = frozenset({"h264_vaapi", "hevc_vaapi", "vp9_vaapi", "av1_vaapi"})
    assert media_worker._select_vaapi_encoder("mp4", "auto", available) == "h264_vaapi"
    assert media_worker._select_vaapi_encoder("mp4", "h265", available) == "hevc_vaapi"
    assert media_worker._select_vaapi_encoder("mkv", "av1", available) == "av1_vaapi"
    assert media_worker._select_vaapi_encoder("webm", "auto", available) == "vp9_vaapi"
    assert media_worker._select_vaapi_encoder("webm", "av1", available) == "av1_vaapi"
    assert media_worker._select_vaapi_encoder("mp4", "h265", frozenset({"h264_vaapi"})) is None


def test_build_video_cmd_vaapi_vs_cpu(tmp_path: Path):
    src = tmp_path / "in.mov"
    dst = tmp_path / "out.mp4"
    opts = ConversionOptions(video_preset="balanced", video_resolution="720p", video_codec="av1")

    hw_cmd = media_worker._build_video_cmd(src, dst, "mp4", opts, "av1_vaapi", "/dev/dri/renderD129")
    assert "-vaapi_device" in hw_cmd
    assert "/dev/dri/renderD129" in hw_cmd
    assert "av1_vaapi" in hw_cmd
    assert "-global_quality" in hw_cmd
    assert "-crf" not in hw_cmd
    assert any("scale_vaapi=-2:720" in part for part in hw_cmd)

    cpu_cmd = media_worker._build_video_cmd(src, dst, "mp4", opts, None, "/dev/dri/renderD129")
    assert "-vaapi_device" not in cpu_cmd
    assert "libaom-av1" in cpu_cmd
    assert "-crf" in cpu_cmd


def test_convert_video_falls_back_to_cpu_on_vaapi_error(tmp_path: Path):
    src = tmp_path / "in.mov"
    src.write_bytes(b"fake")
    dst = tmp_path / "out.mp4"
    r = FakeRedis()
    payload = JobPayload(
        job_id="job123456",
        batch_id="batch123456",
        file_ids=["file123456"],
        input_paths=[str(src)],
        original_filename="clip.mov",
        source_format="mov",
        target_format="mp4",
        pipeline=[{"src": "mov", "dst": "mp4", "engine": "ffmpeg_video", "worker": "media"}],
        current_input_path=str(src),
        output_dir=str(tmp_path),
        options=ConversionOptions(use_hw_accel=True),
    )

    calls: list[list[str]] = []

    def fake_run(r_arg, payload_arg, cmd, duration_us, timeout_sec, phase_label):
        calls.append(cmd)
        if len(calls) == 1:
            dst.write_bytes(b"corrupt-partial")
            raise RuntimeError("vaapi init failed")
        dst.write_bytes(b"valid-cpu-output")

    with (
        patch.object(media_worker, "_probe_duration_us", return_value=1_000_000),
        patch.object(media_worker, "_hw_vaapi_available", return_value=True),
        patch.object(media_worker, "_get_supported_vaapi_encoders", return_value=frozenset({"h264_vaapi"})),
        patch.object(media_worker, "_run_ffmpeg_with_progress", side_effect=fake_run),
    ):
        media_worker._convert_video(r, payload, src, dst, "mp4", payload.options)

    assert len(calls) == 2
    assert "-vaapi_device" in calls[0]
    assert "-vaapi_device" not in calls[1]
    assert dst.read_bytes() == b"valid-cpu-output"


def test_convert_video_does_not_fallback_when_cancelled(tmp_path: Path):
    src = tmp_path / "in.mov"
    src.write_bytes(b"fake")
    dst = tmp_path / "out.mp4"
    r = FakeRedis()
    payload = JobPayload(
        job_id="job123456",
        batch_id="batch123456",
        file_ids=["file123456"],
        input_paths=[str(src)],
        original_filename="clip.mov",
        source_format="mov",
        target_format="mp4",
        pipeline=[{"src": "mov", "dst": "mp4", "engine": "ffmpeg_video", "worker": "media"}],
        current_input_path=str(src),
        output_dir=str(tmp_path),
        options=ConversionOptions(use_hw_accel=True),
    )

    with (
        patch.object(media_worker, "_probe_duration_us", return_value=1_000_000),
        patch.object(media_worker, "_hw_vaapi_available", return_value=True),
        patch.object(media_worker, "_get_supported_vaapi_encoders", return_value=frozenset({"h264_vaapi"})),
        patch.object(media_worker, "_run_ffmpeg_with_progress", side_effect=WorkerCancelledError("cancelled")),
    ):
        with pytest.raises(WorkerCancelledError):
            media_worker._convert_video(r, payload, src, dst, "mp4", payload.options)
