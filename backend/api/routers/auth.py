"""Authentication and strictly-local user management endpoints."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from backend.api.auth_guard import (
    SESSION_COOKIE_NAME,
    get_auth_store,
    get_client_ip,
    is_https_request,
    is_local_admin_request,
    optional_authenticated_user,
    require_authenticated_user,
    require_local_admin,
)
from backend.api.deps import get_redis
from backend.shared.config import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class RegisterRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _set_session_cookie(response: Response, request: Request, token: str, ttl_seconds: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=is_https_request(request),
        path="/",
    )


def _clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=is_https_request(request),
        path="/",
    )


@router.get("/status")
def auth_status(request: Request) -> dict[str, Any]:
    store = get_auth_store(request)
    username = optional_authenticated_user(request)
    return {
        "authenticated": bool(username),
        "username": username,
        "has_users": store.has_users(),
        "can_register_local": is_local_admin_request(request),
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, r=Depends(get_redis)) -> dict[str, Any]:
    settings = get_settings()
    store = get_auth_store(request)
    client_ip = get_client_ip(request) or "unknown"
    uname_key = payload.username.strip().lower()

    ip_fail_key = f"auth:fail:{client_ip}"
    user_fail_key = f"auth:fail:{client_ip}:{uname_key}"
    ip_fails = int(r.get(ip_fail_key) or 0)
    user_fails = int(r.get(user_fail_key) or 0)

    if ip_fails >= settings.login_max_attempts * 2 or user_fails >= settings.login_max_attempts:
        retry_after = max(60, int(r.ttl(user_fail_key) or settings.login_lockout_seconds))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Zu viele fehlgeschlagene Anmeldeversuche. Bitte {retry_after // 60 + 1} Minuten warten.",
            headers={"Retry-After": str(retry_after)},
        )

    matched_user = store.verify_credentials(payload.username, payload.password)
    if not matched_user:
        r.incr(ip_fail_key)
        r.expire(ip_fail_key, settings.login_lockout_seconds)
        r.incr(user_fail_key)
        r.expire(user_fail_key, settings.login_lockout_seconds)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzername oder Passwort ungueltig.",
        )

    r.delete(ip_fail_key, user_fail_key)
    ttl = settings.session_remember_ttl_seconds if payload.remember_me else settings.session_ttl_seconds
    token, _, _ = store.create_session_token(matched_user, ttl)
    _set_session_cookie(response, request, token, ttl)
    return {"authenticated": True, "username": matched_user}


@router.post("/logout")
def logout(request: Request, response: Response, r=Depends(get_redis)) -> dict[str, bool]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        store = get_auth_store(request)
        payload = store.verify_session_token(token)
        if payload and payload.get("jti"):
            rem_ttl = max(60, int(payload["exp"]) - int(time.time()))
            r.setex(f"revoked_jti:{payload['jti']}", rem_ttl, "1")
    _clear_session_cookie(response, request)
    return {"logged_out": True}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(payload: RegisterRequest, request: Request, response: Response) -> dict[str, Any]:
    require_local_admin(request)
    store = get_auth_store(request)
    settings = get_settings()

    was_empty = not store.has_users()
    if not was_empty:
        # Once the first user exists, creating more accounts locally also requires login
        require_authenticated_user(request)

    try:
        created_username = store.create_user(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if was_empty:
        token, _, _ = store.create_session_token(created_username, settings.session_ttl_seconds)
        _set_session_cookie(response, request, token, settings.session_ttl_seconds)

    return {"created": True, "username": created_username, "auto_logged_in": was_empty}


@router.get("/users")
def list_users(request: Request) -> dict[str, Any]:
    require_local_admin(request)
    require_authenticated_user(request)
    store = get_auth_store(request)
    return {"users": store.list_users()}


@router.post("/password")
def change_password(payload: ChangePasswordRequest, request: Request, response: Response) -> dict[str, bool]:
    require_local_admin(request)
    current_user = require_authenticated_user(request)
    store = get_auth_store(request)
    settings = get_settings()

    try:
        store.change_password(current_user, payload.current_password, payload.new_password)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    token, _, _ = store.create_session_token(current_user, settings.session_ttl_seconds)
    _set_session_cookie(response, request, token, settings.session_ttl_seconds)
    return {"updated": True}


@router.delete("/users/{username}")
def delete_user(username: str, request: Request) -> dict[str, Any]:
    require_local_admin(request)
    current_user = require_authenticated_user(request)
    store = get_auth_store(request)

    if username == current_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Das aktuell angemeldete Konto kann sich nicht selbst loeschen.",
        )

    try:
        store.delete_user(username)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return {"deleted": True, "username": username}
