from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.auth_store import AuthStore
from backend.api.main import create_app
from backend.shared.buffer_manager import BufferManager
from backend.shared.config import Settings
from tests.fake_redis import FakeRedis


def _make_auth_app(tmp_path: Path):
    auth_dir = tmp_path / "auth"
    buf_dir = tmp_path / "buffer"
    settings = Settings(
        redis_url="redis://localhost:6379/0",
        buffer_dir=buf_dir,
        job_ttl_seconds=1200,
        max_file_bytes=5_000_000,
        max_batch_bytes=10_000_000,
        buffer_high_watermark_pct=80.0,
        buffer_reject_pct=90.0,
        image_timeout_sec=30,
        doc_timeout_sec=60,
        video_timeout_sec=900,
        enable_hw_accel=False,
        allowed_origins=["*"],
        gc_interval_sec=60,
        chunk_size_default=1024,
        auth_data_dir=auth_dir,
    )
    fake_redis = FakeRedis()
    buf = BufferManager(settings)
    store = AuthStore(auth_dir)
    app = create_app(redis_client=fake_redis, buffer_manager=buf, auth_store=store)
    return app, store


def test_registration_blocked_over_duckdns_and_proxies(tmp_path: Path):
    app, _ = _make_auth_app(tmp_path)
    payload = {"username": "admin", "password": "VeryStrongPassword123"}

    with TestClient(app) as client:
        # 1. DuckDNS Host even over private tunnel IP MUST be blocked (403)
        res_duck = client.post(
            "/api/v1/auth/register",
            headers={"Host": "myconverter.duckdns.org", "X-Gateway-Client-IP": "10.8.0.1"},
            json=payload,
        )
        assert res_duck.status_code == 403

        # 2. Local IP with X-External-Proxy header MUST be blocked (403)
        res_ext = client.post(
            "/api/v1/auth/register",
            headers={
                "Host": "192.168.178.10:8095",
                "X-Gateway-Client-IP": "192.168.178.50",
                "X-External-Proxy": "1",
            },
            json=payload,
        )
        assert res_ext.status_code == 403

        # 3. Local IP with X-Incoming-XFF MUST be blocked (403)
        res_xff = client.post(
            "/api/v1/auth/register",
            headers={
                "Host": "192.168.178.10:8095",
                "X-Gateway-Client-IP": "192.168.178.50",
                "X-Incoming-XFF": "203.0.113.5",
            },
            json=payload,
        )
        assert res_xff.status_code == 403

        # 4. Local IP with X-Forwarded-Proto MUST be blocked (403)
        res_proto = client.post(
            "/api/v1/auth/register",
            headers={
                "Host": "192.168.178.10:8095",
                "X-Gateway-Client-IP": "192.168.178.50",
                "X-Forwarded-Proto": "https",
            },
            json=payload,
        )
        assert res_proto.status_code == 403

        # 5. Public client IP MUST be blocked (403)
        res_pub = client.post(
            "/api/v1/auth/register",
            headers={"Host": "192.168.178.10:8095", "X-Gateway-Client-IP": "198.51.100.22"},
            json=payload,
        )
        assert res_pub.status_code == 403

        # 6. Status over DuckDNS reports can_register_local = False
        st_duck = client.get(
            "/api/v1/auth/status",
            headers={"Host": "myconverter.duckdns.org", "X-Gateway-Client-IP": "10.8.0.1"},
        )
        assert st_duck.status_code == 200
        assert st_duck.json()["can_register_local"] is False
        assert st_duck.json()["has_users"] is False


