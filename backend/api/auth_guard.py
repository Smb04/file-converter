"""Defense-in-depth authentication & strict local-LAN-only admin guard."""

from __future__ import annotations

import ipaddress
from typing import Any

from fastapi import HTTPException, Request, status

from backend.shared.config import Settings, get_settings

SESSION_COOKIE_NAME = "converter_session"

_PROXY_MARKER_HEADERS = (
    "x-external-proxy",
    "x-incoming-xff",
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "forwarded",
    "cf-connecting-ip",
    "cf-ray",
)


def get_auth_store(request: Request) -> Any:
    return request.app.state.auth_store


def get_client_ip(request: Request) -> str:
    # Gateway overwrites X-Gateway-Client-IP with Nginx $remote_addr
    gw_ip = request.headers.get("x-gateway-client-ip")
    if gw_ip:
        return gw_ip.strip()
    if request.client and request.client.host:
        return request.client.host.strip()
    return ""


def is_https_request(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    proto = request.headers.get("x-forwarded-proto", "").lower().strip()
    return proto == "https"


def _extract_host_without_port(raw_host: str) -> str:
    host = raw_host.strip().lower()
    if not host:
        return ""
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end != -1 else host
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    return host


def _is_direct_local_host(host: str) -> bool:
    if not host:
        return False
    if host in {"localhost", "testserver"} or host.endswith(".local"):
        return True
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        # Reject any public domain / duckdns.org hostname even if tunnelled over private IPs
        return False


def _ip_in_cidrs(ip_str: str, cidrs: tuple[str, ...]) -> bool:
    if not ip_str:
        return False
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            if addr in net:
                return True
        except ValueError:
            continue
    return False


def is_local_admin_request(request: Request, settings: Settings | None = None) -> bool:
    """Allow user/password management strictly via direct local LAN access (never via DuckDNS/VPS)."""
    cfg = settings or get_settings()

    # 1. Reject any external proxy / tunnel / CDN headers
    for hdr in _PROXY_MARKER_HEADERS:
        if request.headers.get(hdr):
            return False

    # 2. Require direct local IP / localhost / .local Host header (rejects *.duckdns.org)
    host = _extract_host_without_port(request.headers.get("host", ""))
    if not _is_direct_local_host(host):
        return False

    # 3. Require client IP inside configured LOCAL_ADMIN_CIDRS
    client_ip = get_client_ip(request)
    return _ip_in_cidrs(client_ip, cfg.local_admin_cidrs)


def require_local_admin(request: Request) -> None:
    if not is_local_admin_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registrierung und Benutzerverwaltung sind aus Sicherheitsgruenden nur ueber die direkte lokale IP im Heimnetz moeglich.",
        )


def optional_authenticated_user(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    store = get_auth_store(request)
    payload = store.verify_session_token(token)
    if not payload:
        return None
    jti = payload.get("jti")
    r = request.app.state.redis
    if jti and r.exists(f"revoked_jti:{jti}"):
        return None
    return str(payload["sub"])


def require_authenticated_user(request: Request) -> str:
    username = optional_authenticated_user(request)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Anmeldung erforderlich.",
        )
    return username
