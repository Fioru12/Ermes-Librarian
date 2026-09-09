"""
api/auth.py
Autenticazione JWT + RBAC + rate limiter.
"""

import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from config import cfg
from core.rate_limiter import get_rate_limiter
from core.session_store import session_store as _session_store

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Auth"], include_in_schema=False)

_security = HTTPBearer(auto_error=False)

_RBAC_CACHE: dict[str, dict] = {}  # key_hash -> user_info
_SESSION_COOKIE = "ermes_session"

# Le sessioni stanno sull'archivio condiviso, non in un dizionario di
# processo: vedi core/session_store.py per il perche'.
session_store = _session_store


def _clear_rbac_cache(key_hash: str | None = None) -> None:
    """Rimuove una entry dalla cache RBAC. Se key_hash è None, svuota tutta la cache."""
    if key_hash is None:
        _RBAC_CACHE.clear()
    else:
        _RBAC_CACHE.pop(key_hash, None)


def _invalidate_sessions_for_user(username: str) -> None:
    """Invalidate browser sessions after a local account security change.

    Passa dall'archivio condiviso, quindi la disattivazione di un utente ha
    effetto su tutte le istanze e non solo su quella che ha ricevuto la
    chiamata.
    """
    session_store.delete_for_user(username)


def _session_user(token: str | None) -> dict | None:
    return session_store.get(token)


def _validate_oidc_jwt(token: str) -> dict | None:
    """Valida un token JWT emesso da un provider OIDC aziendale.

    La verifica crittografica (firma, algoritmo, scadenza, `iss`, `aud`) vive
    in `core/oidc_keys.py`; qui resta solo la traduzione dei claim in un
    utente Ermes. La separazione non e' estetica: la versione precedente
    faceva le due cose insieme e si limitava a decodificare il payload in
    base64 senza controllare la firma, quindi un token scritto a mano
    otteneva il ruolo che dichiarava.
    """
    if not token or token.count(".") != 2:
        return None
    try:
        from core.oidc_keys import verify_signed_claims

        claims = verify_signed_claims(token)
        if claims is None:
            return None

        username = claims.get("preferred_username") or claims.get("email") or claims.get("sub") or "oidc-user"
        roles_val = claims.get(cfg.OIDC_ROLES_CLAIM, [])
        if isinstance(roles_val, dict) and "roles" in roles_val:
            roles_val = roles_val["roles"]
        if isinstance(roles_val, str):
            roles_val = [roles_val]

        role = "viewer"
        roles_lower = [str(r).lower() for r in roles_val]
        if any(r in {"admin", "ermes-admin", "administrator"} for r in roles_lower):
            role = "admin"
        elif any(r in {"editor", "ermes-editor"} for r in roles_lower):
            role = "editor"

        groups_val = claims.get(cfg.OIDC_GROUPS_CLAIM, [])
        if isinstance(groups_val, str):
            groups_val = [groups_val]
        groups = [str(g) for g in groups_val if g] if isinstance(groups_val, list) else []

        return {"username": str(username), "role": role, "provider": "oidc", "groups": groups}
    except Exception as e:
        _logger.warning("OIDC token validation error: %s", e)
        return None


def _authenticate_token(api_key: str) -> dict | None:
    """Accept the configured break-glass key, a managed per-user key, or an OIDC Bearer token."""
    if not api_key:
        return None
    if cfg.API_KEY and secrets.compare_digest(api_key, cfg.API_KEY):
        return {"username": "api-admin", "role": "admin"}
    if cfg.OIDC_ENABLED and api_key.count(".") == 2:
        oidc_user = _validate_oidc_jwt(api_key)
        if oidc_user:
            return oidc_user
    from core.governance import authenticate_by_api_key

    return authenticate_by_api_key(api_key)


