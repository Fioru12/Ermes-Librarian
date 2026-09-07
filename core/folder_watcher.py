"""Folder watcher daemon for Ermes Knowledge.

Continuously monitors all registered folder sources across libraries and
automatically ingests new or updated documents.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from config import cfg
from core.folder_importer import scan_import_source
from core.ingestion_service import process_ingestion_job
from core.library_store import LibraryStore

logger = logging.getLogger(__name__)


def sync_all_sources(store: LibraryStore, storage_dir: str | Path | None = None) -> dict:
    """Scan all registered import sources and process pending ingestion jobs.

    Returns execution summary with counts of scanned sources and imported documents.
    """
    storage_root = str(storage_dir or cfg.LIBRARY_STORAGE_DIR)
    sources = store.list_all_import_sources()
    total_imported = 0
    total_failed = 0
    scanned_results = []

    for source in sources:
        try:
            scan_result = scan_import_source(
                store=store,
                library_id=source["library_id"],
                source=source,
                storage_dir=storage_root,
            )
            scanned_results.append(scan_result)
            imported_jobs = scan_result.get("imported", [])
            total_imported += len(imported_jobs)
            total_failed += len(scan_result.get("failed", []))

            # Process newly queued ingestion jobs
            for item in imported_jobs:
                job_id = item.get("job_id")
                if job_id:
                    try:
                        process_ingestion_job(store, job_id, storage_root)
                    except Exception as ex:
                        logger.error("Errore durante l'ingestion del job %s: %s", job_id, ex)
        except Exception as error:
            logger.error("Errore durante la scansione della cartella %s: %s", source.get("path"), error)
            total_failed += 1

    return {
        "scanned_sources": len(sources),
        "total_imported": total_imported,
        "total_failed": total_failed,
        "details": scanned_results,
    }


def start_folder_watcher_thread(
    store: LibraryStore,
    storage_dir: str | Path | None = None,
    interval_sec: int = 15,
    stop_event: threading.Event | None = None,
) -> threading.Thread:
    """Start a background daemon thread that periodically synchronizes watched folders."""

    def _worker():
        logger.info("Folder watcher avviato (intervallo: %ds)", interval_sec)
        while stop_event is None or not stop_event.is_set():
            try:
                sync_all_sources(store, storage_dir)
            except Exception as e:
                logger.error("Eccezione nel ciclo di folder watcher: %s", e)
            if stop_event is not None:
                if stop_event.wait(timeout=interval_sec):
                    break
            else:
                time.sleep(interval_sec)
        logger.info("Folder watcher terminato.")

    thread = threading.Thread(target=_worker, daemon=True, name="ermes-folder-watcher")
    thread.start()
    return thread
