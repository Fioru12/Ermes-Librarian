"""core/connector_scheduler.py
Gestore e Scheduler in Background per la Sincronizzazione Automatica dei Connettori Cloud/Intranet.

Permette di pianificare scansioni e sincronizzazioni incrementali periodiche
(SharePoint, Google Drive, Confluence, S3, WebDAV, Web Scraper) verso le biblioteche,
mantenendo lo stato dei token delta e registrando telemetria e audit.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import cfg
from core.library_store import LibraryStore

_logger = logging.getLogger("ermes.connector_scheduler")


@dataclass
class ConnectorSchedule:
    id: str
    name: str
    connector_type: str
    config: dict[str, Any]
    target_library_id: str
    interval_minutes: int
    enabled: bool
    last_sync_at: float | None
    next_sync_at: float
    last_status: str
    last_error: str | None
    next_delta_token: str | None
    items_synced: int
    created_at: float


class ConnectorScheduleStore:
    """Store persistente per la pianificazione dei connettori cloud."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or (Path(cfg.BASE_DIR) / "connector_schedules.db"))
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_schedules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    connector_type TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    target_library_id TEXT NOT NULL,
                    interval_minutes INTEGER NOT NULL DEFAULT 60,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_sync_at REAL,
                    next_sync_at REAL NOT NULL,
                    last_status TEXT NOT NULL DEFAULT 'idle',
                    last_error TEXT,
                    next_delta_token TEXT,
                    items_synced INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def create_schedule(
        self,
        name: str,
        connector_type: str,
        config: dict[str, Any],
        target_library_id: str,
        interval_minutes: int = 60,
        enabled: bool = True,
    ) -> ConnectorSchedule:
        schedule_id = f"sched_{uuid.uuid4().hex[:12]}"
        now = time.time()
        next_sync = now  # Avvio immediato o al prossimo ciclo

        schedule = ConnectorSchedule(
            id=schedule_id,
            name=name,
            connector_type=connector_type,
            config=config,
            target_library_id=target_library_id,
            interval_minutes=max(5, interval_minutes),
            enabled=enabled,
            last_sync_at=None,
            next_sync_at=next_sync,
            last_status="idle",
            last_error=None,
            next_delta_token=None,
            items_synced=0,
            created_at=now,
        )

        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO connector_schedules (
                    id, name, connector_type, config_json, target_library_id,
                    interval_minutes, enabled, last_sync_at, next_sync_at,
                    last_status, last_error, next_delta_token, items_synced, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule.id,
                    schedule.name,
                    schedule.connector_type,
                    json.dumps(schedule.config),
                    schedule.target_library_id,
                    schedule.interval_minutes,
                    1 if schedule.enabled else 0,
                    schedule.last_sync_at,
                    schedule.next_sync_at,
                    schedule.last_status,
                    schedule.last_error,
                    schedule.next_delta_token,
                    schedule.items_synced,
                    schedule.created_at,
                ),
            )
            conn.commit()

        return schedule

    def list_schedules(self, target_library_id: str | None = None) -> list[ConnectorSchedule]:
        with self._lock, self._get_conn() as conn:
            if target_library_id:
                rows = conn.execute(
                    "SELECT * FROM connector_schedules WHERE target_library_id = ? ORDER BY created_at DESC",
                    (target_library_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM connector_schedules ORDER BY created_at DESC").fetchall()

        return [self._row_to_schedule(r) for r in rows]

    def get_schedule(self, schedule_id: str) -> ConnectorSchedule | None:
        with self._lock, self._get_conn() as conn:
            row = conn.execute("SELECT * FROM connector_schedules WHERE id = ?", (schedule_id,)).fetchone()
        return self._row_to_schedule(row) if row else None

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM connector_schedules WHERE id = ?", (schedule_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_sync_result(
        self,
        schedule_id: str,
        status: str,
        items_count: int = 0,
        next_delta_token: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = time.time()
        sched = self.get_schedule(schedule_id)
        interval_sec = (sched.interval_minutes if sched else 60) * 60
        next_sync = now + interval_sec

        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                UPDATE connector_schedules
                SET last_sync_at = ?,
                    next_sync_at = ?,
                    last_status = ?,
                    last_error = ?,
                    next_delta_token = COALESCE(?, next_delta_token),
                    items_synced = items_synced + ?
                WHERE id = ?
                """,
                (
                    now,
                    next_sync,
                    status,
                    error_message,
                    next_delta_token,
                    items_count,
                    schedule_id,
                ),
            )
            conn.commit()

    def _row_to_schedule(self, row: sqlite3.Row) -> ConnectorSchedule:
        return ConnectorSchedule(
            id=row["id"],
            name=row["name"],
            connector_type=row["connector_type"],
            config=json.loads(row["config_json"]),
            target_library_id=row["target_library_id"],
            interval_minutes=row["interval_minutes"],
            enabled=bool(row["enabled"]),
            last_sync_at=row["last_sync_at"],
            next_sync_at=row["next_sync_at"],
            last_status=row["last_status"],
            last_error=row["last_error"],
            next_delta_token=row["next_delta_token"],
            items_synced=row["items_synced"],
            created_at=row["created_at"],
        )


_store_instance: ConnectorScheduleStore | None = None
_store_lock = threading.Lock()


def get_schedule_store() -> ConnectorScheduleStore:
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = ConnectorScheduleStore()
    return _store_instance


def run_schedule_sync(schedule_id: str, store: LibraryStore) -> dict[str, Any]:
    """Esegue la sincronizzazione di uno schedule specifico e aggiorna i token delta."""
    sched_store = get_schedule_store()
    schedule = sched_store.get_schedule(schedule_id)
    if not schedule:
        raise ValueError(f"Schedule {schedule_id} non trovato")

    from api.connectors import _build_connector
    from core.document_parser import extract_source_units
    from core.library_store import storage_relative_path
    from core.storage_provider import get_storage_provider

    _logger.info("Avvio sincronizzazione schedulata per %s (%s)", schedule.name, schedule.connector_type)
    connector = _build_connector(schedule.connector_type, schedule.config)
    storage_provider = get_storage_provider()
    known_hashes = store.existing_content_hashes(schedule.target_library_id)

    try:
        if schedule.next_delta_token:
            delta_res = connector.fetch_delta(schedule.next_delta_token)
            imported_count = 0
            for doc in delta_res.updated_documents:
                units = extract_source_units(doc.name, doc.content)
                chunks = [(u.text, u.locator) for u in units]
                if not chunks or not chunks[0][0]:
                    chunks = [(doc.name, "Titolo")]

                digest = hashlib.sha256(doc.content).hexdigest()
                if digest in known_hashes:
                    continue

                stored_name = f"{digest[:12]}_{doc.name}"
                stored_rel = storage_relative_path(schedule.target_library_id, stored_name)
                storage_provider.save(stored_rel, doc.content)

                store.add_document(
                    library_id=schedule.target_library_id,
                    filename=doc.name,
                    media_type=doc.media_type,
                    content=doc.content,
                    storage_path=stored_rel,
                    status="ready",
                    chunks=chunks,
                )
                known_hashes.add(digest)
                imported_count += 1

            for del_id in delta_res.deleted_document_ids:
                store.delete_document(schedule.target_library_id, del_id)

            sched_store.update_sync_result(
                schedule_id=schedule.id,
                status="success",
                items_count=imported_count,
                next_delta_token=delta_res.next_delta_token,
                error_message=None,
            )
            return {
                "ok": True,
                "mode": "delta",
                "imported": imported_count,
                "deleted": len(delta_res.deleted_document_ids),
                "next_delta_token": delta_res.next_delta_token,
            }
        else:
            docs = connector.fetch_documents()
            imported_count = 0
            for doc in docs:
                units = extract_source_units(doc.name, doc.content)
                chunks = [(u.text, u.locator) for u in units]
                if not chunks or not chunks[0][0]:
                    chunks = [(doc.name, "Titolo")]

                digest = hashlib.sha256(doc.content).hexdigest()
                if digest in known_hashes:
                    continue

                stored_name = f"{digest[:12]}_{doc.name}"
                stored_rel = storage_relative_path(schedule.target_library_id, stored_name)
                storage_provider.save(stored_rel, doc.content)

                store.add_document(
                    library_id=schedule.target_library_id,
                    filename=doc.name,
                    media_type=doc.media_type,
                    content=doc.content,
                    storage_path=stored_rel,
                    status="ready",
                    chunks=chunks,
                )
                known_hashes.add(digest)
                imported_count += 1

            sched_store.update_sync_result(
                schedule_id=schedule.id,
                status="success",
                items_count=imported_count,
                next_delta_token=None,
                error_message=None,
            )
            return {"ok": True, "mode": "full", "imported": imported_count}

    except Exception as e:
        _logger.exception("Fallimento sincronizzazione per schedule %s: %s", schedule_id, e)
        sched_store.update_sync_result(
            schedule_id=schedule.id,
            status="error",
            items_count=0,
            error_message=str(e),
        )
        raise


def sync_due_schedules(store: LibraryStore) -> int:
    """Controlla tutti gli schedule attivi e sincronizza quelli scaduti."""
    sched_store = get_schedule_store()
    schedules = sched_store.list_schedules()
    now = time.time()
    synced_count = 0

    for sched in schedules:
        if sched.enabled and sched.next_sync_at <= now:
            try:
                run_schedule_sync(sched.id, store)
                synced_count += 1
            except Exception as ex:
                _logger.warning("Errore sincronizzazione schedule %s: %s", sched.id, ex)

    return synced_count


def start_connector_scheduler_thread(
    store: LibraryStore,
    interval_sec: int = 30,
    stop_event: threading.Event | None = None,
) -> threading.Thread:
    """Avvia un daemon thread per monitorare ed eseguire periodicamente i connettori schedulati."""

    def _worker():
        _logger.info("Connector scheduler daemon avviato (controllo ogni %ds)", interval_sec)
        while stop_event is None or not stop_event.is_set():
            try:
                sync_due_schedules(store)
            except Exception as e:
                _logger.error("Eccezione nel ciclo di connector scheduler: %s", e)
            if stop_event is not None:
                if stop_event.wait(timeout=interval_sec):
                    break
            else:
                time.sleep(interval_sec)
        _logger.info("Connector scheduler daemon terminato.")

    thread = threading.Thread(target=_worker, daemon=True, name="ermes-connector-scheduler")
    thread.start()
    return thread
