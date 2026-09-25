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
    completed_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    total_chunks INTEGER NOT NULL DEFAULT 0,
    processed_chunks INTEGER NOT NULL DEFAULT 0,
    dead_letter_reason TEXT NOT NULL DEFAULT ''
);
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS total_chunks INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS processed_chunks INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS dead_letter_reason TEXT NOT NULL DEFAULT '';
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


# ---------------------------------------------------------------------------
# Supporto Nativo pgvector (Fase 2 del piano PG)
# ---------------------------------------------------------------------------

PGVECTOR_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector;"

def format_vector_for_sql(vector: list[float]) -> str:
    """Formatta una lista di float nel formato stringa atteso da pgvector: '[v1,v2,...]'."""
    return f"[{','.join(f'{x:.8f}' for x in vector)}]"


def enable_pgvector(connection, vector_dim: int | None = None) -> bool:
    """Abilita l'estensione pgvector, la colonna embedding_vector e l'indice HNSW.

    Restituisce True se l'estensione e l'indice sono stati creati con successo,
    False se l'estensione pgvector non è presente sul server PostgreSQL.
    """
    try:
        connection.execute(PGVECTOR_EXTENSION_SQL)
        col_type = f"vector({vector_dim})" if vector_dim else "vector"
        connection.execute(f"ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_vector {col_type};")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS chunks_hnsw ON document_chunks "
            "USING hnsw (embedding_vector vector_cosine_ops);"
        )
        connection.commit()
        logger.info("pgvector e indice HNSW abilitati con successo (dim=%s)", vector_dim or "variabile")
        return True
    except Exception as exc:
        logger.warning("pgvector non disponibile su questo PostgreSQL: %s", exc)
        connection.rollback()
        return False


def search_chunks_vector(
    connection,
    library_id: str,
    query_vector: list[float],
    top_k: int = 20,
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Esegue nearest-neighbor search su PostgreSQL tramite indice HNSW e similarità coseno (<=>).

    Restituisce i chunk ordinati per punteggio decrescente con score normalizzato.
    """
    vec_literal = format_vector_for_sql(query_vector)
    where_parts = [
        "d.library_id = %(library_id)s",
        "c.embedding_vector IS NOT NULL",
    ]
    params: dict[str, object] = {
        "library_id": library_id,
        "query_vec": vec_literal,
        "limit": top_k,
    }
    if document_ids:
        where_parts.append("c.document_id = ANY(%(doc_ids)s)")
        params["doc_ids"] = document_ids

    where_clause = " AND ".join(where_parts)
    # where_parts sono frammenti letterali fissi, mai costruiti da input: i valori
    # passano tutti da %(...)s. Vedi core/library_store.py per lo stesso pattern.
    query = f"""
        SELECT
            c.id,
            c.document_id,
            c.ordinal,
            c.text,
            c.source_locator,
            1.0 - (c.embedding_vector <=> %(query_vec)s::vector) AS score
        FROM document_chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE {where_clause}
        ORDER BY c.embedding_vector <=> %(query_vec)s::vector ASC
        LIMIT %(limit)s
    """  # nosec B608
    cursor = connection.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def sync_vector_embeddings(connection, batch_size: int = 500) -> int:
    """Sincronizza i vettori da embedding_json a embedding_vector per i chunk non ancora migrati.

    Restituisce il numero totale di chunk migrati.
    """
    import json

    cursor = connection.execute(
        """
        SELECT id, embedding_json
        FROM document_chunks
        WHERE embedding_vector IS NULL
          AND embedding_json IS NOT NULL
        LIMIT %(batch_size)s
        """,
        {"batch_size": batch_size},
    )
    rows = cursor.fetchall()
    if not rows:
        return 0

    updates = []
    for row in rows:
        raw_emb = row["embedding_json"]
        if isinstance(raw_emb, str):
            try:
                emb = json.loads(raw_emb)
            except Exception:
                continue
        elif isinstance(raw_emb, list):
            emb = raw_emb
        else:
            continue

        if emb and isinstance(emb, list) and isinstance(emb[0], (int, float)):
            updates.append((format_vector_for_sql(emb), row["id"]))

    if updates:
        for vec_str, chunk_id in updates:
            connection.execute(
                "UPDATE document_chunks SET embedding_vector = %s::vector WHERE id = %s",
                (vec_str, chunk_id),
            )
        connection.commit()

    return len(updates)

