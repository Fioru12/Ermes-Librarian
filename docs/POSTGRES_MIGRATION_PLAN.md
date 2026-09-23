# Piano di Migrazione a PostgreSQL

> Stato: **Fasi 0-4 fatte e verificate in CI contro un Postgres 16 reale
> (`tests/test_postgres_parity.py`, 11 test); Fase 5 (script di migrazione
> dati) non iniziata.** Questo file è rimasto fermo al 6 settembre 2026
> mentre il lavoro procedeva altrove, ed è stato letto — comprensibilmente,
> visto lo stato dichiarato — come prova che la migrazione non fosse ancora
> partita. Non fidarti di questa intestazione più della CI: `git log --
> core/postgres_backend.py core/database_backend.py` mostra il lavoro reale.
> Ultimo aggiornamento: 2026-09-23

## Perché un piano e non un refactoring diretto

`core/library_store.py` è ~1250 righe di SQL SQLite-specifico con ~60 metodi:
FTS5 per la ricerca full-text, `sqlite3.Row`, PRAGMA WAL, `executescript`,
JSON in colonna TEXT, lock `threading.Lock` a livello processo. Una
traduzione "in corsa" avrebbe rotto la ricerca ibrida (che è il cuore del
prodotto) senza modo semplice di accorgersene nei test esistenti, che girano
su SQLite. La migrazione va quindi fatta per fasi verificabili.

## Configurazione (già attiva)

- `ERMES_DATABASE_URL` (vuoto di default = SQLite, zero-config come oggi).
  Esempio: `postgresql://ermes:secret@localhost:5432/ermes`
- Extra installazione: `pip install .[postgres]` (psycopg 3)
- Le due variabili sono esclusive: se `DATABASE_URL` è impostato ha
  precedenza; `LIBRARY_DB_PATH` resta il fallback di sviluppo.

## Schema attuale (SQLite) — sorgente di verità

| Tabella | Note critiche per la traduzione |
|---|---|
| `libraries` | semplice; `visibility` CHECK implicito via codice |
| `documents` | `extracted_text` può essere MB: in PG valutare `TOAST`/colonna separata |
| `library_members` | CHECK(role IN viewer/editor) → vincolo PG identico |
| `document_chunks` | `embedding_json` TEXT (JSON di float). In PG: `JSONB` ora, **pgvector** in fase 2 |
| `document_versions` | chiave composta (document_id, version) |
| `document_acls` | chiave composta, usato dal filtro per-documento |
| `ingestion_jobs` | `claim_ingestion_job` usa UPDATE+SELECT sotto un `threading.RLock` per-backend (`PostgresBackend._serial`, non `FOR UPDATE SKIP LOCKED`): corretto — un solo processo alla volta tocca la connessione — ma serializza il claim invece di lasciarlo concorrente. A un solo worker (`ERMES_INGESTION_WORKERS` di default) non si nota; con più worker/processi diventa un collo di bottiglia, non un bug. `SKIP LOCKED` resta la Fase 3, non iniziata. |
| `import_sources` | UNIQUE(library_id, path) |
| `chat_integrations` | UNIQUE(platform, external_channel_id) |

## Le 5 aree di rischio (in ordine di difficoltà)

### 1. FTS5 → full-text PostgreSQL (rischio ALTO)
La ricerca ibrida usa `MATCH` FTS5 con tokenizzazione custom
(`_search_token`, foreground delle stopwords in `reranker.py`). In PG:
- colonna `tsvector` generata + indice GIN
- query con `plainto_tsquery('simple', ...)` (la config `'simple'` preserva
  il comportamento lingua-neutrale; `'italian'` farebbe stemming diverso)
- **Verifica obbligatoria**: parità dei risultati con la suite
  `evaluation/` (RETRIEVAL_EVALUATION.md) prima e dopo.

