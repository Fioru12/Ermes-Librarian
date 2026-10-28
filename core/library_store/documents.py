"""Documents, versions, chunks, document ACLs and library deletion."""

from __future__ import annotations

import hashlib
import json
import uuid

from core.library_store.base import StoreBase
from core.library_store.common import (
    LibraryAccessError,
    LibraryNotFoundError,
)
from core.search_cache import get_search_cache


class DocumentsMixin(StoreBase):
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

    def existing_content_hashes(self, library_id: str) -> set[str]:
        """Content hashes of every document in the library, for import dedupe."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT content_hash FROM documents WHERE library_id = ?",
                (library_id,),
            ).fetchall()
        return {row["content_hash"] for row in rows}

    def content_hash_index(self, library_id: str) -> dict[str, str]:
        """Impronta del contenuto -> id del documento, per aggiornare i permessi dei file gia' importati."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, content_hash FROM documents WHERE library_id = ?",
                (library_id,),
            ).fetchall()
        return {row["content_hash"]: row["id"] for row in rows}

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
        allowed_usernames: list[str] | None = None,
    ) -> dict:
        """Aggiunge un documento, o una nuova versione se il nome esiste gia'.

        `allowed_usernames` (None = regole della biblioteca) scrive la
        allow-list nella stessa transazione: un documento che deve nascere
        riservato non e' mai visibile, nemmeno per un istante, a tutta la
        biblioteca.
        """
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
            if allowed_usernames is not None:
                connection.execute("DELETE FROM document_acls WHERE document_id = ?", (document["id"],))
                connection.executemany(
                    "INSERT INTO document_acls (document_id, username, created_at) VALUES (?, ?, ?)",
                    [(document["id"], name, now) for name in sorted({n.strip() for n in allowed_usernames if n.strip()})],
                )
            self._bump_cache_generation(connection, library_id)
        # Invalidate search cache (document count changed)
        get_search_cache().invalidate(library_id)
        return document
