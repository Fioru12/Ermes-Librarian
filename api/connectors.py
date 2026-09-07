"""
api/connectors.py
Enterprise Cloud & Intranet Connectors API endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _require_role
from api.libraries import get_library_store
from config import cfg
from core.connectors.local_folder import LocalFolderConnector
from core.connectors.microsoft_graph import MicrosoftGraphConnector
from core.connectors.web_scraper import WebScraperConnector
from core.governance import append_audit
from core.library_store import LibraryStore

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connectors", tags=["Enterprise Connectors"])


class TestConnectorRequest(BaseModel):
    type: str = Field(pattern="^(microsoft_graph|web_scraper|local_folder)$")
    config: dict[str, Any] = Field(default_factory=dict)


class SyncConnectorRequest(BaseModel):
    type: str = Field(pattern="^(microsoft_graph|web_scraper|local_folder)$")
    config: dict[str, Any] = Field(default_factory=dict)
    target_library_id: str = Field(min_length=1)


@router.post("/test", summary="Testa connettività e credenziali connettore")
def test_connector(
    request: TestConnectorRequest,
    _auth: dict = Depends(_require_role("admin")),
) -> dict:
    if request.type == "microsoft_graph":
        connector: MicrosoftGraphConnector | WebScraperConnector | LocalFolderConnector = MicrosoftGraphConnector(request.config)
    elif request.type == "web_scraper":
        connector = WebScraperConnector(request.config)
    elif request.type == "local_folder":
        connector = LocalFolderConnector(request.config)
    else:
        raise HTTPException(status_code=400, detail="Tipo connettore non supportato")

    ok, message = connector.test_connection()
    return {"ok": ok, "message": message, "type": request.type}


@router.post("/sync", summary="Sincronizza documenti remoti nella biblioteca specificata")
def sync_connector(
    request: SyncConnectorRequest,
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
) -> dict:
    # Verifica esistenza biblioteca e permessi
    lib = store.get_library(request.target_library_id, _auth)
    if not lib:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata")

    if request.type == "microsoft_graph":
        connector: MicrosoftGraphConnector | WebScraperConnector | LocalFolderConnector = MicrosoftGraphConnector(request.config)
    elif request.type == "web_scraper":
        connector = WebScraperConnector(request.config)
    elif request.type == "local_folder":
        connector = LocalFolderConnector(request.config)
    else:
        raise HTTPException(status_code=400, detail="Tipo connettore non supportato")

    try:
        remote_docs = connector.fetch_documents()
        imported = 0
        skipped_duplicates = 0
        errors = []

        import hashlib

        from core.document_parser import extract_source_units
        from core.library_store import resolve_storage_path, storage_relative_path

        known_hashes = store.existing_content_hashes(request.target_library_id)

        for rdoc in remote_docs:
            try:
                # Estrazione diretta dai byte: extract_source_units non
                # richiede file temporanei (parse_document non esiste piu').
                units = extract_source_units(rdoc.name, rdoc.content)
                chunks = [(u.text, u.locator) for u in units]
                if not chunks or not chunks[0][0]:
                    chunks = [(rdoc.name, "Titolo")]

                # L'originale DEVE essere scritto su disco: add_document
                # registra solo metadati, senza il file il download e la
                # re-ingestione falliscono con "Originale non disponibile"
                # (stessa classe di bug gia' trovata nel folder_importer).
                digest = hashlib.sha256(rdoc.content).hexdigest()
                if digest in known_hashes:
                    skipped_duplicates += 1
                    continue
                stored_name = f"{digest[:12]}_{rdoc.name}"
                stored_rel = storage_relative_path(request.target_library_id, stored_name)
                destination = resolve_storage_path(stored_rel, cfg.LIBRARY_STORAGE_DIR)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(rdoc.content)

                # Inserisce documento nel library store
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


@router.get("/watcher/status", summary="Stato del demone Folder Watcher per cartelle condivise/NAS")
def get_watcher_status(
    _auth: dict = Depends(_require_role("editor")),
    store: LibraryStore = Depends(get_library_store),
) -> dict:
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
) -> dict:
    from core.folder_watcher import sync_all_sources

    result = sync_all_sources(store=store)
    append_audit(
        cfg.AUDIT_FILE,
        "folder_watcher_manual_sync",
        _auth["username"],
        result,
    )
    return {"ok": True, "result": result}
