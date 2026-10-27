"""Ingestion job queue, dead-letter handling and index consistency."""

from __future__ import annotations

import uuid
from pathlib import Path

from core.library_store.base import StoreBase
from core.library_store.common import (
    resolve_storage_path,
)


class IngestionMixin(StoreBase):
    def start_ingestion_job(self, library_id: str, filename: str, document_id: str | None = None) -> dict:
        self.get_library(library_id)
        job = {
            "id": str(uuid.uuid4()),
            "library_id": library_id,
            "document_id": document_id,
            "filename": filename,
            "status": "queued",
            "error_message": "",
            "created_at": self._timestamp(),
            "completed_at": None,
        }
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO ingestion_jobs (id, library_id, document_id, filename, status, error_message, created_at, completed_at)
                   VALUES (:id, :library_id, :document_id, :filename, :status, :error_message, :created_at, :completed_at)""",
                job,
            )
        return job

    def finish_ingestion_job(
        self, job_id: str, status: str, document_id: str | None = None, error_message: str = ""
    ) -> None:
        if status not in {"ready", "failed"}:
            raise ValueError("Stato job non valido")
        with self._lock, self._connection() as connection:
            connection.execute(
                """UPDATE ingestion_jobs SET status = ?, document_id = ?, error_message = ?, completed_at = ? WHERE id = ?""",
                (status, document_id, error_message[:500], self._timestamp(), job_id),
            )

    def requeue_ingestion_job(self, job_id: str, max_attempts: int) -> bool:
        """Rimette in coda un job fallito per una causa transitoria.

        `attempts` conta i re-tentativi: con max_attempts=3 il job gira al
        massimo tre volte (attempts finisce a 2). E' il chiamante a
        decidere se la causa era transitoria (un modello di embedding
        irraggiungibile lo e', un PDF illeggibile no). Restituisce False se
        il job non e' in stato 'failed' o ha esaurito i tentativi.
        """
        with self._lock, self._connection() as connection:
            result = connection.execute(
                """UPDATE ingestion_jobs
                   SET status = 'queued', error_message = '', completed_at = NULL, attempts = attempts + 1
                   WHERE id = ? AND status = 'failed' AND attempts + 1 < ?""",
                (job_id, max_attempts),
            )
            requeued: bool = result.rowcount == 1
            return requeued

    def update_job_progress(self, job_id: str, processed_chunks: int, total_chunks: int) -> None:
        """Aggiorna lo stato di avanzamento per-chunk del job di indicizzazione."""
        with self._lock, self._connection() as connection:
            connection.execute(
                """UPDATE ingestion_jobs
                   SET processed_chunks = ?, total_chunks = ?
                   WHERE id = ?""",
                (processed_chunks, total_chunks, job_id),
            )

    def move_to_dead_letter(self, job_id: str, reason: str) -> None:
        """Sposta un job irrecuperabile o con tentativi esauriti nella Dead-Letter Queue (DLQ)."""
        with self._lock, self._connection() as connection:
            connection.execute(
                """UPDATE ingestion_jobs
                   SET status = 'dead_letter', dead_letter_reason = ?, error_message = ?, completed_at = ?
                   WHERE id = ?""",
                (reason[:500], reason[:500], self._timestamp(), job_id),
            )

    def reprocess_dead_letter_job(self, job_id: str) -> bool:
        """Rilancia un job precedentemente finito nella Dead-Letter Queue azzerando i tentativi."""
        with self._lock, self._connection() as connection:
            result = connection.execute(
                """UPDATE ingestion_jobs
                   SET status = 'queued', attempts = 0, error_message = '', dead_letter_reason = '', completed_at = NULL
                   WHERE id = ? AND status = 'dead_letter'""",
                (job_id,),
            )
            return bool(result.rowcount == 1)

    def list_dead_letter_jobs(self, library_id: str) -> list[dict]:
        """Elenca tutti i job finiti nella Dead-Letter Queue per una specifica biblioteca."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM ingestion_jobs WHERE library_id = ? AND status = 'dead_letter' ORDER BY created_at DESC""",
                (library_id,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def get_job_progress(self, job_id: str) -> dict | None:
        """Restituisce le metriche di avanzamento del job (chunk elaborati, totale, percentuale)."""
        job = self.get_ingestion_job(job_id)
        if not job:
            return None
        total = int(job.get("total_chunks") or 0)
        processed = int(job.get("processed_chunks") or 0)
        percent = (
            round((processed / total * 100.0), 1)
            if total > 0
            else (100.0 if job.get("status") == "ready" else 0.0)
        )
        return {
            "id": job["id"],
            "library_id": job["library_id"],
            "document_id": job.get("document_id"),
            "filename": job["filename"],
            "status": job["status"],
            "attempts": int(job.get("attempts") or 0),
            "processed_chunks": processed,
            "total_chunks": total,
            "progress_percent": percent,
            "error_message": job.get("error_message") or "",
            "dead_letter_reason": job.get("dead_letter_reason") or "",
            "created_at": job["created_at"],
            "completed_at": job.get("completed_at"),
        }

    def ingestion_queue_stats(self) -> dict[str, int]:
        with self._connection() as connection:
            rows = connection.execute("SELECT status, COUNT(*) AS n FROM ingestion_jobs GROUP BY status").fetchall()
        stats = {"queued": 0, "processing": 0, "ready": 0, "failed": 0, "dead_letter": 0}
        for row in rows:
            record = self._row(row)
            stats[str(record["status"])] = int(record["n"])
        return stats

    def get_ingestion_job(self, job_id: str) -> dict | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def claim_ingestion_job(self, job_id: str) -> dict | None:
        """Claim a queued job exactly once. Safe for a future separate worker."""
        with self._lock, self._connection() as connection:
            result = connection.execute(
                "UPDATE ingestion_jobs SET status = 'processing' WHERE id = ? AND status = 'queued'", (job_id,)
            )
            if result.rowcount != 1:
                return None
            row = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def claim_next_ingestion_job(self, worker_id: str = "") -> dict | None:
        """Claim the oldest queued ingestion job atomically.

        On PostgreSQL (Phase 3), uses `SELECT ... FOR UPDATE SKIP LOCKED` inside a single
        atomic statement to avoid worker collision across distributed processes.
        On SQLite, falls back to two-step select + atomic update under process lock.
        """
        if self._is_postgres:
            sql = """
                UPDATE ingestion_jobs
                SET status = 'processing'
                WHERE id = (
                    SELECT id FROM ingestion_jobs
                    WHERE status = 'queued'
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING *
            """
            row = self._exec_returning(sql)
            return self._row(row) if row else None

        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT id FROM ingestion_jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            job_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
            result = connection.execute(
                "UPDATE ingestion_jobs SET status = 'processing' WHERE id = ? AND status = 'queued'",
                (job_id,),
            )
            if result.rowcount != 1:
                return None
            claimed_row = connection.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(claimed_row) if claimed_row else None


    def pending_ingestion_jobs(self) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM ingestion_jobs WHERE status = 'queued' ORDER BY created_at ASC"
            ).fetchall()
        return [self._row(row) for row in rows]

    def verify_index_consistency(self, storage_root: str | Path, expected_embed_model: str | None = None) -> dict:
        """Cross-check database rows against originals and the derived index.

        The SQLite rows are the source of truth; a backup/restore cycle or a
        half-finished upload can drift in four ways this reports:

        - ``missing_originals``: rows whose original file is gone (download
          and reindex would fail while the row looks healthy);
        - ``orphan_files``: files under the storage root no row references
          (an upload that failed between file write and insert);
        - ``ready_without_chunks``: documents marked ready with zero chunks,
          silently invisible to retrieval;
        - embedding issues per document: partially embedded chunk sets, or
          embeddings produced by a model different from the expected one —
          both silently degrade semantic retrieval to keyword-only.

        Identifiers and counts only, never document content: the report is
        safe to log or expose.
        """
        root = Path(storage_root)
        with self._connection() as connection:
            documents = connection.execute("SELECT id, filename, storage_path FROM documents").fetchall()
            # Le versioni precedenti restano nello storage, referenziate solo da `document_versions`:
            # non sono orfane (prima la verifica le segnalava, e la pulizia le avrebbe cancellate).
            version_paths = connection.execute("SELECT storage_path FROM document_versions").fetchall()
            chunk_stats = connection.execute(
                """
                SELECT d.id AS document_id, d.status,
                       COUNT(c.id) AS chunk_count,
                       SUM(CASE WHEN c.embedding_json <> '' THEN 1 ELSE 0 END) AS embedded_count
                FROM documents d LEFT JOIN document_chunks c ON c.document_id = d.id
                GROUP BY d.id
                """
            ).fetchall()
            models = connection.execute(
                """
                SELECT DISTINCT d.id AS document_id, c.embedding_model
                FROM documents d JOIN document_chunks c ON c.document_id = d.id
                WHERE c.embedding_model <> ''
                """
            ).fetchall()

        missing_originals: list[dict] = []
        expected_files: set[Path] = set()
        for row in documents:
            path = resolve_storage_path(row["storage_path"], root)
            expected_files.add(path)
            try:
                inside_root = path.resolve().is_relative_to(root.resolve())
            except (OSError, ValueError):
                inside_root = False
            if not (inside_root and path.is_file()):
                missing_originals.append({"document_id": row["id"], "filename": row["filename"]})

        for row in version_paths:
            expected_files.add(resolve_storage_path(row["storage_path"], root))

        orphan_files: list[str] = []
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and path not in expected_files:
                    orphan_files.append(path.relative_to(root).as_posix())

        ready_without_chunks = sorted(
            row["document_id"] for row in chunk_stats if row["status"] == "ready" and row["chunk_count"] == 0
        )
        partially_embedded = sorted(
            row["document_id"]
            for row in chunk_stats
            if row["chunk_count"] > 0 and 0 < (row["embedded_count"] or 0) < row["chunk_count"]
        )
        mismatched_models = sorted(
            {
                row["document_id"]
                for row in models
                if expected_embed_model and row["embedding_model"] != expected_embed_model
            }
        )

        issue_count = (
            len(missing_originals)
            + len(orphan_files)
            + len(ready_without_chunks)
            + len(partially_embedded)
            + len(mismatched_models)
        )
        return {
            "ok": issue_count == 0,
            "issue_count": issue_count,
            "checked_documents": len(documents),
            "missing_originals": missing_originals,
            "orphan_files": orphan_files,
            "ready_without_chunks": ready_without_chunks,
            "partially_embedded_documents": partially_embedded,
            "embedding_model_mismatch_documents": mismatched_models,
        }

    def recover_stale_ingestion_jobs(self) -> int:
        """Requeue jobs left in 'processing' by an interrupted run.

        ``claim_ingestion_job`` moves a job out of 'queued' before parsing, and
        ``finish_ingestion_job`` is the only writer that ends that state. A
        crash between the two leaves the job outside every queue forever while
        looking active to the UI. Startup calls this before reading the pending
        queue, so an interrupted upload resumes exactly like one accepted just
        before a clean restart.
        """
        with self._lock, self._connection() as connection:
            stuck = connection.execute("SELECT id FROM ingestion_jobs WHERE status = 'processing'").fetchall()
            if stuck:
                connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = 'queued', error_message = '', completed_at = NULL
                    WHERE status = 'processing'
                    """
                )
        return len(stuck)

    def mark_document_status(self, library_id: str, document_id: str, status: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE id = ? AND library_id = ?",
                (status, self._timestamp(), document_id, library_id),
            )

    def list_ingestion_jobs(self, library_id: str, limit: int = 20) -> list[dict]:
        self.get_library(library_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM ingestion_jobs WHERE library_id = ? ORDER BY created_at DESC LIMIT ?",
                (library_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._row(row) for row in rows]
