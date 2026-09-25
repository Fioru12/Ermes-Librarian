# ADR 0003 — SQLite come default, PostgreSQL opzionale, niente framework RAG

**Stato:** accettata · **Data:** formalizzata il 25 settembre 2026

## Contesto

Il destinatario tipico è un ufficio senza un team infrastruttura: un server o
un PC in rete, spesso Windows. Ogni servizio in più da installare (database,
vector store, broker) è un motivo per non adottare lo strumento. Le
installazioni multi-utente più grandi, invece, hanno bisogno di concorrenza
vera e di backup gestiti.

## Decisione

1. **SQLite con FTS5 è il backend predefinito**: zero configurazione, un
   file in `data/`, backup copiando un file.
2. **PostgreSQL (+ pgvector) è opzionale** dietro la stessa interfaccia
   (`core/database_backend.py`, `core/postgres_backend.py`) e si attiva con
   `ERMES_DATABASE_URL`. Se l'URL punta a PostgreSQL e il driver manca,
   l'avvio fallisce: non si ripiega in silenzio su SQLite, perché chi imposta
   quell'URL lo fa per avere un'altra garanzia.
3. **Nessun framework RAG** (LlamaIndex, ChromaDB): recupero, ranking e
   citazioni sono codice del progetto.

## Perché niente framework

Con LlamaIndex, ChromaDB e il client Ollama le dipendenze erano circa 150
pacchetti; senza sono 56. Soprattutto, ogni decisione di ADR 0001 e 0002
(astensione, filtro dei permessi prima del ranking, formato delle citazioni)
richiedeva di aggirare le astrazioni del framework invece di usarle.
`tests/test_legacy_packages_stay_out.py` blocca il loro rientro nei
requisiti del prodotto.

## Conseguenze

- Due backend da mantenere in parità: `tests/test_postgres_parity.py` gira in
  CI contro un PostgreSQL 16 reale (servizio del job `test` in
  `.github/workflows/ci.yml`).
- Il ranking è calcolato in Python sui candidati: la mediana resta di pochi
  millisecondi a 50.000 passaggi, ma il caso peggiore arriva a ~3,3 s. La
  direzione indicata è limitare i candidati con il ranking full-text del
  database (`bm25()` su SQLite, `ts_rank` su PostgreSQL).
- Il piano per portare PostgreSQL a default dei deploy multi-utente è in
  `docs/POSTGRES_MIGRATION_PLAN.md`.