def test_local_setup_duckdns_login_and_post_setup_guard(tmp_path: Path):
    app, _ = _make_auth_app(tmp_path)
    lan_headers = {"Host": "192.168.178.10:8095", "X-Gateway-Client-IP": "192.168.178.50"}
    duck_headers = {
        "Host": "myconverter.duckdns.org",
        "X-Gateway-Client-IP": "10.8.0.1",
        "X-External-Proxy": "1",
        "X-Forwarded-Proto": "https",
    }

    with TestClient(app) as client:
        # Unauthenticated converter calls are rejected
        assert client.post("/api/v1/batches", headers=duck_headers).status_code == 401

        # First setup succeeds on direct LAN IP
        reg1 = client.post(
            "/api/v1/auth/register",
            headers=lan_headers,
            json={"username": "admin", "password": "VeryStrongPassword123"},
        )
        assert reg1.status_code == 201
        assert reg1.json()["auto_logged_in"] is True

        # Authenticated admin can create second user in LAN
        reg2 = client.post(
            "/api/v1/auth/register",
            headers=lan_headers,
            json={"username": "partner", "password": "AnotherStrongPassword123"},
        )
        assert reg2.status_code == 201

    # New unauthenticated client cannot register even from LAN once users exist
    with TestClient(app) as unauth_lan:
        res_unauth_reg = unauth_lan.post(
            "/api/v1/auth/register",
            headers=lan_headers,
            json={"username": "intruder", "password": "IntruderPassword123"},
        )
        assert res_unauth_reg.status_code == 401

    # Client via DuckDNS (HTTPS) can login, use converter, cannot register or change password
    with TestClient(app, base_url="https://myconverter.duckdns.org") as duck_client:
        login_res = duck_client.post(
            "/api/v1/auth/login",
            headers=duck_headers,
            json={"username": "admin", "password": "VeryStrongPassword123", "remember_me": True},
        )
        assert login_res.status_code == 200
        assert login_res.json()["authenticated"] is True

        # Converter works after DuckDNS login
        assert duck_client.get("/api/v1/capabilities", headers=duck_headers).status_code == 200

        # Registration & password change over DuckDNS remain strictly 403 even when logged in
        assert (
            duck_client.post(
                "/api/v1/auth/register",
                headers=duck_headers,
                json={"username": "extra", "password": "ExtraPassword123"},
            ).status_code
            == 403
        )
        assert (
            duck_client.post(
                "/api/v1/auth/password",
                headers=duck_headers,
                json={"current_password": "VeryStrongPassword123", "new_password": "NewPassword456!"},
            ).status_code
            == 403
        )

        # Logout revokes session immediately
        assert duck_client.post("/api/v1/auth/logout", headers=duck_headers).status_code == 200
        assert duck_client.get("/api/v1/capabilities", headers=duck_headers).status_code == 401


def test_password_change_invalidates_old_sessions_and_brute_force_lockout(tmp_path: Path):
    app, _ = _make_auth_app(tmp_path)
    lan_headers = {"Host": "192.168.178.10:8095", "X-Gateway-Client-IP": "192.168.178.50"}
    duck_headers = {
        "Host": "myconverter.duckdns.org",
        "X-Gateway-Client-IP": "10.8.0.1",
        "X-External-Proxy": "1",
    }

    with TestClient(app) as lan_client, TestClient(app) as duck_client:
        assert (
            lan_client.post(
                "/api/v1/auth/register",
                headers=lan_headers,
                json={"username": "admin", "password": "InitialPassword123"},
            ).status_code
            == 201
        )
        assert (
            duck_client.post(
                "/api/v1/auth/login",
                headers=duck_headers,
                json={"username": "admin", "password": "InitialPassword123"},
            ).status_code
            == 200
        )
        assert duck_client.get("/api/v1/capabilities", headers=duck_headers).status_code == 200

        # Change password in LAN -> DuckDNS session must be invalidated immediately
        pw_res = lan_client.post(
            "/api/v1/auth/password",
            headers=lan_headers,
            json={"current_password": "InitialPassword123", "new_password": "RotatedPassword999!"},
        )
        assert pw_res.status_code == 200
        assert duck_client.get("/api/v1/capabilities", headers=duck_headers).status_code == 401

        # Brute-force lockout after 5 wrong login attempts
        for _ in range(5):
            r = duck_client.post(
                "/api/v1/auth/login",
                headers=duck_headers,
                json={"username": "admin", "password": "WrongPassword123"},
            )
            assert r.status_code == 401
        locked = duck_client.post(
            "/api/v1/auth/login",
            headers=duck_headers,
            json={"username": "admin", "password": "RotatedPassword999!"},
        )
        assert locked.status_code == 429
