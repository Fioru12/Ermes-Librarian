"""Persistence layer for Ermes Knowledge libraries.

SQLite keeps the first local-first release easy to run. This module owns the
domain contract so a later PostgreSQL implementation can replace it without
changing the API surface.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from core.library_embeddings import cosine_similarity, embed_texts, min_semantic_score

# Common function words must not become the only "evidence" for a RAG answer.
# This compact local-first baseline deliberately keeps a conservative bilingual
# list; a production language analyser can replace it behind this same method.
_QUERY_STOPWORDS = {
    "a", "ad", "al", "alla", "alle", "che", "chi", "come", "con", "cosa", "dei", "del", "della", "delle",
    "di", "dove", "e", "gli", "i", "il", "in", "la", "le", "lo", "nei", "nelle", "per", "quali", "quando",
    "quale", "sono", "sul", "sulla", "the", "and", "are", "before", "for", "from", "how", "is", "it",
    "of", "on", "or", "to", "was", "what", "when", "where", "who", "why", "with", "your",
    "document", "documents", "documenti", "library", "biblioteca", "policy", "procedure",
}


def storage_relative_path(library_id: str, stored_filename: str) -> str:
    """Location to record for a document, relative to the storage root.

    Absolute paths must never be written: the database would stop being
    portable. A library moved into a container, restored from backup into a
    different directory, or copied to another machine would keep pointing at
    the ingesting machine's filesystem, and every original would become
    unreachable while the rows still looked healthy.
    """
    return f"{library_id}/{stored_filename}"


def resolve_storage_path(stored: str, storage_root: str | Path) -> Path:
    """Resolve a recorded document location against the current storage root.

    Handles three cases: a relative path (what is written now), an absolute
    path that still resolves (same machine, same layout), and an absolute path
    written by another machine — including a Windows path seen from Linux,
    where the whole string is a single POSIX component. The last case is
    re-anchored under the current root by its final two segments, which is the
    `<library_id>/<stored filename>` layout every writer produces.

    The caller must still confirm the result stays inside the storage root:
    this function locates a file, it does not authorise reading it.
    """
    root = Path(storage_root)
    segments = [s for s in stored.replace("\\", "/").split("/") if s not in ("", ".")]
    looks_absolute = stored.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", stored)

    if not looks_absolute:
        return root.joinpath(*segments) if segments else root

    candidate = Path(stored)
    try:
        if candidate.is_file():
            return candidate
    except OSError:
        # Probing a path outside the storage root can fail rather than return
        # False — on Linux, stat() of an unreadable location raises
        # PermissionError. Treat any such failure as "not usable here" and fall
        # through to re-anchoring, instead of letting it reach the caller.
        pass
    if len(segments) >= 2:
        return root / segments[-2] / segments[-1]
    return candidate


class LibraryNotFoundError(KeyError):
    """Raised when a requested library does not exist."""


class LibraryAccessError(PermissionError):
    """Raised when a user cannot access a private library."""


class LibraryStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._lock = threading.RLock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self):
        """Open, commit/rollback, and always close a SQLite connection.

        `sqlite3.Connection.__exit__` commits but does not close; leaving it
        open keeps Windows file handles alive and blocks cleanup/backup.
        """
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS libraries (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    visibility TEXT NOT NULL DEFAULT 'private',
                    assistant_mode TEXT NOT NULL DEFAULT 'evidence_only',
                    assistant_provider TEXT NOT NULL DEFAULT '',
                    owner_id TEXT NOT NULL DEFAULT 'system',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'queued',
                    extracted_text TEXT NOT NULL DEFAULT '',
                    source_units INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS documents_by_library
                    ON documents(library_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS library_members (
                    library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('viewer', 'editor')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (library_id, username)
                );
                CREATE INDEX IF NOT EXISTS members_by_username
                    ON library_members(username, library_id);

                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    source_locator TEXT NOT NULL DEFAULT '',
                    embedding_json TEXT NOT NULL DEFAULT '',
                    embedding_model TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(document_id, ordinal)
                );
                CREATE INDEX IF NOT EXISTS chunks_by_document
                    ON document_chunks(document_id, ordinal);

                CREATE TABLE IF NOT EXISTS document_versions (
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (document_id, version)
                );
                CREATE INDEX IF NOT EXISTS versions_by_document
                    ON document_versions(document_id, version DESC);

                CREATE TABLE IF NOT EXISTS document_acls (
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    username TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (document_id, username)
                );
                CREATE INDEX IF NOT EXISTS acls_by_username
                    ON document_acls(username);

                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
                    document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_by_library
                    ON ingestion_jobs(library_id, created_at DESC);
                """
            )
            # SQLite does not support ADD COLUMN IF NOT EXISTS.  This keeps
            # local developer databases created by earlier v0.1 builds usable.
            columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
            if "extracted_text" not in columns:
                connection.execute("ALTER TABLE documents ADD COLUMN extracted_text TEXT NOT NULL DEFAULT ''")
            if "source_units" not in columns:
                connection.execute("ALTER TABLE documents ADD COLUMN source_units INTEGER NOT NULL DEFAULT 0")
            chunk_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_chunks)")}
            if "source_locator" not in chunk_columns:
                connection.execute("ALTER TABLE document_chunks ADD COLUMN source_locator TEXT NOT NULL DEFAULT ''")
            if "embedding_json" not in chunk_columns:
                connection.execute("ALTER TABLE document_chunks ADD COLUMN embedding_json TEXT NOT NULL DEFAULT ''")
            if "embedding_model" not in chunk_columns:
                connection.execute("ALTER TABLE document_chunks ADD COLUMN embedding_model TEXT NOT NULL DEFAULT ''")
            library_columns = {row[1] for row in connection.execute("PRAGMA table_info(libraries)")}
            if "owner_id" not in library_columns:
                connection.execute("ALTER TABLE libraries ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'system'")
            if "assistant_mode" not in library_columns:
                connection.execute("ALTER TABLE libraries ADD COLUMN assistant_mode TEXT NOT NULL DEFAULT 'evidence_only'")
            if "assistant_provider" not in library_columns:
                connection.execute("ALTER TABLE libraries ADD COLUMN assistant_provider TEXT NOT NULL DEFAULT ''")
            # Backfill the immutable snapshot for databases created before
            # version history existed. The current document is version 1 there.
            connection.execute(
                """
                INSERT OR IGNORE INTO document_versions
                    (document_id, version, filename, media_type, size_bytes, content_hash, storage_path, created_at)
                SELECT id, version, filename, media_type, size_bytes, content_hash, storage_path, created_at
                FROM documents
                """
            )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        return dict(row)

    @staticmethod
    def _search_token(token: str) -> str:
        """Small deterministic Italian-friendly normalization for MVP search.

        It deliberately is not a linguistic model; trimming a terminal vowel
        avoids missing obvious forms such as ``richiesta`` / ``richieste``
        while semantic retrieval remains an optional later ranking signal.
        """
        normalized = token.lower()
        return normalized[:-1] if len(normalized) > 4 and normalized[-1] in "aeiou" else normalized

    @staticmethod
    def _can_access(library: dict, actor: dict | None, write: bool = False, member_role: str | None = None) -> bool:
        if actor is None:
            return True
        if actor.get("role") == "admin":
            return True
        if library.get("owner_id") == actor.get("username"):
            return True
        if member_role == "editor":
            return True
        if member_role == "viewer" and not write:
            return True
        return library.get("visibility") == "shared" and not write

    def _membership_roles(self, username: str) -> dict[str, str]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT library_id, role FROM library_members WHERE username = ?", (username,)
            ).fetchall()
        return {row["library_id"]: row["role"] for row in rows}

    def _membership_role(self, library_id: str, username: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT role FROM library_members WHERE library_id = ? AND username = ?", (library_id, username)
            ).fetchone()
        return row["role"] if row else None

    @staticmethod
    def _can_manage_members(library: dict, actor: dict | None) -> bool:
        return bool(actor and (actor.get("role") == "admin" or library.get("owner_id") == actor.get("username")))

    @classmethod
    def _access_role(cls, library: dict, actor: dict | None, member_role: str | None = None) -> str:
        """Return the effective library role without trusting the client UI."""
        if actor is None:
            return "system"
        if actor.get("role") == "admin":
            return "admin"
        if library.get("owner_id") == actor.get("username"):
            return "owner"
        if member_role in {"viewer", "editor"}:
            return member_role
        return "viewer" if library.get("visibility") == "shared" else "none"

    def list_libraries(self, actor: dict | None = None) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT libraries.*, COUNT(documents.id) AS document_count
                FROM libraries
                LEFT JOIN documents ON documents.library_id = libraries.id
                GROUP BY libraries.id
                ORDER BY libraries.created_at DESC
                """
            ).fetchall()
        memberships = self._membership_roles(actor["username"]) if actor and actor.get("role") != "admin" else {}
        visible: list[dict] = []
        for row in rows:
            library = self._row(row)
            member_role = memberships.get(library["id"])
            if self._can_access(library, actor, member_role=member_role):
                library["access_role"] = self._access_role(library, actor, member_role)
                visible.append(library)
        return visible

    def create_library(self, name: str, description: str = "", visibility: str = "private", owner_id: str = "system") -> dict:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Il nome della biblioteca è obbligatorio.")
        if len(normalized_name) > 120:
            raise ValueError("Il nome della biblioteca può contenere al massimo 120 caratteri.")
        if visibility not in {"private", "shared"}:
            raise ValueError("La visibilità deve essere 'private' o 'shared'.")

        now = self._timestamp()
        library = {
            "id": str(uuid.uuid4()),
            "name": normalized_name,
            "description": description.strip()[:500],
            "visibility": visibility,
            # Cloud generation is opt-in per library, even if an instance has
            # credentials configured for it.
            "assistant_mode": "evidence_only",
            "assistant_provider": "",
            "owner_id": owner_id,
            "created_at": now,
            "updated_at": now,
            "document_count": 0,
        }
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO libraries (id, name, description, visibility, assistant_mode, assistant_provider, owner_id, created_at, updated_at)
                VALUES (:id, :name, :description, :visibility, :assistant_mode, :assistant_provider, :owner_id, :created_at, :updated_at)
                """,
                library,
            )
        return library

    def set_assistant_mode(self, library_id: str, mode: str) -> dict:
        """Backward-compatible shortcut for a policy without named provider."""
        return self.set_assistant_policy(library_id, mode)

    def set_assistant_policy(self, library_id: str, mode: str, provider_name: str = "") -> dict:
        """Persist one explicit per-library generation and egress policy."""
        if mode not in {"evidence_only", "local_ollama", "approved_openrouter", "approved_provider"}:
            raise ValueError("Modalita assistente non valida.")
        provider_name = provider_name.strip()
        if mode == "approved_provider" and not provider_name:
            raise ValueError("Seleziona un provider approvato.")
        if mode != "approved_provider":
            provider_name = ""
        now = self._timestamp()
        with self._lock, self._connection() as connection:
            updated = connection.execute(
                "UPDATE libraries SET assistant_mode = ?, assistant_provider = ?, updated_at = ? WHERE id = ?",
                (mode, provider_name, now, library_id),
            ).rowcount
        if not updated:
            raise LibraryNotFoundError(library_id)
        return self.get_library(library_id)

    def get_library(self, library_id: str, actor: dict | None = None, write: bool = False) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT libraries.*, COUNT(documents.id) AS document_count
                FROM libraries
                LEFT JOIN documents ON documents.library_id = libraries.id
                WHERE libraries.id = ?
                GROUP BY libraries.id
                """,
                (library_id,),
            ).fetchone()
        if row is None:
            raise LibraryNotFoundError(library_id)
        library = self._row(row)
        member_role = self._membership_role(library_id, actor["username"]) if actor and actor.get("role") != "admin" else None
        if not self._can_access(library, actor, write, member_role):
            raise LibraryAccessError(library_id)
        library["access_role"] = self._access_role(library, actor, member_role)
        return library

    def list_library_members(self, library_id: str) -> list[dict]:
        library = self.get_library(library_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT username, role, created_at, updated_at FROM library_members WHERE library_id = ? ORDER BY username",
                (library_id,),
            ).fetchall()
        return [{"username": library["owner_id"], "role": "owner", "created_at": library["created_at"], "updated_at": library["updated_at"]}, *[self._row(row) for row in rows]]

    def set_library_member(self, library_id: str, username: str, role: str) -> dict:
        self.get_library(library_id)
        normalized_username = username.strip()
        if not normalized_username:
            raise ValueError("Utente collaboratore obbligatorio")
        if role not in {"viewer", "editor"}:
            raise ValueError("Ruolo collaboratore non valido")
        library = self.get_library(library_id)
        if normalized_username == library["owner_id"]:
            raise ValueError("Il proprietario non puo essere aggiunto come collaboratore")
        now = self._timestamp()
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO library_members (library_id, username, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(library_id, username) DO UPDATE SET role = excluded.role, updated_at = excluded.updated_at
                """,
                (library_id, normalized_username, role, now, now),
            )
        return {"username": normalized_username, "role": role}

    def remove_library_member(self, library_id: str, username: str) -> bool:
        with self._lock, self._connection() as connection:
            deleted = connection.execute(
                "DELETE FROM library_members WHERE library_id = ? AND username = ?", (library_id, username.strip())
            ).rowcount
        return bool(deleted)

    def can_manage_library_members(self, library_id: str, actor: dict | None) -> bool:
        library = self.get_library(library_id, actor)
        return self._can_manage_members(library, actor)

    # ============================================================
    # Document-level ACL
    # ============================================================
    # Un documento senza righe in document_acls segue le regole di accesso
    # della libreria. Un documento CON righe e' visibile solo ad admin, al
    # proprietario della libreria e agli utenti elencati: la lista e' una
    # allow-list esplicita, non un'aggiunta ai permessi base.

    @staticmethod
    def _actor_bypasses_document_acl(library: dict, actor: dict | None) -> bool:
        """Admin e proprietario vedono sempre tutto; None e' il sistema."""
        return actor is None or actor.get("role") == "admin" or library.get("owner_id") == actor.get("username")

    def _hidden_document_ids(self, connection: sqlite3.Connection, library: dict, actor: dict | None) -> set[str]:
        if self._actor_bypasses_document_acl(library, actor):
            return set()
        rows = connection.execute(
            """
            SELECT DISTINCT d.id
            FROM documents d
            JOIN document_acls a ON a.document_id = d.id
            WHERE d.library_id = ?
              AND d.id NOT IN (SELECT document_id FROM document_acls WHERE username = ?)
            """,
            (library["id"], actor["username"] if actor else ""),
        ).fetchall()
        return {row["id"] for row in rows}

    def list_document_acl(self, library_id: str, document_id: str) -> list[dict]:
        self.get_document(library_id, document_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT username, created_at FROM document_acls WHERE document_id = ? ORDER BY username",
                (document_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def set_document_acl(self, library_id: str, document_id: str, usernames: list[str]) -> dict:
        """Replace the whole allow-list. An empty list removes the restriction."""
        self.get_document(library_id, document_id)
        cleaned = sorted({username.strip() for username in usernames if username and username.strip()})
        now = self._timestamp()
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM document_acls WHERE document_id = ?", (document_id,))
            connection.executemany(
                "INSERT INTO document_acls (document_id, username, created_at) VALUES (?, ?, ?)",
                [(document_id, username, now) for username in cleaned],
            )
        return {"document_id": document_id, "usernames": cleaned}

    def list_documents(self, library_id: str, actor: dict | None = None) -> list[dict]:
        library = self.get_library(library_id, actor)
        with self._lock, self._connection() as connection:
            hidden = self._hidden_document_ids(connection, library, actor)
            rows = connection.execute(
                """
                SELECT * FROM documents
                WHERE library_id = ?
                ORDER BY created_at DESC
                """,
                (library_id,),
            ).fetchall()
        return [self._row(row) for row in rows if row["id"] not in hidden]

    def start_ingestion_job(self, library_id: str, filename: str, document_id: str | None = None) -> dict:
        self.get_library(library_id)
        job = {"id": str(uuid.uuid4()), "library_id": library_id, "document_id": document_id, "filename": filename,
               "status": "queued", "error_message": "", "created_at": self._timestamp(), "completed_at": None}
        with self._lock, self._connection() as connection:
            connection.execute(
                """INSERT INTO ingestion_jobs (id, library_id, document_id, filename, status, error_message, created_at, completed_at)
                   VALUES (:id, :library_id, :document_id, :filename, :status, :error_message, :created_at, :completed_at)""",
                job,
            )
        return job

    def finish_ingestion_job(self, job_id: str, status: str, document_id: str | None = None, error_message: str = "") -> None:
        if status not in {"ready", "failed"}:
            raise ValueError("Stato job non valido")
        with self._lock, self._connection() as connection:
            connection.execute(
                """UPDATE ingestion_jobs SET status = ?, document_id = ?, error_message = ?, completed_at = ? WHERE id = ?""",
                (status, document_id, error_message[:500], self._timestamp(), job_id),
            )

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

    def pending_ingestion_jobs(self) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM ingestion_jobs WHERE status = 'queued' ORDER BY created_at ASC").fetchall()
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
            documents = connection.execute(
                "SELECT id, filename, storage_path FROM documents"
            ).fetchall()
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

        orphan_files: list[str] = []
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and path not in expected_files:
                    orphan_files.append(path.relative_to(root).as_posix())

        ready_without_chunks = sorted(
            row["document_id"] for row in chunk_stats
            if row["status"] == "ready" and row["chunk_count"] == 0
        )
        partially_embedded = sorted(
            row["document_id"] for row in chunk_stats
            if row["chunk_count"] > 0 and 0 < (row["embedded_count"] or 0) < row["chunk_count"]
        )
        mismatched_models = sorted({
            row["document_id"] for row in models
            if expected_embed_model and row["embedding_model"] != expected_embed_model
        })

        issue_count = (
            len(missing_originals) + len(orphan_files) + len(ready_without_chunks)
            + len(partially_embedded) + len(mismatched_models)
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
            stuck = connection.execute(
                "SELECT id FROM ingestion_jobs WHERE status = 'processing'"
            ).fetchall()
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

    def get_document(self, library_id: str, document_id: str, actor: dict | None = None) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ? AND library_id = ?",
                (document_id, library_id),
            ).fetchone()
        if row is None:
            raise LibraryNotFoundError(document_id)
        document = self._row(row)
        if not self._actor_bypasses_document_acl({"owner_id": self._library_owner(library_id)}, actor):
            with self._connection() as connection:
                allowed = connection.execute(
                    "SELECT 1 FROM document_acls WHERE document_id = ? AND username = ?",
                    (document_id, actor["username"] if actor else ""),
                ).fetchone()
                restricted = connection.execute(
                    "SELECT 1 FROM document_acls WHERE document_id = ?",
                    (document_id,),
                ).fetchone()
            if restricted and not allowed:
                raise LibraryAccessError(document_id)
        return document

    def _library_owner(self, library_id: str) -> str:
        with self._connection() as connection:
            row = connection.execute("SELECT owner_id FROM libraries WHERE id = ?", (library_id,)).fetchone()
        return row["owner_id"] if row else ""

    def list_document_versions(self, library_id: str, document_id: str, actor: dict | None = None) -> list[dict]:
        self.get_document(library_id, document_id, actor)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT version, filename, media_type, size_bytes, content_hash, storage_path, created_at
                FROM document_versions WHERE document_id = ? ORDER BY version DESC
                """,
                (document_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def get_document_chunks(self, library_id: str, document_id: str, actor: dict | None = None) -> list[dict]:
        """Chunks of one document, ordered, after the same ACL check as get_document."""
        self.get_document(library_id, document_id, actor)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT ordinal, text, source_locator FROM document_chunks
                WHERE document_id = ? ORDER BY ordinal
                """,
                (document_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def replace_document_index(
        self,
        library_id: str,
        document_id: str,
        extracted_text: str,
        source_units: int,
        chunks: list[tuple[str, str]],
    ) -> dict:
        """Atomically replace derived text/chunks while retaining the original file."""
        self.get_document(library_id, document_id)
        now = self._timestamp()
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
            connection.execute(
                """
                UPDATE documents
                SET extracted_text = ?, source_units = ?, status = 'ready', updated_at = ?
                WHERE id = ? AND library_id = ?
                """,
                (extracted_text, source_units, now, document_id, library_id),
            )
            for ordinal, (text, locator) in enumerate(chunks):
                connection.execute(
                    """
                    INSERT INTO document_chunks (id, document_id, ordinal, text, source_locator, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), document_id, ordinal, text, locator, now),
                )
        return self.get_document(library_id, document_id)

    def search_documents(self, library_id: str, query: str, limit: int = 20) -> list[dict]:
        """Return only the result list for callers that do not need retrieval metadata."""
        results, _ = self.search_with_profile(library_id, query, limit)
        return results

    def search_with_profile(self, library_id: str, query: str, limit: int = 20, actor: dict | None = None) -> tuple[list[dict], dict]:
        """Retrieve chunks with a truthful local retrieval profile.

        Keyword matches are always available. When the index and the current
        query both have embeddings from the local Ollama endpoint, cosine
        similarity is added as a second signal. No external provider is ever
        used for retrieval.

        The optional actor filters out documents restricted by a document ACL:
        filtering happens here, before any citation can be built, so a hidden
        document cannot leak through search results either.
        """
        library = self.get_library(library_id, actor)
        normalized = query.strip()
        if not normalized:
            return [], {"mode": "keyword", "semantic_indexed_chunks": 0, "semantic_used": False}
        with self._connection() as connection:
            hidden = self._hidden_document_ids(connection, library, actor)
            rows = connection.execute(
                """
                SELECT documents.id AS document_id, documents.filename, documents.version, documents.content_hash,
                       document_chunks.id AS chunk_id, document_chunks.ordinal, document_chunks.text AS excerpt,
                       document_chunks.source_locator, document_chunks.embedding_json
                FROM document_chunks
                JOIN documents ON documents.id = document_chunks.document_id
                WHERE documents.library_id = ?
                ORDER BY documents.created_at DESC, document_chunks.ordinal ASC
                """,
                (library_id,),
            ).fetchall()
        rows = [row for row in rows if row["document_id"] not in hidden]
        tokens = [
            self._search_token(token)
            for token in re.findall(r"[\wÀ-ÿ]{3,}", normalized.lower())
            if token not in _QUERY_STOPWORDS
        ]
        indexed_chunks = sum(1 for row in rows if row["embedding_json"])
        query_embeddings = embed_texts([normalized]) if indexed_chunks else []
        query_embedding = query_embeddings[0] if query_embeddings else []
        semantic_used = bool(query_embedding and indexed_chunks)
        ranked: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            haystack = f"{row['filename']} {row['excerpt']}".lower()
            phrase_score = 100 if normalized.lower() in haystack else 0
            haystack_tokens = {self._search_token(token) for token in re.findall(r"[\wÀ-ÿ]{3,}", haystack)}
            token_score = sum(10 for token in tokens if token in haystack_tokens)
            semantic_score = 0.0
            if query_embedding and row["embedding_json"]:
                try:
                    semantic_score = max(0.0, cosine_similarity(query_embedding, json.loads(row["embedding_json"])))
                except (TypeError, ValueError):
                    semantic_score = 0.0
            if phrase_score or token_score or semantic_score >= min_semantic_score():
                ranked.append((phrase_score + token_score + (semantic_score * 40), row))
        ranked.sort(key=lambda item: (-item[0], item[1]["ordinal"]))
        results = [
            {
                **self._row(row),
                "relevance_score": round(score, 4),
                "citation": {
                    "document_id": row["document_id"],
                    "filename": row["filename"],
                    "version": row["version"],
                    "content_hash": f"sha256:{row['content_hash']}",
                    "chunk_id": row["chunk_id"],
                    "locator": row["source_locator"] or f"Passaggio {row['ordinal'] + 1}",
                },
            }
            for score, row in ranked[:max(1, min(limit, 50))]
        ]
        profile = {
            "mode": "hybrid_local" if semantic_used else "keyword",
            "semantic_indexed_chunks": indexed_chunks,
            "semantic_used": semantic_used,
        }
        return results, profile

    def store_chunk_embeddings(
        self, library_id: str, document_id: str, embeddings: list[list[float]], model_id: str,
    ) -> int:
        """Persist vectors derived from the current chunks; originals remain the source of truth."""
        self.get_document(library_id, document_id)
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT id FROM document_chunks WHERE document_id = ? ORDER BY ordinal", (document_id,)
            ).fetchall()
            if len(rows) != len(embeddings):
                return 0
            connection.executemany(
                "UPDATE document_chunks SET embedding_json = ?, embedding_model = ? WHERE id = ?",
                [(json.dumps(embedding, separators=(",", ":")), model_id, row["id"])
                 for row, embedding in zip(rows, embeddings)],
            )
        return len(embeddings)

    def add_document(
        self,
        library_id: str,
        filename: str,
        media_type: str,
        content: bytes,
        storage_path: str,
        extracted_text: str = "",
        source_units: int = 0,
        status: str = "ready",
        chunks: list[tuple[str, str]] | list[str] | None = None,
    ) -> dict:
        self.get_library(library_id)
        now = self._timestamp()
        document = {
            "id": str(uuid.uuid4()),
            "library_id": library_id,
            "filename": filename,
            "media_type": media_type or "application/octet-stream",
            "size_bytes": len(content),
            "content_hash": hashlib.sha256(content).hexdigest(),
            "storage_path": storage_path,
            "version": 1,
            "status": status,
            "extracted_text": extracted_text,
            "source_units": source_units,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock, self._connection() as connection:
            existing = connection.execute(
                "SELECT id, version, created_at FROM documents WHERE library_id = ? AND filename = ?",
                (library_id, filename),
            ).fetchone()
            if existing:
                document["id"] = existing["id"]
                document["version"] = existing["version"] + 1
                document["created_at"] = existing["created_at"]
                connection.execute(
                    """
                    UPDATE documents SET media_type = :media_type, size_bytes = :size_bytes,
                        content_hash = :content_hash, storage_path = :storage_path, version = :version,
                        status = :status, extracted_text = :extracted_text, source_units = :source_units,
                        updated_at = :updated_at WHERE id = :id
                    """,
                    document,
                )
                connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document["id"],))
            else:
                connection.execute(
                    """
                    INSERT INTO documents (
                        id, library_id, filename, media_type, size_bytes, content_hash,
                        storage_path, version, status, extracted_text, source_units, created_at, updated_at
                    ) VALUES (
                        :id, :library_id, :filename, :media_type, :size_bytes, :content_hash,
                        :storage_path, :version, :status, :extracted_text, :source_units, :created_at, :updated_at
                    )
                    """,
                    document,
                )
            connection.execute(
                """
                INSERT INTO document_versions
                    (document_id, version, filename, media_type, size_bytes, content_hash, storage_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (document["id"], document["version"], filename, document["media_type"], document["size_bytes"],
                 document["content_hash"], storage_path, now),
            )
            for ordinal, chunk in enumerate(chunks or []):
                text, locator = chunk if isinstance(chunk, tuple) else (chunk, f"Passaggio {ordinal + 1}")
                connection.execute(
                    """
                    INSERT INTO document_chunks (id, document_id, ordinal, text, source_locator, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), document["id"], ordinal, text, locator, now),
                )
        return document
