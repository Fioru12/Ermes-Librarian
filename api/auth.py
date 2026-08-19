"""
api/auth.py
Autenticazione JWT + RBAC + rate limiter.
"""
import logging
import os
import threading
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from config import cfg
from core.rate_limiter import get_rate_limiter

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Auth"], include_in_schema=False)

_security = HTTPBearer(auto_error=False)

_RBAC_CACHE: dict[str, dict] = {}  # key_hash -> user_info
_SESSIONS: dict[str, tuple[dict, float]] = {}
_SESSIONS_LOCK = threading.RLock()
_SESSION_COOKIE = "ermes_session"


def _clear_rbac_cache(key_hash: str | None = None) -> None:
    """Rimuove una entry dalla cache RBAC. Se key_hash è None, svuota tutta la cache."""
    if key_hash is None:
        _RBAC_CACHE.clear()
    else:
        _RBAC_CACHE.pop(key_hash, None)


def _invalidate_sessions_for_user(username: str) -> None:
    """Invalidate browser sessions after a local account security change."""
    with _SESSIONS_LOCK:
        for token, (session_user, _) in list(_SESSIONS.items()):
            if session_user.get("username") == username:
                _SESSIONS.pop(token, None)


def _session_user(token: str | None) -> dict | None:
    if not token:
        return None
    with _SESSIONS_LOCK:
        entry = _SESSIONS.get(token)
        if entry is None:
            return None
        user, expires_at = entry
        if expires_at <= time.time():
            _SESSIONS.pop(token, None)
            return None
        return user


def _authenticate_token(api_key: str) -> dict | None:
    """Accept the configured break-glass key or a managed per-user key."""
    if not api_key:
        return None
    if cfg.API_KEY and secrets.compare_digest(api_key, cfg.API_KEY):
        return {"username": "api-admin", "role": "admin"}
    from core.governance import authenticate_by_api_key
    return authenticate_by_api_key(api_key)


def _verify_api_key(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict:
    """Fail closed: a valid browser session or Bearer key is mandatory."""
    user = _session_user(request.cookies.get(_SESSION_COOKIE))
    if user is not None:
        # Browser sessions must follow the current local-account state. This
        # makes a deactivation or a role change effective immediately instead
        # of waiting for the session TTL to expire.
        from core.governance import list_users
        current = next((item for item in list_users(cfg.USERS_FILE) if item.get("username") == user.get("username")), None)
        if current is None or not current.get("active", True):
            _invalidate_sessions_for_user(str(user.get("username", "")))
            user = None
        else:
            user = {"username": current["username"], "role": current.get("role", "viewer")}
    if user is None and creds is not None:
        user = _authenticate_token(creds.credentials)
    if user is not None:
        return user

    if not cfg.API_KEY and not cfg.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Autenticazione non configurata")
    raise HTTPException(status_code=401, detail="Autenticazione richiesta")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


@router.post("/api/auth/login", include_in_schema=False)
def login(request: LoginRequest, response: Response) -> dict:
    if not cfg.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Login locale non configurato")
    from core.governance import authenticate_user, ensure_default_admin

    ensure_default_admin(cfg.USERS_FILE, cfg.ADMIN_USERNAME, cfg.ADMIN_PASSWORD)
    user = authenticate_user(cfg.USERS_FILE, request.username.strip(), request.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + max(1, cfg.SESSION_TTL_HOURS) * 3600
    with _SESSIONS_LOCK:
        _SESSIONS[token] = (user, expires_at)
    response.set_cookie(
        _SESSION_COOKIE,
        token,
        max_age=max(1, cfg.SESSION_TTL_HOURS) * 3600,
        httponly=True,
        samesite="lax",
        # Local development commonly binds 0.0.0.0 but is still served over
        # HTTP. Production deployments must terminate TLS before using the UI.
        secure=cfg.HOST not in {"127.0.0.1", "localhost", "0.0.0.0"},
    )
    return {"username": user["username"], "role": user["role"]}


@router.post("/api/auth/logout", include_in_schema=False)
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(_SESSION_COOKIE)
    if token:
        with _SESSIONS_LOCK:
            _SESSIONS.pop(token, None)
    response.delete_cookie(_SESSION_COOKIE)
    return {"ok": True}


@router.get("/api/auth/me", include_in_schema=False)
def current_user(user: dict = Depends(_verify_api_key)) -> dict:
    return user


def _require_role(min_role: str = "viewer"):
    """Factory per dependency che richiede un ruolo minimo."""
    def role_checker(user: dict = Depends(_verify_api_key)) -> dict:
        from core.governance import has_min_role
        user_role = user.get("role", "viewer")
        if not has_min_role(user_role, min_role):
            raise HTTPException(
                status_code=403,
                detail=f"Ruolo '{user_role}' non sufficiente. Serve almeno '{min_role}'.",
            )
        return user
    return role_checker


def _rate_limit(req: Request) -> str:
    client_ip = req.client.host if req.client else "unknown"
    identifier = f"api_{client_ip}"
    allowed, reason = get_rate_limiter().check_request_rate(identifier)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)
    return identifier
