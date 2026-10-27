"""SQLite schema and in-place migrations for the library store."""

from __future__ import annotations


def initialize_sqlite_schema(connection) -> None:
    """Crea lo schema SQLite e applica le migrazioni dei database creati da build precedenti."""
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
