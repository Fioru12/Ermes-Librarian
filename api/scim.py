"""api/scim.py
SCIM 2.0 (RFC 7643 / RFC 7644) Directory Sync Gateway for Ermes Knowledge.

Provides automated provisioning, synchronization, and de-provisioning of users
and identity groups from enterprise Identity Providers such as:
- Microsoft Entra ID (Azure AD)
- Okta
- PingFederate / CyberArk / OneLogin

Endpoints:
- GET  /scim/v2/ServiceProviderConfig
- GET  /scim/v2/Schemas
- GET  /scim/v2/Users
- POST /scim/v2/Users
- GET  /scim/v2/Users/{id}
- PUT  /scim/v2/Users/{id}
- PATCH /scim/v2/Users/{id}
- DELETE /scim/v2/Users/{id}
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from api.auth import _invalidate_sessions_for_user
from config import cfg
from core.governance import append_audit, create_or_update_user, delete_user, list_users
from core.input_validator import sanitize_username

_logger = logging.getLogger("ermes.scim")

router = APIRouter(prefix="/scim/v2", tags=["SCIM 2.0 Directory Sync"])

USER_SCHEMA_URI = "urn:ietf:params:scim:schemas:core:2.0:User"
LIST_SCHEMA_URI = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
PATCH_SCHEMA_URI = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
ERROR_SCHEMA_URI = "urn:ietf:params:scim:api:messages:2.0:Error"


# ==========================================
# Auth Dependency for SCIM Gateway
# ==========================================

def _verify_scim_auth(authorization: str | None = Header(default=None)) -> dict[str, str]:
    """Valida il Bearer token SCIM configurato o in alternativa la Master API Key."""
    if not getattr(cfg, "SCIM_ENABLED", True):
        raise HTTPException(status_code=503, detail="SCIM Directory Sync non abilitato")

    scim_token = getattr(cfg, "SCIM_TOKEN", "").strip()
    master_key = getattr(cfg, "API_KEY", "").strip()

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticazione Bearer richiesta per endpoint SCIM",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split("Bearer ", 1)[1].strip()

    # Valida o con token dedicato SCIM o con API Key di sistema
    valid = False
    if scim_token and secrets.compare_digest(token, scim_token):
        valid = True
    elif master_key and secrets.compare_digest(token, master_key):
        valid = True

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali SCIM non valide",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"client": "scim_idp", "role": "admin"}


# ==========================================
# Helper: Formattazione Utente SCIM
# ==========================================

def _format_scim_user(user: dict[str, Any]) -> dict[str, Any]:
    username = user.get("username", "")
    role = user.get("role", "viewer")
    active = bool(user.get("active", True))

    return {
        "schemas": [USER_SCHEMA_URI],
        "id": username,
        "userName": username,
        "name": {
            "formatted": username,
            "givenName": username,
            "familyName": "",
        },
        "emails": [
            {
                "value": f"{username}@local.domain" if "@" not in username else username,
                "primary": True,
            }
        ],
        "active": active,
        "roles": [{"value": role}],
        "meta": {
            "resourceType": "User",
            "location": f"/scim/v2/Users/{username}",
        },
    }


# ==========================================
# Discovery Endpoints
# ==========================================

@router.get("/ServiceProviderConfig")
def get_service_provider_config(_auth: dict = Depends(_verify_scim_auth)) -> dict[str, Any]:
    """Restituisce le capacità e feature supportate dall'implementazione SCIM di Ermes."""
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "name": "OAuth Bearer Token",
                "description": "Autenticazione tramite Bearer Token per IdP aziendali",
                "specUri": "http://www.rfc-editor.org/info/rfc6750",
                "type": "oauthbearertoken",
                "primary": True,
            }
        ],
    }


