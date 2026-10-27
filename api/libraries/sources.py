"""Watched import folders and chat channel integrations of a library."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key
from api.libraries.common import get_library_store
from config import cfg
from core.folder_importer import scan_import_source
from core.governance import append_audit
from core.ingestion_worker import run_ingestion_job
from core.library_store import (
    LibraryAccessError,
    LibraryNotFoundError,
    LibraryStore,
)

router = APIRouter(prefix="/api/libraries", tags=["Libraries"])


class ImportSourceRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class ChatIntegrationRequest(BaseModel):
    platform: Literal["slack", "teams", "telegram"]
    external_channel_id: str = Field(min_length=1, max_length=500)


@router.get("/{library_id}/sources")
def list_library_sources(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        return {"items": store.list_import_sources(library_id, _auth)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


def _reject_source_path_inside_app(path: str) -> None:
    """Refuse a registered import source that resolves inside the app's own tree.

    Found by review, not in the wild: with no restriction here, any editor of
    ANY library could register another library's storage directory
    (storage/libraries/<other-id>/) as a "folder source" for their own
    library and scan it in — the confidential document would be imported
    verbatim, fully readable via the importing library's own citations. That
    is a complete bypass of the product's central guarantee ("retrieval never
    crosses a library boundary"), reachable without ever touching the normal
    read path the isolation tests actually cover.

    This check is independent of the role gate below: it holds even for a
    library's own owner, because there is no legitimate reason a folder
    source should ever point inside data the application itself manages
    (storage/, data/, security/, docs/, the source tree). A folder source
    exists to pull in an *external* network drop folder.
    """
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Percorso non valido") from error
    app_root = Path(cfg.BASE_DIR).resolve()
    if resolved == app_root or app_root in resolved.parents:
        raise HTTPException(
            status_code=422,
            detail="Il percorso non puo' trovarsi dentro la directory dell'applicazione",
        )


def _require_library_owner_or_admin(store: LibraryStore, library_id: str, actor: dict) -> dict:
    """Import sources grant the server filesystem read access on the actor's say-so.

    That is a materially larger blast radius than uploading through the
    browser, so registering or removing one requires the same trust level as
    deleting the library outright (owner or global admin) — not just
    "editor", which any collaborator added to a shared library can be.
    """
    library = store.get_library(library_id, actor, write=True)
    if library["access_role"] != "owner" and actor.get("role") != "admin":
        raise HTTPException(
            status_code=403, detail="Solo il proprietario o un amministratore possono gestire le sorgenti cartella"
        )
    return library


@router.post("/{library_id}/sources", status_code=201)
def add_library_source(
    library_id: str,
    request: ImportSourceRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Registra una cartella da cui importare documenti (solo percorso, mai credenziali)."""
    path = request.path.strip()
    if not path:
        raise HTTPException(status_code=422, detail="Indica il percorso della cartella")
    _reject_source_path_inside_app(path)
    try:
        _require_library_owner_or_admin(store, library_id, _auth)
        source = store.add_import_source(library_id, path, created_by=_auth["username"])
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    append_audit(
        cfg.AUDIT_FILE, "import_source_added", _auth["username"], {"library_id": library_id, "path": source["path"]}
    )
    return source


@router.delete("/{library_id}/sources/{source_id}")
def remove_library_source(
    library_id: str,
    source_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        _require_library_owner_or_admin(store, library_id, _auth)
        removed = store.remove_import_source(library_id, source_id)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if not removed:
        raise HTTPException(status_code=404, detail="Sorgente non trovata")
    append_audit(
        cfg.AUDIT_FILE, "import_source_removed", _auth["username"], {"library_id": library_id, "source_id": source_id}
    )
    return {"removed": True}


@router.post("/{library_id}/sources/{source_id}/scan")
def scan_library_source(
    library_id: str,
    source_id: str,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Scansiona la cartella e importa i nuovi documenti (dedup per contenuto)."""
    try:
        store.get_library(library_id, _auth, write=True)
        source = store.get_import_source_by_id(library_id, source_id)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Sorgente non trovata") from error
    result = scan_import_source(store, library_id, source, cfg.LIBRARY_STORAGE_DIR)
    for imported in result["imported"]:
        background_tasks.add_task(run_ingestion_job, store, imported["job_id"], cfg.LIBRARY_STORAGE_DIR)
    append_audit(
        cfg.AUDIT_FILE,
        "import_source_scanned",
        _auth["username"],
        {
            "library_id": library_id,
            "source_id": source_id,
            "imported": len(result["imported"]),
            "skipped_duplicates": len(result["skipped_duplicates"]),
            "failed": len(result["failed"]),
        },
    )
    return result


@router.get("/{library_id}/integrations")
def list_library_chat_integrations(
    library_id: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        return {"items": store.list_chat_integrations(library_id, _auth)}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


@router.post("/{library_id}/integrations", status_code=201)
def add_library_chat_integration(
    library_id: str,
    request: ChatIntegrationRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    """Collega un canale Slack/Teams a questa biblioteca (nessuna credenziale
    di piattaforma qui: solo l'id del canale che potrà interrogarla)."""
    try:
        _require_library_owner_or_admin(store, library_id, _auth)
        integration = store.add_chat_integration(
            library_id,
            request.platform,
            request.external_channel_id,
            created_by=_auth["username"],
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    append_audit(
        cfg.AUDIT_FILE,
        "chat_integration_added",
        _auth["username"],
        {
            "library_id": library_id,
            "platform": integration["platform"],
            "external_channel_id": integration["external_channel_id"],
        },
    )
    return integration


@router.delete("/{library_id}/integrations/{integration_id}")
def remove_library_chat_integration(
    library_id: str,
    integration_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        _require_library_owner_or_admin(store, library_id, _auth)
        removed = store.remove_chat_integration(library_id, integration_id)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error
    if not removed:
        raise HTTPException(status_code=404, detail="Collegamento non trovato")
    append_audit(
        cfg.AUDIT_FILE,
        "chat_integration_removed",
        _auth["username"],
        {"library_id": library_id, "integration_id": integration_id},
    )
    return {"removed": True}
