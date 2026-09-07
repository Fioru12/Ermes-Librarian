# Piano di Migrazione a PostgreSQL

> Stato: **GROUNDWORK COMPLETO — migrazione da eseguire** (vedi Fasi).
> Ultimo aggiornamento: 2026-09-06

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
| `ingestion_jobs` | `claim_ingestion_job` usa UPDATE+SELECT: in PG usare `FOR UPDATE SKIP LOCKED` (oggi il file-lock rende impossibili le race; in PG multi-processo servono) |
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

### 2. Similarità vettoriale (rischio MEDIO)
Oggi i chunk portano `embedding_json` e la similarità coseno è calcolata in
Python dopo aver caricato le righe. Fase 1 PG: `JSONB` + calcolo in Python
(comportamento identico). Fase 2 (opzionale): estensione `pgvector` con
indice HNSW — guadagno reale solo oltre ~100k chunk.

### 3. Concorrenza (rischio MEDIO)
- `threading.Lock` protegge solo il processo: con PG multi-worker serve
  transazionalità reale (già presente via context manager) e
  `SELECT ... FOR UPDATE SKIP LOCKED` per i job di ingestion.
- `connection.execute("PRAGMA ...")` e `executescript` non esistono in
  psycopg: lo schema andrà eseguito statement-per-statement.

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
- **Fase 1**: adapter connessione + DDL PG + parity test sullo schema
  (stesse tabelle, stessi vincoli). Nessun cambio di comportamento su SQLite.
- **Fase 2**: porting dei metodi CRUD semplici (libraries, members, ACL,
  import_sources, chat_integrations) con test doppio-backend parametrici.
- **Fase 3**: ingestion_jobs con `SKIP LOCKED` + versioni documenti.
- **Fase 4**: ricerca ibrida su tsvector + benchmark con `evaluation/`
  (gate: nessuna regressione oltre soglia concordata su nDCG/recall).
- **Fase 5**: script di migrazione dati SQLite→PG (`scripts/migrate_to_postgres.py`)
  con verifica conteggi e hash, e flag feature per il cutover.

## Criterio di accettazione

1. Tutti i 275+ test passano su SQLite (default, invariato).
2. Suite parametrica identica passa su PG (docker: `postgres:16-alpine`).
3. Benchmark retrieval invariato (evaluation/).
4. Migrazione dati round-trip verificata su un archivio reale di prova.