@router.get("/Schemas")
def get_schemas(_auth: dict = Depends(_verify_scim_auth)) -> dict[str, Any]:
    """Discovery degli schemi SCIM disponibili."""
    return {
        "schemas": [LIST_SCHEMA_URI],
        "totalResults": 1,
        "itemsPerPage": 1,
        "startIndex": 1,
        "Resources": [
            {
                "id": USER_SCHEMA_URI,
                "name": "User",
                "description": "Schema utente Ermes Knowledge per provisioning",
                "attributes": [
                    {"name": "userName", "type": "string", "required": True},
                    {"name": "active", "type": "boolean", "required": False},
                    {"name": "roles", "type": "complex", "multiValued": True},
                ],
            }
        ],
    }


# ==========================================
# User Resource Models & Endpoints
# ==========================================

class SCIMUserCreate(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [USER_SCHEMA_URI])
    userName: str = Field(..., min_length=2, max_length=100)  # noqa: N815
    name: dict[str, Any] | None = None
    emails: list[dict[str, Any]] | None = None
    active: bool = True
    roles: list[dict[str, Any]] | None = None
    password: str | None = None


class SCIMUserPatch(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [PATCH_SCHEMA_URI])
    Operations: list[dict[str, Any]] = Field(...)  # noqa: N815


@router.get("/Users")
def list_scim_users(
    filter: str | None = Query(default=None, description="Filtro SCIM es. userName eq 'mario'"),
    start_index: int = Query(default=1, ge=1, alias="startIndex"),
    count: int = Query(default=50, ge=1, le=100),
    _auth: dict = Depends(_verify_scim_auth),
) -> dict[str, Any]:
    """Elenca gli utenti con supporto a paginazione e filtro di eguaglianza."""
    all_users = list_users(cfg.USERS_FILE)

    if filter:
        # Supporto standard a: userName eq "valore"
        filter_parts = filter.split(" eq ")
        if len(filter_parts) == 2 and filter_parts[0].strip().lower() == "username":
            target_username = filter_parts[1].strip(" '\"").lower()
            all_users = [u for u in all_users if u.get("username", "").lower() == target_username]

    total_results = len(all_users)
    start_idx = start_index - 1
    page_users = all_users[start_idx : start_idx + count]

    return {
        "schemas": [LIST_SCHEMA_URI],
        "totalResults": total_results,
        "startIndex": start_index,
        "itemsPerPage": len(page_users),
        "Resources": [_format_scim_user(u) for u in page_users],
    }


@router.post("/Users", status_code=status.HTTP_201_CREATED)
def create_scim_user(
    body: SCIMUserCreate,
    _auth: dict = Depends(_verify_scim_auth),
) -> dict[str, Any]:
    """Provisioning di un nuovo utente da IdP aziendale."""
    raw_username = body.userName.split("@")[0] if "@" in body.userName else body.userName
    username = sanitize_username(raw_username)
    if not username or len(username) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="userName non valido per la policy di sistema",
        )

    # Verifica duplicato
    existing = next((u for u in list_users(cfg.USERS_FILE) if u.get("username") == username), None)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Utente '{username}' già registrato nel sistema",
        )

    # Determina ruolo (default 'viewer')
    role = "viewer"
    if body.roles:
        for r in body.roles:
            val = str(r.get("value", "")).lower()
            if val in {"admin", "editor", "viewer"}:
                role = val
                break

    pwd = body.password or secrets.token_urlsafe(24)
    create_or_update_user(cfg.USERS_FILE, username, role, pwd, active=body.active)

    append_audit(
        cfg.AUDIT_FILE,
        "scim_user_provisioned",
        "scim_idp",
        {"username": username, "role": role, "active": body.active},
    )

    created_user = next((u for u in list_users(cfg.USERS_FILE) if u.get("username") == username), None)
    return _format_scim_user(created_user or {"username": username, "role": role, "active": body.active})


