import json
from pathlib import Path

from backend.shared.buffer_manager import (
    BufferManager,
    generate_batch_token,
    sanitize_filename,
    verify_batch_token,
)
from backend.shared.config import Settings
from backend.shared.data_converter import convert_structured_data


def test_sanitize_filename_prevents_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\secret\\<script>.svg") == "_script_.svg"
    assert sanitize_filename("...\x00...") == "file"


def test_batch_token_verification():
    tok = generate_batch_token()
    assert verify_batch_token(tok, tok)
    assert not verify_batch_token(tok, tok[:-1] + ("A" if tok[-1] != "A" else "B"))
    assert not verify_batch_token(tok, None)


def test_buffer_manager_uuid_isolation_and_cleanup(tmp_path: Path):
    settings = Settings(
        redis_url="redis://localhost:6379/0",
        buffer_dir=tmp_path,
        job_ttl_seconds=600,
        max_file_bytes=10_000_000,
        max_batch_bytes=20_000_000,
        buffer_high_watermark_pct=80.0,
        buffer_reject_pct=90.0,
        image_timeout_sec=30,
        doc_timeout_sec=60,
        video_timeout_sec=900,
        enable_hw_accel=False,
        allowed_origins=["*"],
        gc_interval_sec=60,
        chunk_size_default=1024,
    )
    bm = BufferManager(settings)
    bm.ensure_dirs()
    in_path = bm.batch_input_path("batch12345678", "file12345678")
    in_path.write_bytes(b"hello")
    assert in_path.exists()

    bm.delete_batch_dir("batch12345678")
    assert not bm.batch_dir("batch12345678").exists()


def test_structured_data_roundtrip(tmp_path: Path):
    src_json = tmp_path / "in.json"
    dst_yaml = tmp_path / "mid.yaml"
    dst_csv = tmp_path / "mid.csv"
    dst_json = tmp_path / "out.json"

    records = [{"name": "Alpha", "size": 10}, {"name": "Beta", "size": 20}]
    src_json.write_text(json.dumps(records), encoding="utf-8")

    convert_structured_data(src_json, "json", dst_yaml, "yaml")
    convert_structured_data(dst_yaml, "yaml", dst_csv, "csv")
    convert_structured_data(dst_csv, "csv", dst_json, "json")

    parsed = json.loads(dst_json.read_text(encoding="utf-8"))
    assert len(parsed) == 2
    assert parsed[0]["name"] == "Alpha"
    assert parsed[1]["size"] == "20"
