# Piano di Migrazione a PostgreSQL

> Stato: **Tutte le Fasi 0-5 completate e verificate.**
> - Fasi 0-4 verificate in CI contro Postgres 16 (`tests/test_postgres_parity.py`).
> - Fase 3 (concorrenza `SELECT ... FOR UPDATE SKIP LOCKED` per worker multipli) implementata in `core/library_store.py`.
> - Fase 5 (script di migrazione dati a blocchi e verifica integrità) implementata in `scripts/migrate_sqlite_to_postgres.py` e testata in `tests/test_postgres_migration.py`.
> Ultimo aggiornamento: 2026-09-23

## Perché un piano e non un refactoring diretto

`core/library_store.py` è ~1250 righe di SQL SQLite-specifico con ~60 metodi:
FTS5 per la ricerca full-text, `sqlite3.Row`, PRAGMA WAL, `executescript`,
JSON in colonna TEXT, lock `threading.Lock` a livello processo. Una
traduzione "in corsa" avrebbe rotto la ricerca ibrida (che è il cuore del
prodotto) senza modo semplice di accorgersene nei test esistenti, che girano
su SQLite. La migrazione è stata quindi eseguita per fasi verificabili.

## Configurazione (attiva e supportata)

- `ERMES_DATABASE_URL` (vuoto di default = SQLite, zero-config come oggi).
  Esempio: `postgresql://ermes:secret@localhost:5432/ermes`
- Extra installazione: `pip install .[postgres]` (psycopg 3)
- Le due variabili sono esclusive: se `DATABASE_URL` è impostato ha
  precedenza; `LIBRARY_DB_PATH` resta il fallback di sviluppo.

## Schema attuale — sorgente di verità

| Tabella | Note per la compatibilità |
|---|---|
| `libraries` | semplice; `visibility` CHECK implicito via codice |
| `documents` | `extracted_text` gestito nativamente via TOAST in PostgreSQL |
| `library_members` | CHECK(role IN viewer/reviewer/editor/manager) identico |
| `document_chunks` | `embedding_json` JSONB; `pgvector` HNSW opzionale |
| `document_versions` | chiave composta (document_id, version) |
| `document_acls` | chiave composta, usato dal filtro per-documento |
| `ingestion_jobs` | `claim_next_ingestion_job` usa `SELECT ... FOR UPDATE SKIP LOCKED` atomico in PostgreSQL per scalare su $N$ worker/pod concorrenti senza conflitti |
| `import_sources` | UNIQUE(library_id, path) |
| `chat_integrations` | UNIQUE(platform, external_channel_id) |

## Le 5 aree di implementazione

### 1. FTS5 → full-text PostgreSQL (FATTO)
La ricerca ibrida usa colonna `tsvector` generata + indice GIN (`search_tsv`)
con configurazione `'simple'` per preservare il comportamento lingua-neutrale.

### 2. Similarità vettoriale (FATTO)
`embedding_json` è `JSONB`; l'estensione `pgvector` con indice HNSW è
implementata e opzionale (`core/postgres_backend.py::enable_pgvector`).

### 3. Concorrenza & Ingestion Jobs (FATTO)
- `claim_next_ingestion_job` su PostgreSQL esegue una singola query atomica:
  `UPDATE ingestion_jobs SET status = 'processing' WHERE id = (SELECT id FROM ingestion_jobs WHERE status = 'queued' ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *`.
- Permette scalabilità orizzontale a worker e processi multipli senza lock bloccanti.

### 4. Tipi e valori (FATTO)
- `sqlite3.Row` → `psycopg.rows.dict_row`
- Date come TEXT ISO-8601 preservate in entrambi i backend.

### 5. Doppio backend & Migrazione Dati (FATTO)
- `LibraryStore` opera in modo trasparente sia su SQLite che su PostgreSQL.
- Script di migrazione a blocchi: `scripts/migrate_sqlite_to_postgres.py` per
  migrare archivi esistenti con verifica conteggi e integrità.

## Fasi

- **Fase 0 (fatta)**: config `ERMES_DATABASE_URL`, extra `postgres`.
- **Fase 1 (fatta)**: adapter connessione (`PostgresConnectionAdapter`, traduzione `?`→`%s`) + DDL PG (`ensure_schema`) + parity test.
- **Fase 2 (fatta)**: `LibraryStore` gira identico su entrambi i backend (`tests/test_postgres_parity.py`).
- **Fase 3 (fatta)**: `ingestion_jobs` con `SELECT ... FOR UPDATE SKIP LOCKED` per worker paralleli distribuiti.
- **Fase 4 (fatta)**: ricerca ibrida su `tsvector` + GIN (`search_tsv`) e `pgvector`/HNSW.
- **Fase 5 (fatta)**: script di migrazione `scripts/migrate_sqlite_to_postgres.py` e test in `tests/test_postgres_migration.py`.

## Criterio di accettazione

1. Tutti i test passano su SQLite (default, invariato) — ✅ VERIFICATO.
2. Suite parametrica identica passa su PG (docker: `postgres:16-alpine`) — ✅ VERIFICATO in CI.
3. Claim atomico concorrente `SKIP LOCKED` per worker multipli — ✅ IMPLEMENTATO e TESTATO.
4. Script di migrazione con verifica conteggi e parità — ✅ IMPLEMENTATO e TESTATO.
