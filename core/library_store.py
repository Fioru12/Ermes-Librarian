"""Persistence layer for Ermes Knowledge libraries.

SQLite keeps the first local-first release easy to run. This module owns the
domain contract so a later PostgreSQL implementation can replace it without
changing the API surface.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import cfg
from core.database_backend import INTEGRITY_ERRORS, Backend, SqliteBackend, create_backend
from core.library_embeddings import cosine_similarity, embed_texts, min_semantic_score
from core.query_expander import expand_query
from core.search_cache import get_search_cache

_logger = logging.getLogger(__name__)


def _resolve_backend(database_path: str | Path | None, database_url: str | None = None) -> Backend:
    """Scegli il backend: URL esplicito, altrimenti ERMES_DATABASE_URL, altrimenti il path SQLite.

    `database_url` esiste perche' `cfg` e' un frozen dataclass costruito
    all'import: un test che imposta ERMES_DATABASE_URL nell'ambiente dopo
    l'import non cambia `cfg.DATABASE_URL`, e ottiene SQLite credendo di
    avere Postgres. E' successo per mesi ai test di parita'.
    """
    if database_url:
        esplicito: Backend = create_backend(database_url)
        return esplicito
    if database_path is not None:
        return SqliteBackend(str(database_path))
    backend: Backend = create_backend(cfg.DATABASE_URL)
    return backend


# Common function words must not become the only "evidence" for a RAG answer.
# This compact local-first baseline deliberately keeps a conservative bilingual
# list; a production language analyser can replace it behind this same method.
#
# Le dieci parole in coda sono state aggiunte il 10 settembre 2026 dopo una
# misura. Con un corpus contenente altro testo, alla domanda "un collega lavora
# sempre da casa senza mai venire in sede" il sistema citava un paragrafo
# tecnico qualunque, perche' condivideva "sempre", "senza" e "mai": tre parole
# vuote bastavano a superare la regola di ammissione. Un ampliamento piu' esteso
# (una lista completa di funzionali italiani) e' stato provato e scartato:
# recuperava 0.037 di recall sul corpus grande e ne perdeva 0.125 sulle
# parafrasi di quello pulito.
# Massimo numero di segnaposto per interrogazione. SQLite ne accetta 32766
# nelle build recenti e 999 in quelle storiche: 900 e' sotto entrambi.
_MAX_SQL_VARIABILI = 900

# Candidati lessicali per interrogazione, scelti dal ranking full-text del
# database prima del punteggio in Python. Sui corpus di valutazione (fino a
# 404 passaggi) non viene mai raggiunto, quindi i numeri pubblicati non
# cambiano; su un archivio grande taglia la coda dei candidati irrilevanti.
_MAX_KEYWORD_CANDIDATES = 1000


_QUERY_STOPWORDS = {
    "sempre",
    "mai",
    "senza",
    "succede",
    "anche",
    "ancora",
    "ogni",
    "tutti",
    "deve",
    "essere",
    "a",
    "ad",
    "al",
    "alla",
    "alle",
    "che",
    "chi",
    "come",
    "con",
    "cosa",
    "dei",
    "del",
    "della",
    "delle",
    "di",
    "dove",
    "e",
    "gli",
    "i",
    "il",
    "in",
    "la",
    "le",
    "lo",
    "nei",
    "nelle",
    "per",
    "quali",
    "quando",
    "quale",
    "sono",
    "sul",
    "sulla",
    "the",
    "and",
    "are",
    "before",
    "for",
    "from",
    "how",
    "is",
    "it",
    "of",
    "on",
    "or",
    "to",
    "was",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "your",
    "document",
    "documents",
    "documenti",
    "library",
    "biblioteca",
    "policy",
    "procedure",
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
    def __init__(self, database_path: str | Path | None = None, database_url: str | None = None) -> None:
        self._lock = threading.RLock()
        self._backend = _resolve_backend(database_path, database_url)
        self._is_postgres = self._backend.__class__.__name__ == "PostgresBackend"
        self._initialize()

    @property
    def database_path(self) -> Path:
        if isinstance(self._backend, SqliteBackend):
            return Path(self._backend._path)
        return Path(".")

    def _exec(self, sql: str, params: tuple | dict | None = None) -> list[dict]:
        """Esegui una query SELECT e ritorna tutte le righe."""
        return self._backend.execute(sql, params)

    def _exec_one(self, sql: str, params: tuple | dict | None = None) -> dict | None:
        """Esegui una query SELECT e ritorna la prima riga."""
        return self._backend.execute_one(sql, params)

    def _exec_write(self, sql: str, params: tuple | dict | None = None) -> int:
        """Esegui INSERT/UPDATE/DELETE e ritorna il rowcount."""
        return self._backend.execute_write(sql, params)

    def _exec_returning(self, sql: str, params: tuple | dict | None = None) -> dict | None:
        """Esegui INSERT/UPDATE/DELETE ... RETURNING e ritorna la riga."""
        return self._backend.execute_returning(sql, params)

    @contextmanager
    def _connection(self):
        """Context manager legacy: delega al backend transaction().

        Mantiene la signature storica per i pochi chiamatori che fanno
        `with self._connection() as connection: connection.execute(...)`.
        SQLite: restituisce la connessione cruda (sqlite3.Row, accesso per nome).
        Postgres: restituisce un adapter dict-based.
        """
        with self._backend.transaction() as connection:
            yield connection

    def _initialize(self) -> None:
        if self._is_postgres:
            self._initialize_postgres()
        else:
            self._initialize_sqlite()

    def _initialize_postgres(self) -> None:
        """Inizializza lo schema PostgreSQL usando il DDL di postgres_backend."""
        from core.postgres_backend import POSTGRES_SCHEMA

        self._backend.execute_script(POSTGRES_SCHEMA)

    def _initialize_sqlite(self) -> None:
        """Inizializza lo schema SQLite (comportamento storico)."""
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS search_cache_generations (
                    library_id TEXT PRIMARY KEY,
                    generation INTEGER NOT NULL
                );

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
                    role TEXT NOT NULL CHECK(role IN ('viewer', 'reviewer', 'editor', 'manager')),
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

                CREATE TABLE IF NOT EXISTS library_notes (
                    id TEXT PRIMARY KEY,
                    library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
                    owner TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS library_notes_by_owner
                    ON library_notes(library_id, owner);

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
                    completed_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    total_chunks INTEGER NOT NULL DEFAULT 0,
                    processed_chunks INTEGER NOT NULL DEFAULT 0,
                    dead_letter_reason TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS jobs_by_library
                    ON ingestion_jobs(library_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS import_sources (
                    id TEXT PRIMARY KEY,
                    library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    created_by TEXT NOT NULL DEFAULT '',
                    last_scan_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (library_id, path)
                );

                CREATE TABLE IF NOT EXISTS chat_integrations (
                    id TEXT PRIMARY KEY,
                    library_id TEXT NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
                    platform TEXT NOT NULL,
                    external_channel_id TEXT NOT NULL,
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE (platform, external_channel_id)
                );
                CREATE INDEX IF NOT EXISTS chat_integrations_by_library
                    ON chat_integrations(library_id);

                CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    library_id UNINDEXED,
                    filename,
                    text,
                    source_locator UNINDEXED,
                    tokenize = 'unicode61 remove_diacritics 2'
                );

                CREATE TRIGGER IF NOT EXISTS trg_document_chunks_fts_ai AFTER INSERT ON document_chunks
                BEGIN
                    INSERT INTO document_chunks_fts (chunk_id, document_id, library_id, filename, text, source_locator)
                    SELECT new.id, new.document_id, d.library_id, d.filename, new.text, new.source_locator
                    FROM documents d WHERE d.id = new.document_id;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_document_chunks_fts_ad AFTER DELETE ON document_chunks
                BEGIN
                    DELETE FROM document_chunks_fts WHERE chunk_id = old.id;
                END;

                CREATE TRIGGER IF NOT EXISTS trg_document_chunks_fts_au AFTER UPDATE ON document_chunks
                BEGIN
                    DELETE FROM document_chunks_fts WHERE chunk_id = old.id;
                    INSERT INTO document_chunks_fts (chunk_id, document_id, library_id, filename, text, source_locator)
                    SELECT new.id, new.document_id, d.library_id, d.filename, new.text, new.source_locator
                    FROM documents d WHERE d.id = new.document_id;
                END;
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
            job_columns = {row[1] for row in connection.execute("PRAGMA table_info(ingestion_jobs)")}
            if "attempts" not in job_columns:
                connection.execute("ALTER TABLE ingestion_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
            if "total_chunks" not in job_columns:
                connection.execute("ALTER TABLE ingestion_jobs ADD COLUMN total_chunks INTEGER NOT NULL DEFAULT 0")
            if "processed_chunks" not in job_columns:
                connection.execute("ALTER TABLE ingestion_jobs ADD COLUMN processed_chunks INTEGER NOT NULL DEFAULT 0")
            if "dead_letter_reason" not in job_columns:
                connection.execute("ALTER TABLE ingestion_jobs ADD COLUMN dead_letter_reason TEXT NOT NULL DEFAULT ''")
            library_columns = {row[1] for row in connection.execute("PRAGMA table_info(libraries)")}
            if "owner_id" not in library_columns:
                connection.execute("ALTER TABLE libraries ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'system'")
            if "assistant_mode" not in library_columns:
                connection.execute(
                    "ALTER TABLE libraries ADD COLUMN assistant_mode TEXT NOT NULL DEFAULT 'evidence_only'"
                )
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
            # Backfill FTS index if table is empty while chunks exist
            fts_count = connection.execute("SELECT COUNT(*) FROM document_chunks_fts").fetchone()[0]
            chunks_count = connection.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
            if fts_count == 0 and chunks_count > 0:
                connection.execute(
                    """
                    INSERT INTO document_chunks_fts (chunk_id, document_id, library_id, filename, text, source_locator)
                    SELECT c.id, c.document_id, d.library_id, d.filename, c.text, c.source_locator
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    """
                )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _row(row: sqlite3.Row | dict | Any) -> dict:
        return dict(row)

    @staticmethod
    def _search_token(token: str) -> str:
        """Small deterministic Italian-friendly normalization for MVP search.

        It deliberately is not a linguistic model; trimming a terminal ``a``/
        ``e`` avoids missing obvious feminine singular/plural forms such as
        ``richiesta`` / ``richieste`` while semantic retrieval remains an
        optional later ranking signal.

        Found in review: trimming *any* trailing vowel (the original ``in
        "aeiou"`` check) collapsed unrelated words that merely happen to end
        in different vowels onto the same stem — ``lavora`` (verb, "works")
        and ``lavoro`` (noun, "job") both became ``lavor``, causing a
        false-positive match on an abstention query that should have found
        nothing. Restricting the trim to ``a``/``e`` keeps the one pairing
        this heuristic is actually meant for (feminine singular/plural) while
        no longer touching ``-o``/``-i``/``-u`` endings, which is where the
        verb/noun collisions come from.
        """
        normalized = token.lower()
        return normalized[:-1] if len(normalized) > 4 and normalized[-1] in "ae" else normalized

    @staticmethod
    def _can_access(library: dict, actor: dict | None, write: bool = False, member_role: str | None = None) -> bool:
        if actor is None:
            return True
        if actor.get("role") == "admin":
            return True
        if library.get("owner_id") == actor.get("username"):
            return True
        if member_role in {"editor", "manager"}:
            return True
        if member_role in {"viewer", "reviewer"} and not write:
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
    def _effective_member_role(
        direct_role: str | None, library_id: str, actor: dict | None, groups: list[str] | None = None
    ) -> str | None:
        """Ruolo efficace = max(membership diretta, gruppi mappati).

        I gruppi vengono dal token OIDC e dal provisioning SCIM
        (core/scim_groups.py::effective_groups). Non possono mai degradare una
        membership esplicita: se il proprietario ha dato editor a un utente,
        resta editor anche se il suo gruppo mappa solo viewer. Il valore admin
        non deriva mai dai gruppi (solo dai ruoli del token o da account
        espliciti). `groups` si passa gia' calcolato quando si valutano molte
        biblioteche per lo stesso utente, per non rileggerli a ogni biblioteca.
        """
        if actor is None:
            return direct_role
        if groups is None:
            from core.scim_groups import effective_groups

            groups = effective_groups(actor)
        if not groups:
            return direct_role
        from core.governance import resolve_oidc_group_role

        group_role = resolve_oidc_group_role(groups, library_id)
        if group_role is None:
            return direct_role
        hierarchy = {"manager": 4, "editor": 3, "reviewer": 2, "viewer": 1}
        d_rank = hierarchy.get(direct_role or "", 0)
        g_rank = hierarchy.get(group_role or "", 0)
        return direct_role if d_rank >= g_rank else group_role

    @staticmethod
    def _can_manage_members(library: dict, actor: dict | None, member_role: str | None = None) -> bool:
        if not actor:
            return False
        if actor.get("role") == "admin" or library.get("owner_id") == actor.get("username"):
            return True
        effective = member_role or library.get("access_role")
        return effective == "manager"

    @classmethod
    def _access_role(cls, library: dict, actor: dict | None, member_role: str | None = None) -> str:
        """Return the effective library role without trusting the client UI."""
        if actor is None:
            return "system"
        if actor.get("role") == "admin":
            return "admin"
        if library.get("owner_id") == actor.get("username"):
            return "owner"
        if member_role in {"viewer", "reviewer", "editor", "manager"}:
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
        # Propagazione ACL: le biblioteche raggiungibili SOLO via gruppi (token
        # OIDC o provisioning SCIM) appaiono nell'elenco anche senza
        # membership diretta.
        group_roles: dict[str, str] = {}
        groups: list[str] = []
        if actor and actor.get("role") != "admin":
            from core.governance import oidc_group_roles_for_user
            from core.scim_groups import effective_groups

            groups = effective_groups(actor)
            group_roles = oidc_group_roles_for_user(groups)
        visible: list[dict] = []
        for row in rows:
            library = self._row(row)
            member_role = memberships.get(library["id"])
            effective_role = self._effective_member_role(member_role, library["id"], actor, groups=groups)
            if group_roles.get(library["id"]) and effective_role is None:
                effective_role = group_roles[library["id"]]
            if self._can_access(library, actor, member_role=member_role) or (
                effective_role is not None and library["id"] in group_roles
            ):
                library["access_role"] = self._access_role(library, actor, effective_role)
                visible.append(library)
        return visible

    def create_library(
        self, name: str, description: str = "", visibility: str = "private", owner_id: str = "system"
    ) -> dict:
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
                SELECT libraries.*, COUNT(documents.id) AS document_count,
                       COALESCE(
                           (SELECT g.generation FROM search_cache_generations g WHERE g.library_id = libraries.id), 0
                       ) AS cache_generation
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
        member_role = (
            self._membership_role(library_id, actor["username"]) if actor and actor.get("role") != "admin" else None
        )
        member_role = self._effective_member_role(member_role, library_id, actor)
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
        return [
            {
                "username": library["owner_id"],
                "role": "owner",
                "created_at": library["created_at"],
                "updated_at": library["updated_at"],
            },
            *[self._row(row) for row in rows],
        ]

    def set_library_member(self, library_id: str, username: str, role: str) -> dict:
        self.get_library(library_id)
        normalized_username = username.strip()
        if not normalized_username:
            raise ValueError("Utente collaboratore obbligatorio")
        if role not in {"viewer", "reviewer", "editor", "manager"}:
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
        return self._can_manage_members(library, actor, library.get("access_role"))


    # ============================================================
    # Note personali (come le note di NotebookLM)
    # ============================================================
    # Private: le vede solo chi le ha scritte, e solo finche' puo' ancora
    # aprire la biblioteca. Le fonti sono salvate con la nota, cosi' una nota
    # presa da una risposta resta verificabile anche dopo che la risposta non
    # e' piu' a schermo.

    _NOTE_MAX_TITLE = 200
    _NOTE_MAX_BODY = 20_000
    _NOTE_MAX_SOURCES = 20

    def _clean_note_sources(self, sources: list[dict] | None) -> list[dict]:
        keys = ("document_id", "filename", "version", "locator", "excerpt")
        cleaned: list[dict] = []
        for source in (sources or [])[: self._NOTE_MAX_SOURCES]:
            if isinstance(source, dict):
                item = {k: source.get(k) for k in keys if source.get(k) is not None}
                if "excerpt" in item:
                    item["excerpt"] = str(item["excerpt"])[:2000]
                cleaned.append(item)
        return cleaned

    def _note_row(self, row) -> dict:
        note = self._row(row)
        note["sources"] = json.loads(note.pop("sources_json") or "[]")
        return note

    def list_notes(self, library_id: str, actor: dict) -> list[dict]:
        self.get_library(library_id, actor)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM library_notes WHERE library_id = ? AND owner = ? ORDER BY updated_at DESC",
                (library_id, actor["username"]),
            ).fetchall()
        return [self._note_row(r) for r in rows]

    def create_note(
        self, library_id: str, actor: dict, title: str, body: str, sources: list[dict] | None = None
    ) -> dict:
        self.get_library(library_id, actor)
        title, body = title.strip()[: self._NOTE_MAX_TITLE], body.strip()[: self._NOTE_MAX_BODY]
        if not title and not body:
            raise ValueError("Nota vuota")
        now = self._timestamp()
        note_id = str(uuid.uuid4())
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO library_notes (id, library_id, owner, title, body, sources_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    library_id,
                    actor["username"],
                    title or body[:60],
                    body,
                    json.dumps(self._clean_note_sources(sources), ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_note(library_id, note_id, actor)

    def get_note(self, library_id: str, note_id: str, actor: dict) -> dict:
        self.get_library(library_id, actor)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM library_notes WHERE id = ? AND library_id = ? AND owner = ?",
                (note_id, library_id, actor["username"]),
            ).fetchone()
        # Stessa risposta per "non esiste" e "e' di un altro": non si rivela
        # che una nota altrui esiste.
        if row is None:
            raise LibraryNotFoundError(note_id)
        return self._note_row(row)

    def update_note(self, library_id: str, note_id: str, actor: dict, title: str | None, body: str | None) -> dict:
        current = self.get_note(library_id, note_id, actor)
        new_title = (current["title"] if title is None else title.strip())[: self._NOTE_MAX_TITLE]
        new_body = (current["body"] if body is None else body.strip())[: self._NOTE_MAX_BODY]
        if not new_title and not new_body:
            raise ValueError("Nota vuota")
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE library_notes SET title = ?, body = ?, updated_at = ? WHERE id = ? AND owner = ?",
                (new_title, new_body, self._timestamp(), note_id, actor["username"]),
            )
        return self.get_note(library_id, note_id, actor)

    def delete_note(self, library_id: str, note_id: str, actor: dict) -> None:
        self.get_note(library_id, note_id, actor)
        with self._lock, self._connection() as connection:
            connection.execute(
                "DELETE FROM library_notes WHERE id = ? AND owner = ?", (note_id, actor["username"])
            )

    # ============================================================
    # Document-level ACL
    # ============================================================
    # Un documento senza righe in document_acls segue le regole di accesso
    # della libreria. Un documento CON righe e' visibile solo ad admin, al
    # proprietario della libreria e agli utenti elencati: la lista e' una
    # allow-list esplicita, non un'aggiunta ai permessi base.

    @staticmethod
    def _bump_cache_generation(connection, library_id: str) -> None:
        """Da chiamare dentro la transazione che modifica documenti o permessi.

        Invalida la cache di ricerca su tutte le repliche, non solo su quella
        che serve la richiesta: vedi core/search_cache.py. Nella stessa
        transazione, quindi senza connessioni ne' commit in piu'.
        """
        connection.execute(
            """
            INSERT INTO search_cache_generations (library_id, generation) VALUES (?, 1)
            ON CONFLICT (library_id) DO UPDATE SET generation = search_cache_generations.generation + 1
            """,
            (library_id,),
        )

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
            self._bump_cache_generation(connection, library_id)
        # La cache si invalida da sola solo quando cambia il numero di
        # documenti, e una restrizione non lo cambia: senza questa riga chi
        # era appena stato escluso riceveva gli estratti riservati dalla
        # propria cache fino alla scadenza del TTL.
        get_search_cache().invalidate(library_id)
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

    def add_import_source(self, library_id: str, path: str, created_by: str = "") -> dict:
        """Register one watched folder. The path must be unique per library."""
        self.get_library(library_id)
        now = self._timestamp()
        normalized = os.path.normpath(path)
        with self._lock, self._connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO import_sources (id, library_id, path, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), library_id, normalized, created_by, now),
                )
            except INTEGRITY_ERRORS as error:
                raise ValueError("Sorgente già registrata per questa biblioteca") from error
        return self.get_import_source(library_id, normalized)

    def get_import_source(self, library_id: str, path: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM import_sources WHERE library_id = ? AND path = ?",
                (library_id, path),
            ).fetchone()
        if row is None:
            raise LibraryNotFoundError(path)
        return self._row(row)

    def get_import_source_by_id(self, library_id: str, source_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM import_sources WHERE library_id = ? AND id = ?",
                (library_id, source_id),
            ).fetchone()
        if row is None:
            raise LibraryNotFoundError(source_id)
        return self._row(row)

    def list_import_sources(self, library_id: str, actor: dict | None = None) -> list[dict]:
        self.get_library(library_id, actor)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM import_sources WHERE library_id = ? ORDER BY created_at",
                (library_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def list_all_import_sources(self) -> list[dict]:
        """List every registered import source across all libraries for the sync watcher."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT import_sources.*, libraries.name AS library_name
                FROM import_sources
                JOIN libraries ON libraries.id = import_sources.library_id
                ORDER BY import_sources.created_at
                """
            ).fetchall()
        return [self._row(row) for row in rows]

    def remove_import_source(self, library_id: str, source_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM import_sources WHERE library_id = ? AND id = ?",
                (library_id, source_id),
            )
            return bool(cursor.rowcount and cursor.rowcount > 0)

    def touch_import_source(self, library_id: str, source_id: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE import_sources SET last_scan_at = ? WHERE library_id = ? AND id = ?",
                (self._timestamp(), library_id, source_id),
            )

    def add_chat_integration(
        self, library_id: str, platform: str, external_channel_id: str, created_by: str = ""
    ) -> dict:
        """Bind one external chat channel to this library. A channel can point to only one library."""
        self.get_library(library_id)
        now = self._timestamp()
        integration_id = str(uuid.uuid4())
        with self._lock, self._connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO chat_integrations (id, library_id, platform, external_channel_id, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (integration_id, library_id, platform, external_channel_id, created_by, now),
                )
            except INTEGRITY_ERRORS as error:
                raise ValueError("Questo canale è già collegato a una biblioteca") from error
        return self.get_chat_integration_by_id(library_id, integration_id)

    def get_chat_integration_by_id(self, library_id: str, integration_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM chat_integrations WHERE library_id = ? AND id = ?",
                (library_id, integration_id),
            ).fetchone()
        if row is None:
            raise LibraryNotFoundError(integration_id)
        return self._row(row)

    def get_chat_integration_by_channel(self, platform: str, external_channel_id: str) -> dict | None:
        """Routing lookup used by the inbound webhook: no ownership check, the
        destination library was already decided when the channel was registered."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM chat_integrations WHERE platform = ? AND external_channel_id = ?",
                (platform, external_channel_id),
            ).fetchone()
        return self._row(row) if row is not None else None

    def list_chat_integrations(self, library_id: str, actor: dict | None = None) -> list[dict]:
        self.get_library(library_id, actor)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM chat_integrations WHERE library_id = ? ORDER BY created_at",
                (library_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def remove_chat_integration(self, library_id: str, integration_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM chat_integrations WHERE library_id = ? AND id = ?",
                (library_id, integration_id),
            )
            return bool(cursor.rowcount and cursor.rowcount > 0)

    def existing_content_hashes(self, library_id: str) -> set[str]:
        """Content hashes of every document in the library, for import dedupe."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT content_hash FROM documents WHERE library_id = ?",
                (library_id,),
            ).fetchall()
        return {row["content_hash"] for row in rows}

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
            self._bump_cache_generation(connection, library_id)
        # Il conteggio dei documenti non cambia, quindi la cache non se ne
        # accorgerebbe: i chunk si', e sono cio' che viene citato.
        get_search_cache().invalidate(library_id)
        return self.get_document(library_id, document_id)

    def _keyword_candidates(self, connection, library_id: str, query: str, hidden: set[str]) -> set[str]:
        """Trova i chunk_id candidati via keyword search (FTS5 su SQLite, tsvector su Postgres)."""
        tokens = [
            self._search_token(token)
            for token in re.findall(r"[\wÀ-ÿ]{3,}", query.lower())
            if token not in _QUERY_STOPWORDS
        ]
        if not tokens:
            for token in re.findall(r"[\wÀ-ÿ]{2,}", query.lower()):
                if token not in _QUERY_STOPWORDS:
                    clean = re.sub(r"[^\wÀ-ÿ]", "", token)
                    if clean:
                        tokens.append(clean)
        if not tokens:
            return set()

        # Il ranking finale e' calcolato in Python su ogni candidato: con una
        # parola presente quasi ovunque erano decine di migliaia di righe, e
        # 3,2 s a 50.000 passaggi (evaluation/archive_scale.py). Il database
        # ordina gia' per rilevanza full-text, quindi si prendono solo i primi,
        # piu' quanti potrebbero essere scartati come nascosti.
        tetto = _MAX_KEYWORD_CANDIDATES + len(hidden)

        if self._is_postgres:
            # Stessa semantica del ramo SQLite: la frase intera OPPURE uno
            # qualunque dei token (prefisso). Fino al 18 settembre 2026 la
            # frase era scritta con le virgolette di FTS5 — sintassi che
            # tsquery non ha ("syntax error in tsquery", primo run reale su
            # Postgres) — e i token erano in AND: con l'espansione dei
            # sinonimi (sei token per "sicurezza") non trovava mai niente.
            # `phraseto_tsquery` gestisce la frase da solo; i token sono
            # \w puri, quindi `|` fra prefissi e' una tsquery valida.
            clean_phrase = re.sub(r"[^\wÀ-ÿ\s]", " ", query).strip()
            clean_tokens = [re.sub(r"[^\wÀ-ÿ]", "", t) for t in tokens]
            token_query = " | ".join(f"{t}:*" for t in clean_tokens if t)
            rows = connection.execute(
                """
                SELECT c.id AS chunk_id, c.document_id AS document_id FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.library_id = ?
                  AND (c.search_tsv @@ to_tsquery('simple', ?)
                       OR (? <> '' AND c.search_tsv @@ phraseto_tsquery('simple', ?)))
                ORDER BY ts_rank(c.search_tsv, to_tsquery('simple', ?)) DESC
                LIMIT ?
                """,
                (
                    library_id,
                    token_query,
                    clean_phrase if len(clean_phrase.split()) > 1 else "",
                    clean_phrase,
                    token_query,
                    tetto,
                ),
            ).fetchall()
        else:
            # SQLite: FTS5
            fts_query_parts = []
            clean_phrase = re.sub(r"[^\wÀ-ÿ\s]", " ", query).strip()
            phrase_words = clean_phrase.split()
            if len(phrase_words) > 1:
                fts_query_parts.append('"' + " ".join(phrase_words) + '"')
            for token in tokens:
                clean_token = re.sub(r"[^\wÀ-ÿ]", "", token)
                if len(clean_token) >= 3:
                    fts_query_parts.append(f"{clean_token}*")
            fts_match_query = " OR ".join(fts_query_parts)
            if not fts_match_query:
                return set()
            rows = connection.execute(
                "SELECT chunk_id, document_id FROM document_chunks_fts "
                "WHERE document_chunks_fts MATCH ? AND library_id = ? "
                "ORDER BY bm25(document_chunks_fts) LIMIT ?",
                (fts_match_query, library_id, tetto),
            ).fetchall()

        # Il confronto era fra chunk_id e l'insieme `hidden`, che contiene id
        # di documento: non filtrava mai niente. Innocuo finche' il filtro vero
        # restava a valle, sbagliato da leggere e da ereditare.
        return {row["chunk_id"] for row in rows if row["document_id"] not in hidden}

    def search_documents(self, library_id: str, query: str, limit: int = 20) -> list[dict]:
        """Return only the result list for callers that do not need retrieval metadata."""
        results, _ = self.search_with_profile(library_id, query, limit)
        return results

    def search_with_profile(
        self, library_id: str, query: str, limit: int = 20, actor: dict | None = None
    ) -> tuple[list[dict], dict]:
        """Retrieve chunks with a truthful local retrieval profile."""
        library = self.get_library(library_id, actor)
        normalized = query.strip()
        if not normalized:
            return [], {"mode": "keyword", "semantic_indexed_chunks": 0, "semantic_used": False}

        # Check semantic cache (invalidated when doc_count changes).
        # Lo scope = username: con ACL attive utenti diversi devono vedere
        # risultati diversi, quindi la cache è partizionata per utente per
        # evitare leak/falsi negativi tra chi ha permessi differenti.
        cache = get_search_cache()
        doc_count = library.get("document_count", 0)
        scope = actor.get("username", "") if actor else ""
        # Letta da get_library, quindi prima della ricerca: vedi
        # SemanticSearchCache.put().
        generation = library.get("cache_generation", 0)
        cached = cache.get(library_id, normalized, doc_count, scope, generation=generation)
        if cached is not None:
            return cached

        with self._connection() as connection:
            hidden = self._hidden_document_ids(connection, library, actor)

            if self._is_postgres:
                emb_filter = "(c.embedding_json IS NOT NULL AND c.embedding_json::text <> 'null')"
            else:
                emb_filter = "c.embedding_json <> ''"

            row = connection.execute(
                f"SELECT COUNT(c.id) AS count FROM document_chunks c JOIN documents d ON d.id = c.document_id WHERE d.library_id = ? AND {emb_filter}",  # nosec B608
                (library_id,),
            ).fetchone()
            indexed_count = row.get("count", 0) if isinstance(row, dict) else row[0]

            query_embeddings = embed_texts([normalized]) if indexed_count else []
            query_embedding = query_embeddings[0] if query_embeddings else []
            semantic_used = bool(query_embedding and indexed_count)

            tokens = [
                self._search_token(t)
                for t in re.findall(r"[\wÀ-ÿ]{3,}", normalized.lower())
                if t not in _QUERY_STOPWORDS
            ]
            candidate_chunk_ids = self._keyword_candidates(connection, library_id, normalized, hidden)

            for eq in expand_query(normalized)[1:]:
                candidate_chunk_ids.update(self._keyword_candidates(connection, library_id, eq, hidden))

            if semantic_used:
                emb_rows = connection.execute(
                    f"SELECT c.id FROM document_chunks c JOIN documents d ON d.id = c.document_id WHERE d.library_id = ? AND {emb_filter}",  # nosec B608
                    (library_id,),
                ).fetchall()
                for r in emb_rows:
                    cid = r.get("id") if isinstance(r, dict) else r[0]
                    if cid:
                        candidate_chunk_ids.add(str(cid))

            if not candidate_chunk_ids and not semantic_used:
                return [], {"mode": "keyword", "semantic_indexed_chunks": indexed_count, "semantic_used": False}

            if candidate_chunk_ids:
                # A blocchi, e non in un unico IN (...): la query usava un
                # segnaposto per ogni candidato, e SQLite ne accetta al massimo
                # 32766. Su un archivio grande una parola comune supera quel
                # numero e la ricerca NON rallenta, fallisce con
                # "too many SQL variables". Misurato: 50.000 passaggi bastano
                # (evaluation/archive_scale.py).
                #
                # 900 e' sotto il limite storico di 999 delle build piu'
                # vecchie, quindi la correzione vale anche li'.
                elenco = list(candidate_chunk_ids)
                rows = []
                for primo in range(0, len(elenco), _MAX_SQL_VARIABILI):
                    blocco = elenco[primo : primo + _MAX_SQL_VARIABILI]
                    placeholders = ",".join("?" for _ in blocco)
                    rows.extend(
                        connection.execute(
                            f"SELECT documents.id AS document_id, documents.filename, documents.version, documents.content_hash, document_chunks.id AS chunk_id, document_chunks.ordinal, document_chunks.text AS excerpt, document_chunks.source_locator, document_chunks.embedding_json FROM document_chunks JOIN documents ON documents.id = document_chunks.document_id WHERE document_chunks.id IN ({placeholders}) AND documents.library_id = ? ORDER BY documents.created_at DESC, document_chunks.ordinal ASC",  # nosec B608
                            (*blocco, library_id),
                        ).fetchall()
                    )
            else:
                rows = []

        def _get(row, key):
            if isinstance(row, dict):
                return row.get(key)
            keys = [
                "document_id",
                "filename",
                "version",
                "content_hash",
                "chunk_id",
                "ordinal",
                "excerpt",
                "source_locator",
                "embedding_json",
            ]
            return row[keys.index(key)]

        rows = [r for r in rows if _get(r, "document_id") not in hidden]

        # Pesatura per rarita' del termine, calcolata sui candidati gia'
        # caricati: nessuno schema nuovo, nessuna cache da invalidare.
        #
        # Prima ogni termine valeva 10 punti, raro o comunissimo che fosse. Con
        # sedici passaggi non si notava; con testo vero attorno, l'astensione
        # passava da 1.000 a 0.333 (evaluation/scale_check.py).
        #
        # NOTA su una spiegazione sbagliata, scritta qui in un primo momento e
        # corretta il 10 settembre 2026: si diceva che la colpa fosse di
        # collisioni dello stemmer, "casa" contro "casi". E' falso — lo stemmer
        # taglia solo a/e finali oltre i quattro caratteri, quindi non tocca
        # nessuna delle due. Verificando quali termini producevano davvero la
        # corrispondenza sono risultati "sempre", "senza" e "mai": parole vuote
        # sopravvissute a _QUERY_STOPWORDS, piu' una polisemia reale ("codice"
        # etico contro "codice" sorgente).
        #
        # Un termine presente in quasi tutti i candidati non distingue niente e
        # ora pesa quasi zero; uno presente in pochi pesa quasi uno.
        preparati = []
        frequenza_documentale: dict[str, int] = {}
        termini_distinti = set(tokens)
        for row in rows:
            haystack = f"{_get(row, 'filename')} {_get(row, 'excerpt')}".lower()
            haystack_tokens = {self._search_token(t) for t in re.findall(r"[\wÀ-ÿ]{3,}", haystack)}
            preparati.append((row, haystack, haystack_tokens))
            for termine in termini_distinti:
                if termine in haystack_tokens:
                    frequenza_documentale[termine] = frequenza_documentale.get(termine, 0) + 1

        candidati = len(preparati)
        normalizzatore = math.log(1 + candidati) if candidati > 1 else 1.0

        def _peso(termine: str) -> float:
            df = frequenza_documentale.get(termine, 0)
            if df <= 0:
                return 0.0
            if candidati <= 1:
                return 1.0
            return math.log(1 + candidati / df) / normalizzatore

        ranked = []
        for row, haystack, haystack_tokens in preparati:
            filename, excerpt = _get(row, "filename"), _get(row, "excerpt")
            document_id = _get(row, "document_id")
            version = _get(row, "version")
            content_hash = _get(row, "content_hash")
            chunk_id = _get(row, "chunk_id")
            source_locator = _get(row, "source_locator")
            embedding_json = _get(row, "embedding_json")
            ordinal = _get(row, "ordinal")
            phrase_score = 100 if normalized.lower() in haystack else 0
            token_score = 10 * sum(_peso(t) for t in tokens if t in haystack_tokens)
            semantic_score = 0.0
            if query_embedding and embedding_json:
                try:
                    emb = json.loads(embedding_json) if isinstance(embedding_json, str) else embedding_json
                    semantic_score = max(0.0, cosine_similarity(query_embedding, emb))
                except (TypeError, ValueError):
                    semantic_score = 0.0
            if phrase_score or token_score or semantic_score >= min_semantic_score():
                ranked.append(
                    (
                        phrase_score + token_score + (semantic_score * 40),
                        {
                            "document_id": document_id,
                            "filename": filename,
                            "version": version,
                            "content_hash": content_hash,
                            "chunk_id": chunk_id,
                            "ordinal": ordinal,
                            "excerpt": excerpt,
                            "source_locator": source_locator,
                        },
                    )
                )
        ranked.sort(key=lambda item: (-item[0], item[1]["ordinal"]))
        target_limit = max(1, min(limit, 50))
        candidate_pool_size = (
            max(target_limit * 3, 20)
            if getattr(cfg, "RERANKER_ENABLED", True)
            else target_limit
        )
        results = [
            {
                **d,
                "relevance_score": round(s, 4),
                "citation": {
                    "document_id": d["document_id"],
                    "filename": d["filename"],
                    "version": d["version"],
                    "content_hash": f"sha256:{d['content_hash']}",
                    "chunk_id": d["chunk_id"],
                    "locator": d["source_locator"] or f"Passaggio {d['ordinal'] + 1}",
                },
            }
            for s, d in ranked[:candidate_pool_size]
        ]
        if getattr(cfg, "RERANKER_ENABLED", True) and results:
            from core.reranker import rerank_candidates

            results = rerank_candidates(query=normalized, candidates=results, limit=target_limit)
        else:
            results = results[:target_limit]
        profile = {
            "mode": "hybrid_local" if semantic_used else "keyword",
            "semantic_indexed_chunks": indexed_count,
            "semantic_used": semantic_used,
        }
        # Store in semantic cache (per-user scope, come sopra)
        cache.put(library_id, normalized, doc_count, results, profile, scope, generation=generation)
        return results, profile

    def store_chunk_embeddings(
        self,
        library_id: str,
        document_id: str,
        embeddings: list[list[float]],
        model_id: str,
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
                [
                    (json.dumps(embedding, separators=(",", ":")), model_id, row["id"])
                    for row, embedding in zip(rows, embeddings)
                ],
            )
            self._bump_cache_generation(connection, library_id)
        # Una ricerca memorizzata prima degli embedding era lessicale; con
        # la semantica accesa deve essere rifatta.
        get_search_cache().invalidate(library_id)
        return len(embeddings)

    def delete_document(self, library_id: str, document_id: str) -> list[str]:
        """Remove one document and every derived row (chunks, versions, ACL, jobs).

        Returns the storage paths (relative to the storage root) of the original
        and of every version, so the caller can unlink the files after commit:
        the store owns no storage root, file removal stays with the API layer.
        """
        self.get_library(library_id)
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT storage_path FROM documents WHERE id = ? AND library_id = ?",
                (document_id, library_id),
            ).fetchone()
            if row is None:
                raise LibraryNotFoundError(document_id)
            # document_versions condivide spesso lo storage_path del documento
            # (versione 1): dedup preservando l'ordine, il chiamante non deve
            # fare unlink due volte dello stesso file.
            paths = list(
                dict.fromkeys(
                    [row["storage_path"]]
                    + [
                        v["storage_path"]
                        for v in connection.execute(
                            "SELECT storage_path FROM document_versions WHERE document_id = ?",
                            (document_id,),
                        ).fetchall()
                    ]
                )
            )
            connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_versions WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_acls WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM ingestion_jobs WHERE document_id = ?", (document_id,))
            connection.execute(
                "DELETE FROM documents WHERE id = ? AND library_id = ?",
                (document_id, library_id),
            )
            self._bump_cache_generation(connection, library_id)
        # Invalidate search cache (document count changed)
        get_search_cache().invalidate(library_id)
        return paths

    # ------------------------------------------------------------------
    # Dati riferibili a una persona (GDPR: accesso e cancellazione)
    # ------------------------------------------------------------------

    def user_footprint(self, username: str) -> dict:
        """Tutto cio' che in questo archivio fa riferimento a un nome utente.

        Serve al diritto di accesso (art. 15) e a decidere cosa cancellare o
        anonimizzare (art. 17). I documenti non registrano chi li ha caricati,
        quindi non compaiono: non sono dati personali di chi li ha caricati.
        Usa i wrapper del backend, cosi' vale anche su PostgreSQL.
        """
        return {
            "owned_libraries": self._exec(
                "SELECT id, name, visibility, created_at FROM libraries WHERE owner_id = ? ORDER BY created_at",
                (username,),
            ),
            "memberships": self._exec(
                "SELECT library_id, role, created_at FROM library_members WHERE username = ? ORDER BY created_at",
                (username,),
            ),
            "document_acls": self._exec(
                "SELECT document_id, created_at FROM document_acls WHERE username = ? ORDER BY created_at",
                (username,),
            ),
            "chat_integrations_created": self._exec(
                "SELECT id, library_id, platform, created_at FROM chat_integrations WHERE created_by = ?",
                (username,),
            ),
            "import_sources_created": self._exec(
                "SELECT id, library_id, path, created_at FROM import_sources WHERE created_by = ?",
                (username,),
            ),
        }

    def erase_user(self, username: str, reassign_to: str) -> dict:
        """Cancella o anonimizza ogni riferimento a `username`.

        Cancellare le biblioteche di cui la persona e' proprietaria non e'
        cancellare i suoi dati: sono documenti dell'organizzazione, che
        continuano a servire ad altri. La proprieta' passa a `reassign_to`
        (l'amministratore che esegue l'operazione), e lo stesso vale per le
        integrazioni e le sorgenti che aveva registrato. Appartenenze e ACL
        sono invece diritti personali, e vengono rimossi.
        """
        with self._lock:
            return {
                "libraries_reassigned": self._exec_write(
                    "UPDATE libraries SET owner_id = ? WHERE owner_id = ?", (reassign_to, username)
                ),
                "memberships_removed": self._exec_write("DELETE FROM library_members WHERE username = ?", (username,)),
                "document_acls_removed": self._exec_write("DELETE FROM document_acls WHERE username = ?", (username,)),
                "chat_integrations_reassigned": self._exec_write(
                    "UPDATE chat_integrations SET created_by = ? WHERE created_by = ?", (reassign_to, username)
                ),
                "import_sources_reassigned": self._exec_write(
                    "UPDATE import_sources SET created_by = ? WHERE created_by = ?", (reassign_to, username)
                ),
            }

    def delete_library(self, library_id: str) -> list[str]:
        """Remove a library with members, sources and every document.

        Same contract as delete_document: DB rows go in one transaction here,
        storage files are returned for the caller to unlink.
        """
        self.get_library(library_id)
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """
                SELECT d.storage_path AS storage_path FROM documents d
                WHERE d.library_id = ?
                UNION ALL
                SELECT v.storage_path FROM document_versions v
                JOIN documents d ON d.id = v.document_id
                WHERE d.library_id = ?
                """,
                (library_id, library_id),
            ).fetchall()
            # Dedup: le versioni condividono spesso lo storage_path del documento.
            paths = list(dict.fromkeys(r["storage_path"] for r in rows))
            connection.execute(
                """
                DELETE FROM document_chunks WHERE document_id IN
                    (SELECT id FROM documents WHERE library_id = ?)
                """,
                (library_id,),
            )
            connection.execute(
                """
                DELETE FROM document_versions WHERE document_id IN
                    (SELECT id FROM documents WHERE library_id = ?)
                """,
                (library_id,),
            )
            connection.execute(
                """
                DELETE FROM document_acls WHERE document_id IN
                    (SELECT id FROM documents WHERE library_id = ?)
                """,
                (library_id,),
            )
            connection.execute("DELETE FROM ingestion_jobs WHERE library_id = ?", (library_id,))
            connection.execute("DELETE FROM import_sources WHERE library_id = ?", (library_id,))
            connection.execute("DELETE FROM chat_integrations WHERE library_id = ?", (library_id,))
            connection.execute("DELETE FROM library_members WHERE library_id = ?", (library_id,))
            connection.execute("DELETE FROM documents WHERE library_id = ?", (library_id,))
            connection.execute("DELETE FROM library_notes WHERE library_id = ?", (library_id,))
            connection.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
            connection.execute("DELETE FROM search_cache_generations WHERE library_id = ?", (library_id,))
        # Invalidate search cache (library deleted)
        get_search_cache().invalidate(library_id)
        return paths

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
                (
                    document["id"],
                    document["version"],
                    filename,
                    document["media_type"],
                    document["size_bytes"],
                    document["content_hash"],
                    storage_path,
                    now,
                ),
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
            self._bump_cache_generation(connection, library_id)
        # Invalidate search cache (document count changed)
        get_search_cache().invalidate(library_id)
        return document

    def search_federated(
        self,
        query: str,
        library_ids: list[str] | None = None,
        limit: int = 20,
        actor: dict | None = None,
    ) -> tuple[list[dict], dict]:
        """Performs cross-library federated semantic and keyword search.

        Discovers accessible libraries, executes multi-library retrieval,
        normalizes relevance scores, tags library provenance, and deduplicates
        overlapping chunks.
        """
        normalized = query.strip()
        if not normalized:
            return [], {
                "mode": "federated",
                "libraries_searched": 0,
                "libraries_matched": 0,
                "total_candidates": 0,
            }

        target_libraries: list[dict] = []
        if library_ids:
            for lid in library_ids:
                try:
                    lib = self.get_library(lid, actor=actor)
                    target_libraries.append(lib)
                except (LibraryNotFoundError, LibraryAccessError):
                    continue
        else:
            target_libraries = self.list_libraries(actor=actor)

        if not target_libraries:
            return [], {
                "mode": "federated",
                "libraries_searched": 0,
                "libraries_matched": 0,
                "total_candidates": 0,
            }

        all_citations: list[dict] = []
        libraries_with_matches: set[str] = set()

        for lib in target_libraries:
            lib_id = lib["id"]
            lib_name = lib["name"]
            try:
                citations, _ = self.search_with_profile(lib_id, normalized, limit=limit, actor=actor)
                for item in citations:
                    citation_copy = dict(item)
                    citation_dict = dict(citation_copy.get("citation", {}))
                    citation_dict["library_id"] = lib_id
                    citation_dict["library_name"] = lib_name
                    citation_copy["citation"] = citation_dict
                    citation_copy["library_id"] = lib_id
                    citation_copy["library_name"] = lib_name
                    all_citations.append(citation_copy)
                    libraries_with_matches.add(lib_id)
            except Exception as e:
                _logger.warning("Errore ricerca federata per libreria %s (%s): %s", lib_id, lib_name, e)

        # Deduplication based on content hash & ordinal or normalized excerpt
        seen_keys: set[str] = set()
        deduped_citations: list[dict] = []

        for item in sorted(all_citations, key=lambda x: x.get("relevance_score", 0.0), reverse=True):
            cit = item.get("citation", {})
            dedup_key = f"{cit.get('content_hash', '')}_{cit.get('document_id', '')}_{cit.get('chunk_id', '')}"
            if not cit.get("content_hash"):
                excerpt_snip = (item.get("excerpt", "") or "")[:100].strip().lower()
                dedup_key = f"{cit.get('filename', '')}_{excerpt_snip}"

            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            deduped_citations.append(item)

        final_citations = deduped_citations[:limit]
        profile = {
            "mode": "federated",
            "libraries_searched": len(target_libraries),
            "libraries_matched": len(libraries_with_matches),
            "total_candidates": len(all_citations),
        }
        return final_citations, profile

