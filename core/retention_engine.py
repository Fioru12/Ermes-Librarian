"""Enterprise Document Lifecycle, Retention & Legal Hold Engine.

Provides GDPR Article 17 ("Right to be Forgotten") & ISO 27001 data retention
compliance for enterprise libraries. Supports custom retention periods, legal hold
protections, and automated archival / soft deletion / cryptographic purging.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from config import cfg
from core.governance import append_audit

_logger = logging.getLogger(__name__)

RetentionAction = Literal["archive", "soft_delete", "purge"]
RetentionStatus = Literal["active", "archived", "soft_deleted", "purged"]


@dataclass
class LibraryRetentionPolicy:
    library_id: str
    retention_days: int  # 0 means indefinite retention (no auto-expiry)
    action: RetentionAction
    created_at: str
    updated_at: str


@dataclass
class DocumentRetentionRecord:
    document_id: str
    library_id: str
    filename: str
    created_at: str
    expires_at: str | None
    legal_hold: bool
    legal_hold_reason: str
    legal_hold_by: str
    status: RetentionStatus
    purged_at: str | None
    sha256: str


class RetentionEngine:
    """Manages document retention policies, legal holds, and lifecycle enforcement."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._db_path = Path(cfg.BASE_DIR) / "retention_policies.db"
        else:
            self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS library_retention_policies (
                    library_id TEXT PRIMARY KEY,
                    retention_days INTEGER NOT NULL DEFAULT 0,
                    action TEXT NOT NULL DEFAULT 'archive',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_retention_overrides (
                    document_id TEXT PRIMARY KEY,
                    library_id TEXT NOT NULL,
                    legal_hold INTEGER NOT NULL DEFAULT 0,
                    legal_hold_reason TEXT NOT NULL DEFAULT '',
                    legal_hold_by TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    purged_at TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def set_library_policy(
        self,
        library_id: str,
        retention_days: int,
        action: RetentionAction = "archive",
        actor: str = "system",
    ) -> LibraryRetentionPolicy:
        """Configures or updates retention policy for a library."""
        if retention_days < 0:
            raise ValueError("I giorni di conservazione non possono essere negativi.")
        if action not in ("archive", "soft_delete", "purge"):
            raise ValueError(f"Azione di conservazione non valida: {action}")

        now = datetime.now(UTC).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO library_retention_policies (library_id, retention_days, action, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(library_id) DO UPDATE SET
                    retention_days = excluded.retention_days,
                    action = excluded.action,
                    updated_at = excluded.updated_at
                """,
                (library_id, retention_days, action, now, now),
            )
            conn.commit()

        append_audit(
            cfg.AUDIT_FILE,
            "retention_policy_updated",
            actor,
            {
                "library_id": library_id,
                "retention_days": retention_days,
                "action": action,
            },
        )
        return LibraryRetentionPolicy(
            library_id=library_id,
            retention_days=retention_days,
            action=action,
            created_at=now,
            updated_at=now,
        )

    def get_library_policy(self, library_id: str) -> LibraryRetentionPolicy | None:
        """Retrieves retention policy for a library."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM library_retention_policies WHERE library_id = ?",
                (library_id,),
            ).fetchone()
            if not row:
                return None
            return LibraryRetentionPolicy(
                library_id=row["library_id"],
                retention_days=row["retention_days"],
                action=row["action"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def set_document_legal_hold(
        self,
        library_id: str,
        document_id: str,
        legal_hold: bool,
        reason: str = "",
        actor: str = "system",
    ) -> dict[str, Any]:
        """Applies or removes legal hold protection on a specific document."""
        now = datetime.now(UTC).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO document_retention_overrides (
                    document_id, library_id, legal_hold, legal_hold_reason, legal_hold_by, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'active', ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    legal_hold = excluded.legal_hold,
                    legal_hold_reason = excluded.legal_hold_reason,
                    legal_hold_by = excluded.legal_hold_by,
                    updated_at = excluded.updated_at
                """,
                (document_id, library_id, 1 if legal_hold else 0, reason, actor, now),
            )
            conn.commit()

        append_audit(
            cfg.AUDIT_FILE,
            "legal_hold_modified",
            actor,
            {"library_id": library_id, "document_id": document_id, "legal_hold": legal_hold, "reason": reason},
        )

        return {
            "document_id": document_id,
            "library_id": library_id,
            "legal_hold": legal_hold,
            "legal_hold_reason": reason,
            "legal_hold_by": actor,
            "updated_at": now,
        }

    def get_document_retention_status(
        self, library_id: str, document_id: str
    ) -> dict[str, Any]:
        """Returns the retention and legal hold status for a document."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM document_retention_overrides WHERE document_id = ? AND library_id = ?",
                (document_id, library_id),
            ).fetchone()
            if not row:
                return {
                    "document_id": document_id,
                    "library_id": library_id,
                    "legal_hold": False,
                    "legal_hold_reason": "",
                    "legal_hold_by": "",
                    "status": "active",
                    "purged_at": None,
                }
            return {
                "document_id": row["document_id"],
                "library_id": row["library_id"],
                "legal_hold": bool(row["legal_hold"]),
                "legal_hold_reason": row["legal_hold_reason"],
                "legal_hold_by": row["legal_hold_by"],
                "status": row["status"],
                "purged_at": row["purged_at"],
            }

    def evaluate_retention(
        self,
        library_id: str | None = None,
        dry_run: bool = False,
        store: Any = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        """Evaluates retention policies and applies actions to expired documents.

        Respects legal_hold protections unconditionally.
        """
        if store is None:
            from core.library_store import LibraryStore

            store = LibraryStore(cfg.LIBRARY_DB_PATH)

        now = datetime.now(UTC)
        results: dict[str, Any] = {
            "evaluated_at": now.isoformat(),
            "dry_run": dry_run,
            "total_documents_checked": 0,
            "archived": [],
            "soft_deleted": [],
            "purged": [],
            "legal_hold_protected": [],
        }

        with self._connection() as conn:
            if library_id:
                policy_rows = conn.execute(
                    "SELECT * FROM library_retention_policies WHERE library_id = ? AND retention_days > 0",
                    (library_id,),
                ).fetchall()
            else:
                policy_rows = conn.execute(
                    "SELECT * FROM library_retention_policies WHERE retention_days > 0"
                ).fetchall()

            for p_row in policy_rows:
                lib_id = p_row["library_id"]
                ret_days = p_row["retention_days"]
                action: RetentionAction = p_row["action"]
                cutoff_date = now - timedelta(days=ret_days)

                try:
                    docs = store.list_documents(lib_id)
                except Exception as e:
                    _logger.warning("Errore recupero documenti per libreria %s: %s", lib_id, e)
                    continue

                for doc in docs:
                    doc_id = doc["id"]
                    results["total_documents_checked"] += 1

                    # Check doc creation date
                    created_raw = doc.get("created_at") or doc.get("updated_at")
                    try:
                        doc_created = datetime.fromisoformat(created_raw)
                        if doc_created.tzinfo is None:
                            doc_created = doc_created.replace(tzinfo=UTC)
                    except (ValueError, TypeError):
                        continue

                    if doc_created > cutoff_date:
                        # Document is still within retention period
                        continue

                    # Check legal hold
                    hold_row = conn.execute(
                        "SELECT legal_hold, legal_hold_reason FROM document_retention_overrides WHERE document_id = ?",
                        (doc_id,),
                    ).fetchone()
                    if hold_row and hold_row["legal_hold"]:
                        results["legal_hold_protected"].append({
                            "document_id": doc_id,
                            "library_id": lib_id,
                            "filename": doc.get("filename"),
                            "reason": hold_row["legal_hold_reason"],
                        })
                        continue

                    # Apply lifecycle action
                    item_info = {
                        "document_id": doc_id,
                        "library_id": lib_id,
                        "filename": doc.get("filename"),
                        "created_at": doc_created.isoformat(),
                        "action": action,
                    }

                    if action == "archive":
                        results["archived"].append(item_info)
                        if not dry_run:
                            try:
                                store.mark_document_status(lib_id, doc_id, status="archived")
                                conn.execute(
                                    """
                                    INSERT INTO document_retention_overrides (document_id, library_id, status, updated_at)
                                    VALUES (?, ?, 'archived', ?)
                                    ON CONFLICT(document_id) DO UPDATE SET status = 'archived', updated_at = excluded.updated_at
                                    """,
                                    (doc_id, lib_id, now.isoformat()),
                                )
                                conn.commit()
                            except Exception as err:
                                _logger.error("Errore archiviazione doc %s: %s", doc_id, err)
                    elif action == "soft_delete":
                        results["soft_deleted"].append(item_info)
                        if not dry_run:
                            try:
                                store.mark_document_status(lib_id, doc_id, status="soft_deleted")
                                conn.execute(
                                    """
                                    INSERT INTO document_retention_overrides (document_id, library_id, status, updated_at)
                                    VALUES (?, ?, 'soft_deleted', ?)
                                    ON CONFLICT(document_id) DO UPDATE SET status = 'soft_deleted', updated_at = excluded.updated_at
                                    """,
                                    (doc_id, lib_id, now.isoformat()),
                                )
                                conn.commit()
                            except Exception as err:
                                _logger.error("Errore soft delete doc %s: %s", doc_id, err)
                    elif action == "purge":
                        results["purged"].append(item_info)
                        if not dry_run:
                            try:
                                store.delete_document(lib_id, doc_id)
                                conn.execute(
                                    """
                                    INSERT INTO document_retention_overrides (document_id, library_id, status, purged_at, updated_at)
                                    VALUES (?, ?, 'purged', ?, ?)
                                    ON CONFLICT(document_id) DO UPDATE SET status = 'purged', purged_at = excluded.purged_at, updated_at = excluded.updated_at
                                    """,
                                    (doc_id, lib_id, now.isoformat(), now.isoformat()),
                                )
                                conn.commit()
                                append_audit(
                                    cfg.AUDIT_FILE,
                                    "document_retention_purged",
                                    actor,
                                    {"library_id": lib_id, "document_id": doc_id, "filename": doc.get("filename"), "sha256": doc.get("content_hash")},
                                )
                            except Exception as err:
                                _logger.error("Errore purge doc %s: %s", doc_id, err)

        return results


_retention_engine: RetentionEngine | None = None


def get_retention_engine() -> RetentionEngine:
    """Singleton getter for RetentionEngine."""
    global _retention_engine
    if _retention_engine is None:
        _retention_engine = RetentionEngine()
    return _retention_engine
