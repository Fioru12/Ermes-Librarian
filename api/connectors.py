"""api/connectors.py
Enterprise Cloud & Intranet Connectors API endpoints.
Supports real-time webhooks, delta tokens, and cloud storage providers.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from api.auth import _require_role
from api.libraries import _reject_source_path_inside_app, _require_library_owner_or_admin, get_library_store
from config import cfg
from core.connectors.base import BaseConnector
from core.connectors.confluence import ConfluenceConnector
from core.connectors.google_drive import GoogleDriveConnector
from core.connectors.local_folder import LocalFolderConnector
from core.connectors.microsoft_graph import MicrosoftGraphConnector
from core.connectors.s3_bucket import S3BucketConnector
from core.connectors.web_scraper import WebScraperConnector
from core.connectors.webdav import WebDAVConnector
from core.document_parser import extract_source_units
from core.governance import append_audit
from core.library_store import LibraryAccessError, LibraryNotFoundError, LibraryStore, storage_relative_path
from core.storage_provider import get_storage_provider

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connectors", tags=["Enterprise Connectors"])


SUPPORTED_CONNECTORS_PATTERN = "^(microsoft_graph|google_drive|confluence|web_scraper|local_folder|s3_bucket|webdav)$"


class TestConnectorRequest(BaseModel):
    type: str = Field(pattern=SUPPORTED_CONNECTORS_PATTERN)
    config: dict[str, Any] = Field(default_factory=dict)


class SyncConnectorRequest(BaseModel):
    type: str = Field(pattern=SUPPORTED_CONNECTORS_PATTERN)
    config: dict[str, Any] = Field(default_factory=dict)
    target_library_id: str = Field(min_length=1)


class DeltaSyncRequest(BaseModel):
    type: str = Field(pattern=SUPPORTED_CONNECTORS_PATTERN)
    config: dict[str, Any] = Field(default_factory=dict)
    target_library_id: str = Field(min_length=1)
    delta_token: str | None = None


def _build_connector(connector_type: str, config: dict[str, Any]) -> BaseConnector:
    if connector_type == "microsoft_graph":
        return MicrosoftGraphConnector(config)
    elif connector_type == "google_drive":
        return GoogleDriveConnector(config)
    elif connector_type == "confluence":
        return ConfluenceConnector(config)
    elif connector_type == "web_scraper":
        return WebScraperConnector(config)
    elif connector_type == "local_folder":
        return LocalFolderConnector(config)
    elif connector_type == "s3_bucket":
        return S3BucketConnector(config)
    elif connector_type == "webdav":
        return WebDAVConnector(config)
    raise HTTPException(status_code=400, detail=f"Tipo connettore non supportato: {connector_type}")


@router.post("/test", summary="Testa connettività e credenziali connettore")
def test_connector(
    request: TestConnectorRequest,
    _auth: dict = Depends(_require_role("admin")),
) -> dict[str, Any]:
    connector = _build_connector(request.type, request.config)
    ok, message = connector.test_connection()
    return {"ok": ok, "message": message, "type": request.type}


@router.post("/sync", summary="Sincronizza documenti remoti nella biblioteca specificata (scansione completa)")
def sync_connector(
    request: SyncConnectorRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    # Verifica esistenza biblioteca e permessi
    lib = store.get_library(request.target_library_id, _auth)
    if not lib:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata")

    try:
        _require_library_owner_or_admin(store, request.target_library_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as errore:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from errore

    if request.type == "local_folder":
        _reject_source_path_inside_app(str(request.config.get("folder_path", "")))

    connector = _build_connector(request.type, request.config)

    try:
        remote_docs = connector.fetch_documents()
        imported = 0
        skipped_duplicates = 0
        errors: list[str] = []

        storage_provider = get_storage_provider()
        known_hashes = store.existing_content_hashes(request.target_library_id)

        for rdoc in remote_docs:
            try:
                units = extract_source_units(rdoc.name, rdoc.content)
                chunks = [(u.text, u.locator) for u in units]
                if not chunks or not chunks[0][0]:
                    chunks = [(rdoc.name, "Titolo")]

                digest = hashlib.sha256(rdoc.content).hexdigest()
                if digest in known_hashes:
                    skipped_duplicates += 1
                    continue

                stored_name = f"{digest[:12]}_{rdoc.name}"
                stored_rel = storage_relative_path(request.target_library_id, stored_name)
                storage_provider.save(stored_rel, rdoc.content)

                store.add_document(
                    library_id=request.target_library_id,
                    filename=rdoc.name,
                    media_type=rdoc.media_type,
                    content=rdoc.content,
                    storage_path=stored_rel,
                    status="ready",
                    chunks=chunks,
                )
                known_hashes.add(digest)
                imported += 1

            except Exception as e:
                _logger.warning("Errore importazione documento remoto %s: %s", rdoc.name, e)
                errors.append(f"{rdoc.name}: {e}")

        append_audit(
            cfg.AUDIT_FILE,
            "connector_sync",
            _auth["username"],
            {
                "connector_type": request.type,
                "library_id": request.target_library_id,
                "imported": imported,
                "skipped_duplicates": skipped_duplicates,
                "total_found": len(remote_docs),
            },
        )

        return {
            "ok": True,
            "imported_count": imported,
            "skipped_duplicates": skipped_duplicates,
            "total_found": len(remote_docs),
            "errors": errors,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore sincronizzazione connettore: {e}") from e


@router.post("/sync-delta", summary="Sincronizzazione incrementale basata su delta-token o cursore")
def sync_connector_delta(
    request: DeltaSyncRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    lib = store.get_library(request.target_library_id, _auth)
    if not lib:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata")

    try:
        _require_library_owner_or_admin(store, request.target_library_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as errore:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from errore

    if request.type == "local_folder":
        _reject_source_path_inside_app(str(request.config.get("folder_path", "")))

    connector = _build_connector(request.type, request.config)

    try:
        delta_res = connector.fetch_delta(request.delta_token)
        imported = 0
        skipped_duplicates = 0
        errors: list[str] = list(delta_res.errors)

        storage_provider = get_storage_provider()
        known_hashes = store.existing_content_hashes(request.target_library_id)

        # Inserimento / Aggiornamento documenti nuovi o modificati
        for rdoc in delta_res.updated_documents:
            try:
                units = extract_source_units(rdoc.name, rdoc.content)
                chunks = [(u.text, u.locator) for u in units]
                if not chunks or not chunks[0][0]:
                    chunks = [(rdoc.name, "Titolo")]

                digest = hashlib.sha256(rdoc.content).hexdigest()
                if digest in known_hashes:
                    skipped_duplicates += 1
                    continue

                stored_name = f"{digest[:12]}_{rdoc.name}"
                stored_rel = storage_relative_path(request.target_library_id, stored_name)
                storage_provider.save(stored_rel, rdoc.content)

                store.add_document(
                    library_id=request.target_library_id,
                    filename=rdoc.name,
                    media_type=rdoc.media_type,
                    content=rdoc.content,
                    storage_path=stored_rel,
                    status="ready",
                    chunks=chunks,
                )
                known_hashes.add(digest)
                imported += 1
            except Exception as e:
                _logger.warning("Errore importazione delta documento %s: %s", rdoc.name, e)
                errors.append(f"{rdoc.name}: {e}")

        # Rimozione documenti cancellati alla sorgente remota
        deleted_count = 0
        if delta_res.deleted_document_ids:
            library_docs = store.list_documents(request.target_library_id, _auth)
            for d in library_docs:
                if d.get("id") in delta_res.deleted_document_ids or d.get("filename") in delta_res.deleted_document_ids:
                    paths = store.delete_document(request.target_library_id, d["id"])
                    for p in paths:
                        storage_provider.delete(p)
                    deleted_count += 1

        append_audit(
            cfg.AUDIT_FILE,
            "connector_delta_sync",
            _auth["username"],
            {
                "connector_type": request.type,
                "library_id": request.target_library_id,
                "imported": imported,
                "deleted": deleted_count,
                "skipped_duplicates": skipped_duplicates,
                "next_delta_token": delta_res.next_delta_token,
            },
        )

        return {
            "ok": True,
            "imported_count": imported,
            "deleted_count": deleted_count,
            "skipped_duplicates": skipped_duplicates,
            "next_delta_token": delta_res.next_delta_token,
            "errors": errors,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore sincronizzazione incrementale: {e}") from e


# ============================================================
# Cloud Webhooks Gateway
# ============================================================

@router.api_route("/webhooks/microsoft-graph", methods=["GET", "POST"], summary="Ricevitore webhook per Microsoft Graph")
async def microsoft_graph_webhook(
    request: Request,
    validation_token: str | None = Query(default=None, alias="validationToken"),
) -> Response:
    """Gestisce la convalida handshake e le notifiche di cambio da Microsoft Graph."""
    # Handshake di registrazione sottoscrizione
    if validation_token:
        return Response(content=validation_token, media_type="text/plain", status_code=200)

    try:
        body = await request.json()
    except Exception:
        body = {}

    notifications = body.get("value", []) if isinstance(body, dict) else []
    _logger.info("Ricevuta notifica webhook Microsoft Graph: %d eventi", len(notifications))

    append_audit(
        cfg.AUDIT_FILE,
        "microsoft_graph_webhook_notification",
        "ms_graph_webhook",
        {"events_count": len(notifications)},
    )
    return Response(status_code=202)


@router.post("/webhooks/google-drive", summary="Ricevitore push notification per Google Drive")
async def google_drive_webhook(
    request: Request,
    x_goog_channel_id: str | None = Header(default=None),
    x_goog_resource_state: str | None = Header(default=None),
    x_goog_message_number: str | None = Header(default=None),
) -> Response:
    """Riceve notifiche push dai canali watch di Google Drive."""
    _logger.info(
        "Ricevuta push notification Google Drive (channel=%s, state=%s, msg=%s)",
        x_goog_channel_id,
        x_goog_resource_state,
        x_goog_message_number,
    )
    append_audit(
        cfg.AUDIT_FILE,
        "google_drive_webhook_notification",
        "google_drive_webhook",
        {
            "channel_id": x_goog_channel_id,
            "resource_state": x_goog_resource_state,
            "message_number": x_goog_message_number,
        },
    )
    return Response(status_code=200)


@router.get("/watcher/status", summary="Stato del demone Folder Watcher per cartelle condivise/NAS")
def get_watcher_status(
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    sources = store.list_all_import_sources()
    return {
        "active": True,
        "monitored_sources_count": len(sources),
        "sources": sources,
    }


@router.post("/watcher/sync", summary="Forza la sincronizzazione immediata di tutte le cartelle monitorate")
def sync_watcher_now(
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    from core.folder_watcher import sync_all_sources

    result = sync_all_sources(store=store)
    append_audit(
        cfg.AUDIT_FILE,
        "folder_watcher_manual_sync",
        _auth["username"],
        result,
    )
    return {"ok": True, "result": result}
