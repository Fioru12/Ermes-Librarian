"""PostgreSQL backend: adapter di connessione + DDL (Fase 1 del piano).

Piano completo: docs/POSTGRES_MIGRATION_PLAN.md. Questa fase NON cambia
comportamento: espone lo schema PG che rispecchia 1:1 quello SQLite e un
helper di connessione. Il porting dei metodi di LibraryStore è Fase 2+.

Scelte di traduzione (documentate nel piano):
- FTS5 + trigger -> colonna generata `search_tsv` + indice GIN, config
  'simple' (lingua-neutrale, preserva il comportamento dell'unicode61).
- `embedding_json` TEXT -> JSONB (lettura identica in Python; pgvector è Fase 2).
- Timestamp ISO-8601 restano TEXT per non cambiare la semantica dei confronti.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# DSN di default coerente col container di sviluppo locale (porta 5433
# per non collidere con altri PG già presenti sulla macchina).
DEFAULT_PG_DSN = "postgresql://postgres:ermes_dev@localhost:5433/ermes_test"

POSTGRES_SCHEMA = """
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
    embedding_json JSONB NOT NULL DEFAULT 'null',
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

-- Controparte del virtual table FTS5 + trigger: colonna generata con
-- tokenizzazione 'simple' (lingua-neutrale, come unicode61 senza stemming)
-- e indice GIN. Aggiornata automaticamente da INSERT/UPDATE/DELETE.
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text, ''))) STORED;

CREATE INDEX IF NOT EXISTS chunks_fts
    ON document_chunks USING GIN (search_tsv);
"""

# Tabelle attese, nello stesso insieme dello schema SQLite (l'FTS5 virtuale
# diventa la colonna search_tsv su document_chunks).
EXPECTED_TABLES = {
    "libraries",
    "documents",
    "library_members",
    "document_chunks",
    "document_versions",
    "document_acls",
    "ingestion_jobs",
    "import_sources",
    "chat_integrations",
}


# Secondo percorso di connessione, distinto da PostgresBackend in
# core/database_backend.py. Anche questo aveva bisogno di un timeout
# esplicito: senza, il controllo di disponibilita' in
# tests/test_postgres_parity.py restava appeso oltre due minuti, e quel file
# da solo faceva passare la suite da 68 a 260 secondi.
CONNECT_TIMEOUT_SECONDI = 10


def connect(url: str, timeout: int | None = None):
    """Apri una connessione psycopg con righe dizionario.

    Commit/rollback restano responsabilità del chiamante (stesso contratto
    del context manager SQLite in LibraryStore). Chiusura esplicita richiesta.
    """
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        url,
        row_factory=dict_row,
        autocommit=False,
        connect_timeout=CONNECT_TIMEOUT_SECONDI if timeout is None else timeout,
    )


def ensure_schema(connection) -> None:
    """Crea lo schema PG statement-per-statement.

    psycopg non ha executescript: ogni statement va eseguito singolarmente.
    Lo split su ';' è sicuro: lo schema non contiene ';' dentro stringhe.
    Le righe di commento vengono rimosse perché, dopo lo split, restano
    attaccate allo statement seguente.
    """
    for raw_statement in POSTGRES_SCHEMA.split(";"):
        lines = [line for line in raw_statement.splitlines() if not line.strip().startswith("--")]
        statement = "\n".join(lines).strip()
        if statement:
            connection.execute(statement)
    connection.commit()
