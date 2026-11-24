"""Persistent scrypt user store and HMAC-SHA256 signed session tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,32}$")
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_DUMMY_SALT = b"0123456789abcdef"


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64_decode(val: str) -> bytes:
    pad = "=" * (-len(val) % 4)
    return base64.urlsafe_b64decode(val + pad)


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=actual_salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return actual_salt.hex(), digest.hex()


def _pw_version(pw_hash_hex: str) -> str:
    return hashlib.sha256(pw_hash_hex.encode("ascii")).hexdigest()[:12]


class AuthStore:
    """Thread-safe local JSON user store (kept isolated from ephemeral /buffer)."""

    def __init__(self, auth_data_dir: Path) -> None:
        self.dir = auth_data_dir
        self.file_path = self.dir / "users.json"
        self._lock = threading.RLock()

    def ensure_initialized(self) -> None:
        with self._lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            if not self.file_path.exists():
                initial = {
                    "secret_key": secrets.token_hex(32),
                    "users": {},
                }
                self._write_atomic(initial)

    def _read_data(self) -> dict[str, Any]:
        self.ensure_initialized()
        return json.loads(self.file_path.read_text(encoding="utf-8"))

    def _write_atomic(self, data: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.dir / f"users.{secrets.token_hex(6)}.tmp"
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, self.file_path)
        try:
            os.chmod(self.file_path, 0o600)
        except OSError:
            pass

    @staticmethod
    def validate_username(username: str) -> str:
        cleaned = username.strip()
        if not _USERNAME_RE.fullmatch(cleaned):
            raise ValueError(
                "Benutzername muss 3-32 Zeichen lang sein (Buchstaben, Zahlen, '.', '_' oder '-')."
            )
        return cleaned

    @staticmethod
    def validate_password(password: str) -> str:
        if len(password) < 10:
            raise ValueError("Passwort muss mindestens 10 Zeichen lang sein.")
        if len(password) > 128:
            raise ValueError("Passwort darf hoechstens 128 Zeichen lang sein.")
        return password

    def has_users(self) -> bool:
        with self._lock:
            data = self._read_data()
            return bool(data.get("users"))

    def list_users(self) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read_data()
            return [
                {
                    "username": uname,
                    "created_at": info.get("created_at"),
                    "updated_at": info.get("updated_at"),
                }
                for uname, info in sorted(data.get("users", {}).items())
            ]

    def create_user(self, username: str, password: str) -> str:
        uname = self.validate_username(username)
        pw = self.validate_password(password)
        with self._lock:
            data = self._read_data()
            users = data.setdefault("users", {})
            if any(existing.lower() == uname.lower() for existing in users):
                raise ValueError("Dieser Benutzername existiert bereits.")
            salt_hex, hash_hex = _hash_password(pw)
            now = int(time.time())
            users[uname] = {
                "salt": salt_hex,
                "hash": hash_hex,
                "created_at": now,
                "updated_at": now,
            }
            self._write_atomic(data)
            return uname

    def verify_credentials(self, username: str, password: str) -> str | None:
        cleaned = username.strip()
        with self._lock:
            data = self._read_data()
            users = data.get("users", {})
            matched_key = next((k for k in users if k.lower() == cleaned.lower()), None)
            if not matched_key:
                # Dummy scrypt run mitigates user enumeration via response timing
                _hash_password(password[:128], salt=_DUMMY_SALT)
                return None
            record = users[matched_key]
            salt = bytes.fromhex(record["salt"])
            _, candidate_hex = _hash_password(password[:128], salt=salt)
            if hmac.compare_digest(record["hash"], candidate_hex):
                return matched_key
            return None

    def change_password(self, username: str, current_password: str, new_password: str) -> None:
        new_pw = self.validate_password(new_password)
        with self._lock:
            verified = self.verify_credentials(username, current_password)
            if not verified:
                raise PermissionError("Aktuelles Passwort ist nicht korrekt.")
            data = self._read_data()
            salt_hex, hash_hex = _hash_password(new_pw)
            data["users"][verified]["salt"] = salt_hex
            data["users"][verified]["hash"] = hash_hex
            data["users"][verified]["updated_at"] = int(time.time())
            self._write_atomic(data)

    def delete_user(self, username: str) -> None:
        with self._lock:
            data = self._read_data()
            users = data.get("users", {})
            if username not in users:
                raise KeyError("Benutzer nicht gefunden.")
            if len(users) <= 1:
                raise ValueError("Der letzte verbleibende Benutzer kann nicht geloescht werden.")
            del users[username]
            self._write_atomic(data)

    def create_session_token(self, username: str, ttl_seconds: int) -> tuple[str, str, int]:
        with self._lock:
            data = self._read_data()
            user = data.get("users", {}).get(username)
            if not user:
                raise KeyError("Benutzer nicht gefunden.")
            secret = bytes.fromhex(data["secret_key"])
            now = int(time.time())
            exp = now + ttl_seconds
            jti = secrets.token_hex(16)
            payload = {
                "sub": username,
                "iat": now,
                "exp": exp,
                "jti": jti,
                "pw_ver": _pw_version(user["hash"]),
            }
        body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        sig = _b64_encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
        return f"{body}.{sig}", jti, exp

    def verify_session_token(self, token: str | None) -> dict[str, Any] | None:
        if not token or "." not in token:
            return None
        try:
            body, sig = token.split(".", 1)
            with self._lock:
                data = self._read_data()
                secret = bytes.fromhex(data["secret_key"])
                expected_sig = _b64_encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
                if not hmac.compare_digest(sig, expected_sig):
                    return None
                payload = json.loads(_b64_decode(body).decode("utf-8"))
                now = int(time.time())
                if int(payload.get("exp", 0)) <= now:
                    return None
                user = data.get("users", {}).get(payload.get("sub", ""))
                if not user:
                    return None
                if not hmac.compare_digest(payload.get("pw_ver", ""), _pw_version(user["hash"])):
                    return None
                return payload
        except Exception:
            return None