def _verify_api_key(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict:
    """Fail closed: a valid browser session or Bearer key is mandatory."""
    user = _session_user(request.cookies.get(_SESSION_COOKIE))
    if user is not None and user.get("provider") != "oidc":
        # Browser sessions must follow the current local-account state.
        from core.governance import list_users

        current = next(
            (item for item in list_users(cfg.USERS_FILE) if item.get("username") == user.get("username")), None
        )
        if current is None or not current.get("active", True):
            _invalidate_sessions_for_user(str(user.get("username", "")))
            user = None
        else:
            user = {"username": current["username"], "role": current.get("role", "viewer")}
    if user is None and creds is not None:
        user = _authenticate_token(creds.credentials)
    if user is not None:
        return user

    if not cfg.API_KEY and not cfg.ADMIN_PASSWORD and not cfg.OIDC_ENABLED:
        raise HTTPException(status_code=503, detail="Autenticazione non configurata")
    raise HTTPException(status_code=401, detail="Autenticazione richiesta")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class OidcSessionRequest(BaseModel):
    id_token: str = Field(min_length=10)


@router.get("/api/auth/oidc/config", include_in_schema=False)
def oidc_config() -> dict:
    """Restituisce la configurazione pubblica OIDC per il client web."""
    return {
        "enabled": cfg.OIDC_ENABLED,
        "issuer": cfg.OIDC_ISSUER,
        "client_id": cfg.OIDC_CLIENT_ID,
        "audience": cfg.OIDC_AUDIENCE,
    }


@router.post("/api/auth/oidc/session", include_in_schema=False)
def oidc_session_login(request: OidcSessionRequest, response: Response) -> dict:
    """Crea una sessione browser a partire da un token OIDC verificato."""
    if not cfg.OIDC_ENABLED:
        raise HTTPException(status_code=503, detail="Autenticazione SSO/OIDC non abilitata")
    user = _validate_oidc_jwt(request.id_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Token OIDC non valido o scaduto")

    token = secrets.token_urlsafe(32)
    expires_at = time.time() + max(1, cfg.SESSION_TTL_HOURS) * 3600
    session_store.create(token, user, expires_at)
    response.set_cookie(
        _SESSION_COOKIE,
        token,
        max_age=max(1, cfg.SESSION_TTL_HOURS) * 3600,
        httponly=True,
        samesite="lax",
        secure=cfg.HOST not in {"127.0.0.1", "localhost", "0.0.0.0"},  # nosec B104: binding check, not binding
    )
    return {"username": user["username"], "role": user["role"], "provider": "oidc"}


@router.post("/api/auth/login", include_in_schema=False)
def login(request: LoginRequest, response: Response) -> dict:
    if not cfg.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Login locale non configurato")
    from core.governance import authenticate_user, ensure_default_admin

    user = authenticate_user(cfg.USERS_FILE, request.username.strip(), request.password)
    if user is None:
        ensure_default_admin(cfg.USERS_FILE, cfg.ADMIN_USERNAME, cfg.ADMIN_PASSWORD)
        user = authenticate_user(cfg.USERS_FILE, request.username.strip(), request.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Credenziali non valide")
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + max(1, cfg.SESSION_TTL_HOURS) * 3600
    session_store.create(token, user, expires_at)
    response.set_cookie(
        _SESSION_COOKIE,
        token,
        max_age=max(1, cfg.SESSION_TTL_HOURS) * 3600,
        httponly=True,
        samesite="lax",
        # Local development commonly binds 0.0.0.0 but is still served over
        # HTTP. Production deployments must terminate TLS before using the UI.
        secure=cfg.HOST not in {"127.0.0.1", "localhost", "0.0.0.0"},  # nosec B104: binding check, not binding
    )
    return {"username": user["username"], "role": user["role"]}


@router.post("/api/auth/logout", include_in_schema=False)
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(_SESSION_COOKIE)
    if token:
        session_store.delete(token)
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


# ============================================================
# Admin: mapping gruppi OIDC -> ACL biblioteche
# ============================================================


class GroupMappingRequest(BaseModel):
    group: str = Field(min_length=1, max_length=200)
    library_id: str = Field(min_length=1, max_length=100)
    role: str = Field(pattern="^(viewer|editor)$")


class GroupMappingDeleteRequest(BaseModel):
    group: str = Field(min_length=1, max_length=200)
    library_id: str = Field(min_length=1, max_length=100)


@router.get("/api/admin/oidc/group-mappings", include_in_schema=False)
def list_group_mappings(_user: dict = Depends(_require_role("admin"))) -> dict:
    from core.governance import load_oidc_group_mappings

    return {"mappings": load_oidc_group_mappings()}


@router.put("/api/admin/oidc/group-mappings", include_in_schema=False)
def upsert_group_mapping(request: GroupMappingRequest, user: dict = Depends(_require_role("admin"))) -> dict:
    from core.governance import append_audit, set_oidc_group_mapping

    try:
        entry = set_oidc_group_mapping(request.group, request.library_id, request.role)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    append_audit(cfg.AUDIT_FILE, "oidc_group_mapping_upsert", user.get("username", "unknown"), detail=entry)
    return entry


@router.delete("/api/admin/oidc/group-mappings", include_in_schema=False)
def delete_group_mapping(request: GroupMappingDeleteRequest, user: dict = Depends(_require_role("admin"))) -> dict:
    from core.governance import append_audit, remove_oidc_group_mapping

    removed = remove_oidc_group_mapping(request.group, request.library_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Mapping non trovato")
    append_audit(
        cfg.AUDIT_FILE,
        "oidc_group_mapping_delete",
        user.get("username", "unknown"),
        detail={"group": request.group, "library_id": request.library_id},
    )
    return {"ok": True}