### 2. Similarità vettoriale (rischio MEDIO) — FATTO
`embedding_json` è `JSONB`; il calcolo in Python resta il percorso di
default (comportamento identico a SQLite). L'estensione `pgvector` con
indice HNSW è implementata e opzionale (`core/postgres_backend.py::
enable_pgvector`) — va abilitata esplicitamente, il guadagno è reale solo
oltre ~100k chunk.

### 3. Concorrenza (rischio MEDIO) — parzialmente fatto
- psycopg non è thread-safe per connessione: `PostgresBackend` tiene un
  `threading.RLock` (`_serial`) che serializza *ogni* accesso del processo
  alla connessione — scrittura corretta, ma non concorrenza reale.
  `SELECT ... FOR UPDATE SKIP LOCKED` per i job di ingestion (Fase 3) resta
  da fare: oggi il claim funziona ma non scala oltre un worker per processo.
- `connection.execute("PRAGMA ...")` e `executescript` non esistono in
  psycopg: lo schema viene eseguito statement-per-statement
  (`ensure_schema`), fatto.

### 4. Tipi e valori (rischio BASSO ma capillare)
- `sqlite3.Row` → `psycopg.rows.dict_row`
- `INTEGER` truthiness e date come TEXT ISO-8601: restano stringhe anche in
  PG (colonne TEXT) per non cambiare la semantica dei confronti.
- `ON CONFLICT` / `last_insert_rowid` da rivedere puntualmente.

### 5. Doppio backend (rischio BASSO)
I test devono continuare a girare su SQLite (veloci, tmp_path). Struttura
consigliata: `LibraryStore` (logica/ACL invariata) + adapter di connessione
che espone `execute/execute_many/query` nel dialetto giusto. La logica
business NON deve duplicarsi.

## Fasi

- **Fase 0 (fatta)**: config `ERMES_DATABASE_URL`, extra `postgres`, questo documento.
- **Fase 1 (fatta)**: adapter connessione (`PostgresConnectionAdapter`,
  traduzione `?`→`%s`) + DDL PG (`ensure_schema`) + parity test sullo schema.
  Nessun cambio di comportamento su SQLite. Verificato in CI contro
  `postgres:16-alpine` reale (job `test`, non un mock).
- **Fase 2 (fatta)**: `LibraryStore` gira identico su entrambi i backend —
  libraries, members, ACL, import_sources, chat_integrations, versioni
  documento — coperto da `tests/test_postgres_parity.py` (11 test: CRUD,
  cascade delete, vincoli CHECK, integrity error non-500, roundtrip JSONB).
- **Fase 3 (non iniziata)**: `ingestion_jobs` con `SELECT ... FOR UPDATE
  SKIP LOCKED`. Oggi il claim è corretto ma serializzato da un lock per
  processo (vedi sezione Concorrenza) — funziona, non scala oltre un
  worker.
- **Fase 4 (fatta)**: ricerca ibrida su `tsvector` + GIN (`search_tsv`,
  tokenizzazione `'simple'` come da piano) e similarità vettoriale via
  `pgvector`/HNSW opzionale. Non è stato eseguito un benchmark A/B
  SQLite-vs-PG con `evaluation/`: la parità è verificata a livello di
  schema e query, non di nDCG/recall misurato sui due backend.
- **Fase 5 (non iniziata)**: script di migrazione dati SQLite→PG
  (`scripts/migrate_to_postgres.py` non esiste ancora) con verifica
  conteggi e hash, e flag feature per il cutover. Oggi passare a Postgres
  significa ripartire da un database vuoto, non migrare dati esistenti.

## Criterio di accettazione

1. Tutti i test passano su SQLite (default, invariato) — vero oggi.
2. Suite parametrica identica passa su PG (docker: `postgres:16-alpine`) — vero oggi, in CI a ogni push.
3. Benchmark retrieval invariato (evaluation/) — non ancora eseguito su PG.
4. Migrazione dati round-trip verificata su un archivio reale di prova — non ancora possibile, manca lo script (Fase 5).
