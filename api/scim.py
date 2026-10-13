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
- GET|POST /scim/v2/Groups, GET|PUT|PATCH|DELETE /scim/v2/Groups/{id}
"""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from api.auth import _invalidate_sessions_for_user
from config import cfg
from core.governance import append_audit, create_or_update_user, delete_user, list_users
from core.input_validator import sanitize_username
from core.scim_groups import scim_group_store

_logger = logging.getLogger("ermes.scim")

router = APIRouter(prefix="/scim/v2", tags=["SCIM 2.0 Directory Sync"])

USER_SCHEMA_URI = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA_URI = "urn:ietf:params:scim:schemas:core:2.0:Group"
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
        "totalResults": 2,
        "itemsPerPage": 2,
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
            },
            {
                "id": GROUP_SCHEMA_URI,
                "name": "Group",
                "description": "Gruppo Ermes: il displayName si mappa sulle biblioteche",
                "attributes": [
                    {"name": "displayName", "type": "string", "required": True},
                    {"name": "members", "type": "complex", "multiValued": True},
                ],
            },
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
    # Un account ricreato piu' tardi con lo stesso nome non deve ritrovarsi
    # nei gruppi di quello eliminato.
    scim_group_store.remove_user_everywhere(target)

    append_audit(
        cfg.AUDIT_FILE,
        "scim_user_deleted",
        "scim_idp",
        {"username": target},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==========================================
# Group Resource (RFC 7643 §4.2)
# ==========================================
#
# Vedi core/scim_groups.py per il perche'. Il `displayName` e' il nome che le
# mappature gruppo -> biblioteca usano; i membri sono gli `id` degli utenti
# SCIM, cioe' i loro username.

_MEMBER_FILTER = re.compile(r'^members\[\s*value\s+eq\s+"([^"]+)"\s*\]$', re.IGNORECASE)


class SCIMGroupCreate(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [GROUP_SCHEMA_URI])
    displayName: str = Field(..., min_length=1, max_length=200)  # noqa: N815
    members: list[dict[str, Any]] | None = None


def _format_scim_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemas": [GROUP_SCHEMA_URI],
        "id": group["id"],
        "displayName": group["display_name"],
        "members": [
            {"value": username, "display": username, "$ref": f"/scim/v2/Users/{username}"}
            for username in group.get("members", [])
        ],
        "meta": {
            "resourceType": "Group",
            "created": group["created_at"],
            "location": f"/scim/v2/Groups/{group['id']}",
        },
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _member_value(item: Any) -> str:
    return str(item.get("value") if isinstance(item, dict) else item).strip()


def _known_usernames(values: list[Any]) -> list[str]:
    """Username esistenti per i membri indicati; 400 se uno non esiste.

    Un membro sconosciuto non si accetta "per dopo": il primo account locale
    creato con quel nome erediterebbe l'accesso del gruppo senza che l'IdP
    lo abbia mai deciso per lui.
    """
    by_lower = {u.get("username", "").lower(): u.get("username", "") for u in list_users(cfg.USERS_FILE)}
    out: list[str] = []
    for item in values:
        raw = _member_value(item)
        username = by_lower.get(raw.lower())
        if not username:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Membro sconosciuto: {raw!r}")
        out.append(username)
    return out


def _group_or_404(group_id: str) -> dict[str, Any]:
    group = scim_group_store.get(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gruppo non trovato")
    return group


def _conflict_if_name_taken(display_name: str, except_id: str | None = None) -> None:
    existing = scim_group_store.find_by_display_name(display_name)
    if existing and existing["id"] != except_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Gruppo {display_name!r} gia' esistente")


@router.get("/Groups")
def list_scim_groups(
    filter: str | None = Query(default=None, description='Filtro SCIM es. displayName eq "Finanza"'),
    start_index: int = Query(default=1, ge=1, alias="startIndex"),
    count: int = Query(default=50, ge=1, le=100),
    _auth: dict = Depends(_verify_scim_auth),
) -> dict[str, Any]:
    groups = scim_group_store.all()
    if filter:
        parts = filter.split(" eq ")
        if len(parts) == 2 and parts[0].strip().lower() == "displayname":
            wanted = parts[1].strip(" '\"")
            groups = [g for g in groups if g["display_name"] == wanted]
    page = groups[start_index - 1 : start_index - 1 + count]
    return {
        "schemas": [LIST_SCHEMA_URI],
        "totalResults": len(groups),
        "startIndex": start_index,
        "itemsPerPage": len(page),
        "Resources": [_format_scim_group(g) for g in page],
    }


@router.post("/Groups", status_code=status.HTTP_201_CREATED)
def create_scim_group(body: SCIMGroupCreate, _auth: dict = Depends(_verify_scim_auth)) -> dict[str, Any]:
    display_name = body.displayName.strip()
    _conflict_if_name_taken(display_name)
    members = _known_usernames(body.members or [])
    group = scim_group_store.create(display_name, members)
    append_audit(cfg.AUDIT_FILE, "scim_group_provisioned", "scim_idp", {"group": display_name, "members": members})
    return _format_scim_group(group)


@router.get("/Groups/{group_id}")
def get_scim_group(group_id: str, _auth: dict = Depends(_verify_scim_auth)) -> dict[str, Any]:
    return _format_scim_group(_group_or_404(group_id))


@router.put("/Groups/{group_id}")
def replace_scim_group(
    group_id: str,
    body: SCIMGroupCreate,
    _auth: dict = Depends(_verify_scim_auth),
) -> dict[str, Any]:
    _group_or_404(group_id)
    display_name = body.displayName.strip()
    _conflict_if_name_taken(display_name, except_id=group_id)
    members = _known_usernames(body.members or [])
    scim_group_store.rename(group_id, display_name)
    scim_group_store.replace_members(group_id, members)
    append_audit(cfg.AUDIT_FILE, "scim_group_replaced", "scim_idp", {"group": display_name, "members": members})
    return _format_scim_group(_group_or_404(group_id))


@router.patch("/Groups/{group_id}")
def patch_scim_group(
    group_id: str,
    body: SCIMUserPatch,
    _auth: dict = Depends(_verify_scim_auth),
) -> dict[str, Any]:
    """Operazioni add/remove/replace sui membri e sul nome.

    Copre le due forme di rimozione che si incontrano: Entra ID manda
    `path: members[value eq "id"]`, Okta `path: members` con l'elenco in
    `value`. Un'operazione non riconosciuta e' un errore, non un no-op: un
    IdP che crede di aver tolto un membro deve saperlo se non e' successo.
    """
    group = _group_or_404(group_id)
    added: list[str] = []
    removed: list[str] = []
    new_name: str | None = None
    for op in body.Operations:
        kind = str(op.get("op", "")).lower()
        path = str(op.get("path", "") or "").strip()
        value = op.get("value")
        member_filter = _MEMBER_FILTER.match(path)

        if kind == "add" and path.lower() == "members":
            added += _known_usernames(_as_list(value))
        elif kind == "remove" and member_filter:
            removed.append(member_filter.group(1))
        elif kind == "remove" and path.lower() == "members":
            removed += list(group["members"]) if value is None else [_member_value(v) for v in _as_list(value)]
        elif kind == "replace" and path.lower() == "members":
            members = _known_usernames(_as_list(value))
            removed += [m for m in group["members"] if m not in members]
            added += members
        elif kind == "replace" and path.lower() == "displayname":
            new_name = str(value or "").strip()
        elif kind == "replace" and not path and isinstance(value, dict) and "displayName" in value:
            new_name = str(value["displayName"] or "").strip()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Operazione PATCH non supportata: {kind} {path}".strip(),
            )

    # Tutto validato prima di scrivere: un PATCH con un'operazione sbagliata
    # in fondo non deve lasciare applicate a meta' quelle prima.
    if new_name is not None:
        if not new_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="displayName vuoto")
        _conflict_if_name_taken(new_name, except_id=group_id)
        scim_group_store.rename(group_id, new_name)
    by_lower = {m.lower(): m for m in group["members"]}
    scim_group_store.remove_members(group_id, [by_lower.get(r.lower(), r) for r in removed])
    scim_group_store.add_members(group_id, added)

    updated = _group_or_404(group_id)
    append_audit(
        cfg.AUDIT_FILE,
        "scim_group_patched",
        "scim_idp",
        {"group": updated["display_name"], "added": added, "removed": removed},
    )
    return _format_scim_group(updated)


@router.delete("/Groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scim_group(group_id: str, _auth: dict = Depends(_verify_scim_auth)) -> Response:
    group = _group_or_404(group_id)
    scim_group_store.delete(group_id)
    append_audit(cfg.AUDIT_FILE, "scim_group_deleted", "scim_idp", {"group": group["display_name"]})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
