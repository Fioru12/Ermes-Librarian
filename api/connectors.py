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
from core.connectors import registry
from core.connectors.base import BaseConnector
from core.document_parser import extract_source_units
from core.governance import append_audit
from core.library_store import LibraryAccessError, LibraryNotFoundError, LibraryStore, storage_relative_path
from core.storage_provider import get_storage_provider

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connectors", tags=["Enterprise Connectors"])


# Solo la forma del nome: quali tipi esistono lo decide il registro
# (core/connectors/registry.py), che include i plugin configurati.
SUPPORTED_CONNECTORS_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"


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
    try:
        return registry.create_connector(connector_type, config)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Tipo connettore non supportato: {connector_type}") from None
    except registry.ConnectorPluginError as errore:
        # Configurazione dell'installazione sbagliata, non richiesta sbagliata.
        _logger.error("%s", errore)
        raise HTTPException(status_code=503, detail="Plugin connettori non configurati correttamente") from errore


@router.get("/types", summary="Tipi di connettore disponibili (integrati e plugin)")
def list_connector_types(_auth: dict = Depends(_require_role("admin"))) -> dict[str, Any]:
    try:
        types = registry.available_types()
    except registry.ConnectorPluginError as errore:
        _logger.error("%s", errore)
        raise HTTPException(status_code=503, detail="Plugin connettori non configurati correttamente") from errore
    return {"types": [{"type": t, "builtin": registry.is_builtin(t)} for t in types]}


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

        from core.antivirus import AntivirusScanError, scan_document

        for rdoc in remote_docs:
            try:
                try:
                    scan_res = scan_document(rdoc.content, filename=rdoc.name, actor=str(_auth.get("username", "")))
                    if not scan_res.is_clean:
                        virus = scan_res.virus_name or "minaccia rilevata"
                        _logger.warning("Antivirus ha bloccato il documento remoto %s: %s", rdoc.name, virus)
                        errors.append(f"{rdoc.name}: File malevolo bloccato ({virus})")
                        continue
                except AntivirusScanError as scan_err:
                    _logger.error("Servizio antivirus non disponibile durante la sincronizzazione connettore: %s", scan_err)
                    errors.append(f"{rdoc.name}: Servizio antivirus non disponibile ({scan_err})")
                    continue

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


# ============================================================
# Scheduled Connectors Management
# ============================================================


class CreateConnectorScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    connector_type: str = Field(pattern=SUPPORTED_CONNECTORS_PATTERN)
    config: dict[str, Any] = Field(default_factory=dict)
    target_library_id: str = Field(min_length=1)
    interval_minutes: int = Field(default=60, ge=5, le=10080)
    enabled: bool = True


@router.get("/schedules", summary="Elenca tutti i connettori cloud schedulati")
def list_connector_schedules(
    library_id: str | None = Query(default=None),
    _auth: dict = Depends(_require_role("editor")),
) -> dict[str, Any]:
    from core.connector_scheduler import get_schedule_store

    store = get_schedule_store()
    schedules = store.list_schedules(target_library_id=library_id)
    return {
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "connector_type": s.connector_type,
                "target_library_id": s.target_library_id,
                "interval_minutes": s.interval_minutes,
                "enabled": s.enabled,
                "last_sync_at": s.last_sync_at,
                "next_sync_at": s.next_sync_at,
                "last_status": s.last_status,
                "last_error": s.last_error,
                "items_synced": s.items_synced,
                "created_at": s.created_at,
            }
            for s in schedules
        ]
    }


@router.post("/schedules", summary="Crea una nuova pianificazione di sincronizzazione automatica per connettore")
def create_connector_schedule(
    req: CreateConnectorScheduleRequest,
    _auth: dict = Depends(_require_role("admin")),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    # Verifica che la biblioteca target esista
    lib = store.get_library(req.target_library_id, _auth)
    if not lib:
        raise HTTPException(status_code=404, detail="Biblioteca target non trovata")

    from core.connector_scheduler import get_schedule_store

    sched_store = get_schedule_store()
    schedule = sched_store.create_schedule(
        name=req.name,
        connector_type=req.connector_type,
        config=req.config,
        target_library_id=req.target_library_id,
        interval_minutes=req.interval_minutes,
        enabled=req.enabled,
    )

    append_audit(
        cfg.AUDIT_FILE,
        "connector_schedule_created",
        _auth["username"],
        {"schedule_id": schedule.id, "name": schedule.name, "type": schedule.connector_type},
    )

    return {
        "ok": True,
        "schedule": {
            "id": schedule.id,
            "name": schedule.name,
            "connector_type": schedule.connector_type,
            "target_library_id": schedule.target_library_id,
            "interval_minutes": schedule.interval_minutes,
            "enabled": schedule.enabled,
            "next_sync_at": schedule.next_sync_at,
        },
    }


@router.delete("/schedules/{schedule_id}", summary="Elimina una pianificazione di connettore")
def delete_connector_schedule(
    schedule_id: str,
    _auth: dict = Depends(_require_role("admin")),
) -> dict[str, Any]:
    from core.connector_scheduler import get_schedule_store

    sched_store = get_schedule_store()
    deleted = sched_store.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pianificazione non trovata")

    append_audit(
        cfg.AUDIT_FILE,
        "connector_schedule_deleted",
        _auth["username"],
        {"schedule_id": schedule_id},
    )
    return {"ok": True, "deleted_id": schedule_id}


@router.post("/schedules/{schedule_id}/trigger", summary="Avvia immediatamente la sincronizzazione di una pianificazione")
def trigger_connector_schedule_now(
    schedule_id: str,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    from core.connector_scheduler import run_schedule_sync

    try:
        result = run_schedule_sync(schedule_id, store=store)
        append_audit(
            cfg.AUDIT_FILE,
            "connector_schedule_triggered",
            _auth["username"],
            {"schedule_id": schedule_id, "result": result},
        )
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante l'esecuzione del connettore: {e}") from e