@router.get("/Users/{user_id}")
def get_scim_user(
    user_id: str,
    _auth: dict = Depends(_verify_scim_auth),
) -> dict[str, Any]:
    """Recupera il record SCIM di un utente per id/username."""
    target = user_id.strip().lower()
    user = next((u for u in list_users(cfg.USERS_FILE) if u.get("username", "").lower() == target), None)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utente non trovato")
    return _format_scim_user(user)


@router.put("/Users/{user_id}")
def replace_scim_user(
    user_id: str,
    body: SCIMUserCreate,
    _auth: dict = Depends(_verify_scim_auth),
) -> dict[str, Any]:
    """Sostituisce gli attributi di un utente (full update)."""
    target = user_id.strip().lower()
    user = next((u for u in list_users(cfg.USERS_FILE) if u.get("username", "").lower() == target), None)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utente non trovato")

    role = "viewer"
    if body.roles:
        for r in body.roles:
            val = str(r.get("value", "")).lower()
            if val in {"admin", "editor", "viewer"}:
                role = val
                break

    create_or_update_user(
        cfg.USERS_FILE,
        target,
        role,
        body.password or "",
        active=body.active,
    )
    if not body.active:
        _invalidate_sessions_for_user(target)

    append_audit(
        cfg.AUDIT_FILE,
        "scim_user_replaced",
        "scim_idp",
        {"username": target, "role": role, "active": body.active},
    )

    updated = next((u for u in list_users(cfg.USERS_FILE) if u.get("username", "").lower() == target), None)
    return _format_scim_user(updated or {"username": target, "role": role, "active": body.active})


@router.patch("/Users/{user_id}")
def patch_scim_user(
    user_id: str,
    body: SCIMUserPatch,
    _auth: dict = Depends(_verify_scim_auth),
) -> dict[str, Any]:
    """Aggiornamento parziale (de-provisioning, disattivazione, cambio ruolo)."""
    target = user_id.strip().lower()
    user = next((u for u in list_users(cfg.USERS_FILE) if u.get("username", "").lower() == target), None)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utente non trovato")

    active = user.get("active", True)
    role = user.get("role", "viewer")

    for op in body.Operations:
        op_type = str(op.get("op", "")).lower()
        path = str(op.get("path", "")).lower()
        val = op.get("value")

        if op_type in {"replace", "add"}:
            if path == "active":
                active = bool(val)
            elif isinstance(val, dict) and "active" in val:
                active = bool(val["active"])
            elif path == "roles":
                if isinstance(val, list) and val:
                    candidate = str(val[0].get("value", "")).lower()
                    if candidate in {"admin", "editor", "viewer"}:
                        role = candidate
            elif isinstance(val, dict) and "roles" in val:
                raw_roles = val.get("roles")
                if isinstance(raw_roles, list) and raw_roles:
                    candidate = str(raw_roles[0].get("value", "")).lower()
                    if candidate in {"admin", "editor", "viewer"}:
                        role = candidate

    create_or_update_user(cfg.USERS_FILE, target, role, "", active=active)

    # De-provisioning immediato: disconnette tutte le sessioni attive dell'utente
    if not active:
        _invalidate_sessions_for_user(target)
        _logger.info("Utente %s disattivato da IdP via SCIM (sessioni revocate)", target)

    append_audit(
        cfg.AUDIT_FILE,
        "scim_user_patched",
        "scim_idp",
        {"username": target, "active": active, "role": role},
    )

    updated = next((u for u in list_users(cfg.USERS_FILE) if u.get("username", "").lower() == target), None)
    return _format_scim_user(updated or {"username": target, "role": role, "active": active})


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scim_user(
    user_id: str,
    _auth: dict = Depends(_verify_scim_auth),
) -> Response:
    """Eliminazione / de-provisioning definitivo dell'utente da IdP."""
    target = user_id.strip().lower()
    _invalidate_sessions_for_user(target)
    deleted = delete_user(cfg.USERS_FILE, target)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utente non trovato")

    append_audit(
        cfg.AUDIT_FILE,
        "scim_user_deleted",
        "scim_idp",
        {"username": target},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
