import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.main import create_app, run_gc_cycle
from backend.shared.buffer_manager import BufferManager
from backend.shared.config import Settings
from tests.fake_redis import FakeRedis


def _make_test_env(tmp_path: Path, reject_pct: float = 90.0):
    settings = Settings(
        redis_url="redis://localhost:6379/0",
        buffer_dir=tmp_path,
        job_ttl_seconds=1200,
        max_file_bytes=5_000_000,
        max_batch_bytes=10_000_000,
        buffer_high_watermark_pct=80.0,
        buffer_reject_pct=reject_pct,
        image_timeout_sec=30,
        doc_timeout_sec=60,
        video_timeout_sec=900,
        enable_hw_accel=False,
        allowed_origins=["*"],
        gc_interval_sec=60,
        chunk_size_default=1024,
    )
    fake_redis = FakeRedis()
    buf = BufferManager(settings)
    app = create_app(redis_client=fake_redis, buffer_manager=buf)
    return app, fake_redis, buf, settings


def test_health_and_capabilities(tmp_path: Path):
    app, _, _, _ = _make_test_env(tmp_path)
    with TestClient(app) as client:
        res_h = client.get("/api/v1/health")
        assert res_h.status_code == 200
        assert res_h.json()["status"] == "ok"

        res_c = client.get("/api/v1/capabilities")
        assert res_c.status_code == 200
        assert "matrix" in res_c.json()


def test_chunked_upload_convert_and_purge(tmp_path: Path):
    app, fake_redis, buf, _ = _make_test_env(tmp_path)
    sample_png = b"\x89PNG\r\n\x1a\n" + b"0" * 1500
    chunk_size = 1024

    with TestClient(app) as client:
        b_res = client.post("/api/v1/batches")
        assert b_res.status_code == 201
        batch = b_res.json()
        headers = {"X-Batch-Token": batch["batch_token"]}

        init_res = client.post(
            "/api/v1/uploads/init",
            headers=headers,
            json={
                "batch_id": batch["batch_id"],
                "filename": "photo.jpg",  # Intentionally misleading extension
                "size": len(sample_png),
                "declared_mime": "image/jpeg",
                "chunk_size": chunk_size,
                "total_chunks": 2,
            },
        )
        assert init_res.status_code == 200
        upload_id = init_res.json()["upload_id"]

        assert client.put(f"/api/v1/uploads/{upload_id}/chunks/0", headers=headers, content=sample_png[:1024]).status_code == 200
        assert client.put(f"/api/v1/uploads/{upload_id}/chunks/1", headers=headers, content=sample_png[1024:]).status_code == 200

        comp_res = client.post(f"/api/v1/uploads/{upload_id}/complete", headers=headers)
        assert comp_res.status_code == 200
        comp_data = comp_res.json()
        assert comp_data["detected_format"] == "png"
        assert "webp" in comp_data["valid_targets"]

        conv_res = client.post(
            f"/api/v1/batches/{batch['batch_id']}/convert",
            headers=headers,
            json={
                "items": [{"file_id": comp_data["file_id"], "target_format": "webp"}],
                "merge_mode": "none",
                "ordered_file_ids": [],
            },
        )
        assert conv_res.status_code == 200
        job_id = conv_res.json()["jobs"][0]["job_id"]

        # Simulate worker output for ZIP download check
        out_file = buf.job_output_dir(batch["batch_id"], job_id) / "step_0.webp"
        out_file.write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
        job_rec = json.loads(fake_redis.get(f"job:{job_id}") or "{}")
        job_rec["status"] = "completed"
        job_rec["output_path"] = str(out_file)
        job_rec["output_filename"] = "photo.webp"
        fake_redis.setex(f"job:{job_id}", 600, json.dumps(job_rec))

        zip_res = client.get(f"/api/v1/batches/{batch['batch_id']}/download.zip", headers=headers)
        assert zip_res.status_code == 200
        assert zip_res.content[:2] == b"PK"

        del_res = client.delete(f"/api/v1/batches/{batch['batch_id']}", headers=headers)
        assert del_res.status_code == 200
        assert not buf.batch_dir(batch["batch_id"]).exists()


def test_high_watermark_rejects_with_507(tmp_path: Path):
    # reject_pct=0.0 guarantees reject threshold is exceeded
    app, _, _, _ = _make_test_env(tmp_path, reject_pct=0.0)
    with TestClient(app) as client:
        res = client.post("/api/v1/batches")
        assert res.status_code == 507


def test_gc_cleans_expired_batch_dir(tmp_path: Path):
    app, fake_redis, buf, settings = _make_test_env(tmp_path)
    orphan = buf.batch_dir("orphanbatch12345")
    orphan.mkdir(parents=True, exist_ok=True)
    res = run_gc_cycle(fake_redis, buf, settings)
    assert res["expired_batches"] >= 1
    assert not orphan.exists()
