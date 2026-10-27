"""Library endpoints: create, list, detail, assistant policy, members, delete, export/import, duplicates."""

from __future__ import annotations

import contextlib
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key, rate_limited
from api.libraries.common import _require_library_member_manager, _unlink_storage_paths, get_library_store
from config import cfg
from core.governance import append_audit
from core.library_store import (
    LibraryAccessError,
    LibraryNotFoundError,
    LibraryStore,
)

router = APIRouter(prefix="/api/libraries", tags=["Libraries"])


class CreateLibraryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    visibility: str = Field(default="private")


class AssistantPolicyRequest(BaseModel):
    mode: str = Field(pattern="^(evidence_only|local_ollama|approved_openrouter|approved_provider)$")
    provider_name: str = Field(default="", max_length=120, pattern=r"^[A-Za-z0-9 ._:-]*$")


class LibraryMemberRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    role: str = Field(pattern="^(viewer|reviewer|editor|manager)$")


@router.get("")
def list_libraries(
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    return {"items": store.list_libraries(_auth)}


@router.post("", status_code=201)
def create_library(
    request: CreateLibraryRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        return store.create_library(request.name, request.description, request.visibility, owner_id=_auth["username"])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/index-consistency")
def library_index_consistency(
    _auth: dict = Depends(_require_role("admin")),
    store: LibraryStore = Depends(get_library_store),
):
    """Diagnostica di allineamento tra DB, originali e vettori (solo admin)."""
    report = store.verify_index_consistency(cfg.LIBRARY_STORAGE_DIR, cfg.EMBED_MODEL_ID)
    return report


@router.get("/{library_id}")
def get_library_detail(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Dettaglio biblioteca con access_role effettivo dell'utente."""
    try:
        return store.get_library(library_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.put("/{library_id}/assistant-policy")
def set_library_assistant_policy(
    library_id: str,
    request: AssistantPolicyRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Set the explicit generation/data-egress policy for one library."""
    try:
        library = store.get_library(library_id, _auth, write=True)
        if request.mode in {"approved_openrouter", "approved_provider"} and not store.can_manage_library_members(
            library_id, _auth
        ):
            raise HTTPException(
                status_code=403, detail="Solo il proprietario o un amministratore possono autorizzare un provider cloud"
            )
        if request.mode == "approved_openrouter" and (not cfg.LIBRARY_CLOUD_CONSENT or not cfg.OPENROUTER_API_KEY):
            raise HTTPException(status_code=409, detail="OpenRouter non e autorizzato o configurato per questa istanza")
        if request.mode == "approved_provider" and _get_approved_cloud_provider(request.provider_name) is None:
            raise HTTPException(
                status_code=409, detail="Provider cloud non autorizzato o non configurato per questa istanza"
            )
        updated = store.set_assistant_policy(library_id, request.mode, request.provider_name)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    append_audit(
        cfg.AUDIT_FILE,
        "library_assistant_policy_changed",
        _auth["username"],
        {"library_id": library["id"], "mode": request.mode, "provider_name": updated.get("assistant_provider", "")},
    )
    return {
        "id": updated["id"],
        "assistant_mode": updated["assistant_mode"],
        "assistant_provider": updated.get("assistant_provider", ""),
    }


def _get_approved_cloud_provider(name: str):
    """Return one enabled, credentialed, non-local provider without secrets."""
    if not cfg.LIBRARY_CLOUD_CONSENT or not name:
        return None
    from core.ai.providers.registry import get_registry

    provider = get_registry().get_provider(name)
    if provider is None or not provider.config.enabled or provider.config.type == "ollama":
        return None
    if not provider.config.api_key or not provider.config.default_model:
        return None
    return provider


@router.get("/{library_id}/assistant-options")
def library_assistant_options(
    library_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Safe provider labels for a library policy picker; no credentials leak."""
    try:
        store.get_library(library_id, _auth, write=True)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if not cfg.LIBRARY_CLOUD_CONSENT:
        return {"items": [], "cloud_enabled": False}
    from core.ai.providers.registry import get_registry

    items = []
    for item in get_registry().list_providers():
        provider = _get_approved_cloud_provider(str(item.get("name", "")))
        if provider:
            items.append(
                {
                    "name": provider.config.name,
                    "type": provider.config.type,
                    "default_model": provider.config.default_model,
                }
            )
    return {"items": items, "cloud_enabled": True}


@router.get("/{library_id}/members")
def list_library_members(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    _require_library_member_manager(store, library_id, _auth)
    return {"items": store.list_library_members(library_id)}


@router.put("/{library_id}/members")
def set_library_member(
    library_id: str,
    request: LibraryMemberRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    _require_library_member_manager(store, library_id, _auth)
    try:
        member = store.set_library_member(library_id, request.username, request.role)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    append_audit(cfg.AUDIT_FILE, "library_member_changed", _auth["username"], {"library_id": library_id, **member})
    return member


@router.delete("/{library_id}/members/{username}", status_code=204)
def remove_library_member(
    library_id: str,
    username: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    _require_library_member_manager(store, library_id, _auth)
    if not store.remove_library_member(library_id, username):
        raise HTTPException(status_code=404, detail="Collaboratore non trovato")
    append_audit(
        cfg.AUDIT_FILE, "library_member_removed", _auth["username"], {"library_id": library_id, "username": username}
    )


@router.delete("/{library_id}", status_code=204)
def delete_library(
    library_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Elimina l'intera biblioteca. Solo il proprietario o un admin globale."""
    try:
        library = store.get_library(library_id, _auth, write=True)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if library["access_role"] != "owner" and _auth.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo il proprietario puo' eliminare la biblioteca")
    paths = store.delete_library(library_id)
    _unlink_storage_paths(paths)
    append_audit(
        cfg.AUDIT_FILE, "library_deleted", _auth["username"], {"library_id": library_id, "name": library["name"]}
    )


@router.get("/{library_id}/export")
def export_library_endpoint(
    library_id: str,
    _auth: dict = Depends(_require_role("viewer")),
    store: LibraryStore = Depends(get_library_store),
):
    """Export the entire library with documents and chunks as a downloadable .ermes pack."""
    import tempfile

    from core.library_pack import export_library_pack

    try:
        library = store.get_library(library_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error

    temp_pack = tempfile.NamedTemporaryFile(suffix=".ermes", delete=False)
    temp_pack.close()

    try:
        pack_path = export_library_pack(
            store=store,
            library_id=library_id,
            storage_dir=cfg.LIBRARY_STORAGE_DIR,
            output_path=temp_pack.name,
            actor=_auth,
        )
        safe_name = "".join(c for c in library["name"] if c.isalnum() or c in "._ -").strip() or "biblioteca"
        filename = f"{safe_name}.ermes"
        append_audit(
            cfg.AUDIT_FILE, "library_exported", _auth["username"], {"library_id": library_id, "name": library["name"]}
        )
        return FileResponse(
            path=pack_path,
            filename=filename,
            media_type="application/gzip",
        )
    except Exception as error:
        if os.path.exists(temp_pack.name):
            with contextlib.suppress(OSError):
                os.unlink(temp_pack.name)
        raise HTTPException(status_code=500, detail=f"Errore durante l'esportazione: {error}") from error


@router.post("/import-pack", status_code=201, dependencies=[Depends(rate_limited)])
async def import_library_pack_endpoint(
    file: UploadFile = File(...),
    name: str = Form(""),
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Import a .ermes knowledge pack and create a new library with full indexing."""
    import tempfile

    from core.library_pack import MAX_TOTAL_BYTES_FACTOR, KnowledgePackError, import_library_pack

    # Un pacchetto contiene molti documenti, quindi il limite e' un multiplo
    # di quello per singolo upload. Si scrive su disco a blocchi: fino al 18
    # settembre 2026 `await file.read()` senza limite caricava l'intero
    # archivio in memoria, e la rotta era l'unica con upload senza
    # rate_limited.
    max_member_bytes = cfg.ADMIN_MAX_UPLOAD_MB * 1024 * 1024
    max_pack_bytes = max_member_bytes * MAX_TOTAL_BYTES_FACTOR
    temp_pack = tempfile.NamedTemporaryFile(suffix=".ermes", delete=False)
    try:
        written = 0
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > max_pack_bytes:
                raise HTTPException(status_code=413, detail="Pacchetto troppo grande")
            temp_pack.write(chunk)
        temp_pack.close()
        if written == 0:
            raise HTTPException(status_code=400, detail="Pacchetto vuoto")

        library = import_library_pack(
            store=store,
            pack_path=temp_pack.name,
            storage_dir=cfg.LIBRARY_STORAGE_DIR,
            owner_id=_auth["username"],
            override_name=name,
            max_member_bytes=max_member_bytes,
        )
        append_audit(
            cfg.AUDIT_FILE,
            "library_pack_imported",
            _auth["username"],
            {"library_id": library["id"], "name": library["name"]},
        )
        return library
    except HTTPException:
        raise
    except KnowledgePackError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Errore durante l'importazione: {error}") from error
    finally:
        temp_pack.close()
        if os.path.exists(temp_pack.name):
            with contextlib.suppress(OSError):
                os.unlink(temp_pack.name)


@router.get("/{library_id}/duplicates")
def get_library_duplicates_endpoint(
    library_id: str,
    _auth: dict = Depends(_require_role("viewer")),
    store: LibraryStore = Depends(get_library_store),
):
    """Rileva documenti identici o con forte sovrapposizione testuale (near-duplicates)."""
    from core.deduplication import find_library_duplicates

    try:
        store.get_library(library_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    docs = store.list_documents(library_id, _auth)
    enriched_docs = []
    for d in docs:
        full_doc = store.get_document(library_id, d["id"], _auth)
        if full_doc:
            chunks = full_doc.get("chunks", [])
            text = " ".join(c[0] for c in chunks if isinstance(c, (list, tuple)) and c)
            enriched_docs.append(
                {
                    "id": d["id"],
                    "filename": d.get("filename", ""),
                    "text": text,
                }
            )

    duplicates = find_library_duplicates(enriched_docs)
    return {"duplicates": duplicates, "total_groups": len(duplicates)}
