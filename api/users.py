"""
api/users.py
User management (admin) — RBAC.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _clear_rbac_cache, _invalidate_sessions_for_user, _require_role
from config import cfg

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["RBAC"])


class ApiKeyResponse(BaseModel):
    success: bool
    api_key: str | None = None
    username: str
    role: str
    message: str = ""


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="Nome utente")
    role: str = Field(default="viewer", description="Ruolo: admin, editor, viewer")


class CreateLocalAccountRequest(CreateUserRequest):
    password: str = Field(..., min_length=8, max_length=256, description="Password iniziale dell'account web")


class UpdateLocalAccountRequest(BaseModel):
    role: str | None = Field(default=None, description="Nuovo ruolo: admin, editor, viewer")
    password: str | None = Field(default=None, min_length=8, max_length=256, description="Nuova password")
    active: bool | None = Field(default=None, description="Abilita o disabilita l'accesso web")


def _validated_username_and_role(username_value: str, role_value: str) -> tuple[str, str]:
    from core.input_validator import sanitize_username

    username = sanitize_username(username_value.strip().lower())
    if not username or len(username) < 2:
        raise HTTPException(400, "Nome utente non valido (min 2 caratteri alfanumerici)")
    role = role_value.strip().lower()
    if role not in {"admin", "editor", "viewer"}:
        raise HTTPException(400, f"Ruolo non valido: {role}")
    return username, role


@router.get("/api/accounts", summary="Elenco account web locali")
async def list_local_accounts(user: dict = Depends(_require_role("admin"))):
    """List password-based local accounts without exposing authentication data."""
    from core.governance import list_users
    return {"users": list_users(cfg.USERS_FILE)}


@router.post("/api/accounts", summary="Crea un account web locale")
async def create_local_account(req: CreateLocalAccountRequest, user: dict = Depends(_require_role("admin"))):
    """Create a local browser-login account; password is never returned or logged."""
    from core.governance import append_audit, create_or_update_user, list_users, validate_password_strength

    username, role = _validated_username_and_role(req.username, req.role)
    if any(item.get("username") == username for item in list_users(cfg.USERS_FILE)):
        raise HTTPException(409, "Esiste gia un account con questo nome utente")
    valid, reason = validate_password_strength(req.password)
    if not valid:
        raise HTTPException(422, reason)
    create_or_update_user(cfg.USERS_FILE, username, role, req.password, active=True)
    append_audit(cfg.AUDIT_FILE, "local_account_created", user.get("username", "admin"), {"username": username, "role": role})
    return {"success": True, "username": username, "role": role, "message": "Account locale creato"}


@router.patch("/api/accounts/{username}", summary="Aggiorna un account web locale")
async def update_local_account(username: str, req: UpdateLocalAccountRequest, user: dict = Depends(_require_role("admin"))):
    """Change role, password or active state without ever returning credentials."""
    from core.governance import append_audit, create_or_update_user, list_users, validate_password_strength
    from core.input_validator import sanitize_username

    username = sanitize_username(username.strip().lower())
    existing_accounts = list_users(cfg.USERS_FILE)
    existing = next((item for item in existing_accounts if item.get("username") == username), None)
    if existing is None:
        raise HTTPException(404, "Account locale non trovato")
    if req.role is None and req.password is None and req.active is None:
        raise HTTPException(400, "Nessuna modifica richiesta")

    role = existing.get("role", "viewer") if req.role is None else req.role.strip().lower()
    if role not in {"admin", "editor", "viewer"}:
        raise HTTPException(400, f"Ruolo non valido: {role}")
    active = bool(existing.get("active", True)) if req.active is None else bool(req.active)
    actor_username = user.get("username", "")
    bootstrap_username = cfg.ADMIN_USERNAME.strip().lower()
    if username == bootstrap_username and (not active or role != "admin" or req.password is not None):
        raise HTTPException(400, "L'account amministratore iniziale si modifica solo tramite la configurazione locale")
    if username == actor_username and (not active or role != "admin"):
        raise HTTPException(400, "Non puoi disattivare o ridurre il tuo stesso account amministratore")
    if req.password is not None:
        valid, reason = validate_password_strength(req.password)
        if not valid:
            raise HTTPException(422, reason)

    # Always retain at least one active administrator, avoiding local lockout.
    active_admins = sum(
        1
        for account in existing_accounts
        if account.get("username") != username and account.get("role") == "admin" and account.get("active", True)
    )
    if role == "admin" and active:
        active_admins += 1
    if active_admins < 1:
        raise HTTPException(400, "Deve rimanere almeno un amministratore attivo")

    create_or_update_user(cfg.USERS_FILE, username, role, req.password or "", active=active)
    _invalidate_sessions_for_user(username)
    append_audit(
        cfg.AUDIT_FILE,
        "local_account_updated",
        actor_username or "admin",
        {"username": username, "role": role, "active": active, "password_changed": req.password is not None},
    )
    return {"success": True, "username": username, "role": role, "active": active, "message": "Account locale aggiornato"}


@router.get("/api/users", summary="Elenco utenti con API key")
async def list_api_users(user: dict = Depends(_require_role("admin"))):
    from core.governance import list_api_keys
    return {"users": list_api_keys()}


@router.post("/api/users", summary="Crea un nuovo utente con API key")
async def create_api_user(req: CreateUserRequest, user: dict = Depends(_require_role("admin"))):
    from core.governance import set_user_api_key
    username, role = _validated_username_and_role(req.username, req.role)

    api_key = set_user_api_key(username, role=role)
    from core.governance import append_audit
    append_audit(cfg.AUDIT_FILE, "user_api_key_created", user.get("username", "admin"), {"username": username, "role": role})

    return ApiKeyResponse(
        success=True,
        api_key=api_key,
        username=username,
        role=role,
        message="API key creata. SALVALA: non sarà più mostrata.",
    )


@router.post("/api/users/{username}/rotate-key", summary="Rigenera la API key di un utente")
async def rotate_api_key(username: str, user: dict = Depends(_require_role("admin"))):
    from core.governance import list_api_keys, revoke_user_api_key, set_user_api_key

    username = username.strip().lower()
    existing_user = next((item for item in list_api_keys() if item.get("username") == username), None)
    if existing_user is None:
        raise HTTPException(404, f"Utente '{username}' non trovato")
    if not revoke_user_api_key(username):
        raise HTTPException(404, f"Utente '{username}' non trovato")

    _clear_rbac_cache()
    # Rotation changes the secret only; it must never silently change access.
    role = existing_user.get("role", "viewer")
    new_key = set_user_api_key(username, role=role)
    from core.governance import append_audit
    append_audit(cfg.AUDIT_FILE, "user_api_key_rotated", user.get("username", "admin"), {"username": username})

    return {
        "success": True,
        "api_key": new_key,
        "username": username,
        "role": role,
        "message": "API key rigenerata. SALVALA: non sarà più mostrata.",
    }


@router.delete("/api/users/{username}", summary="Revoca la API key di un utente")
async def delete_api_user(username: str, user: dict = Depends(_require_role("admin"))):
    from core.governance import revoke_user_api_key

    username = username.strip().lower()
    if not revoke_user_api_key(username):
        raise HTTPException(404, f"Utente '{username}' non trovato")

    from core.governance import append_audit
    append_audit(cfg.AUDIT_FILE, "user_api_key_revoked", user.get("username", "admin"), {"username": username})
    _clear_rbac_cache()

    return {"success": True, "message": f"API key di '{username}' revocata"}
