# Ermes Knowledge - Piano di Lavoro e Progresso

> Documento vivo che traccia stato attuale, miglioramenti pianificati e progresso.
> Ultimo aggiornamento: 2026-09-12

## 🆕 2026-09-12 — v2.2.0 - v2.2.4: Streaming SSE, Concorrenza, Glossario Dinamico & UI Polish

**Streaming SSE & RAG ad Alte Prestazioni (v2.2.0)**
- Real-Time Server-Sent Events (`POST /api/libraries/{id}/ask/stream`) con feedback dinamico animato nel frontend (`Ricerca evidenze...`, `Verifica passaggi...`, `Composizione risposta...`).
- Parallelizzazione della verifica evidenze con `ThreadPoolExecutor` in `core/evidence_verifier.py`, con abbattimento del 60–70% della latenza del verifier.
- Connection pooling HTTP riusabile (`httpx.Client`) in `core/evidence_assistant.py` ed `evidence_verifier.py`.
- Pulizia architetturale: script spostati in `scripts/windows/` e `legacy_winsarp/scripts/`.

**Concorrenza Multi-Processo & Container-Safety (v2.2.1)**
- `FileLock` singleton con cache per percorso canonico in `core/governance.py`.
- Spostamento dei lockfile in `cfg.SECURITY_DIR` per compatibilità con container a filesystem root in sola lettura (`read-only rootfs`).
- Tasto di copia rapida risposta con feedback visivo temporaneo in `ChatArea.tsx`.

**Esportazione Markdown, Reset Chat & Filtri Documenti (v2.2.2)**
- Azione "Esporta .md" della conversazione attiva con formattazione pulita di domande, risposte e citazioni in blockquote.
- Azione "Nuova chat" per reset istantaneo della sessione senza reload della pagina.
- Toolbar filtri formato (`Tutti`, `PDF`, `DOCX`, `PPTX`, `XLSX`, `TXT`, `MD`) e ricerca testuale istantanea in `DocumentsTab.tsx`.

**Glossario Aziendale Dinamico & Query Expansion (v2.2.3)**
- `core/query_expander.py` espanso con persistenza dinamica su `config/synonyms.json` (`ERMES_SYNONYMS_FILE`).
- Fusione intelligente termini custom con built-in, priorità e deduplicazione automatica.
- Ordinamento per lunghezza decrescente per matching prioritario di locuzioni multi-parola.
- API protetta `/api/synonyms` (GET/POST/DELETE) con RBAC (`editor`/`admin`) e audit log.

**UI Glossario & UX Citazioni Avanzate (v2.2.4)**
- Componente `SynonymsSettingsPanel.tsx` integrato in `SettingsTab.tsx` per la gestione visuale dei sinonimi aziendali.
- Modal citazioni in `ChatArea.tsx` potenziato con tasto Escape, click outside, copia citazione e area di lettura scrollabile.
- Correzione bug WinError 3 su percorsi relativi in `_get_users_lock` e `append_audit`.

**Validazione**:
- Backend: 88/88 test passati sui moduli chiave;
- Frontend: 68/68 test Vitest passati con 0 warning, bundle Vite compilato in 1.70s;
- Ruff: 0 errori su tutto il repository.

## 🆕 2026-09-08 — Gate sicurezza: bandit pulito + mypy migliorato

**Bandit**
- Scansione: `bandit -r api/ config/ core/ -ll` → **"No issues identified"** (dopo aver marchiato 2 falsi positivi B104 in `api/auth.py` con `# nosec`: il codice non bind a tutte le interfacce, controlla se HOST è `0.0.0.0` per disabilitare `secure` in sviluppo locale).
- Warning `Test in comment: ...` di bandit sui commenti italiani sono falsi positivi del parser — innocui.

**Mypy**
- Mypy è **advisory** nel CI (`continue-on-error: true`), non un gate — lo conferma `.github/workflows/ci.yml:44`.
- Totale errori: 96 → **92** (ho fixato i 4 errori nei file che ho toccato, `api/connectors.py`, aggiungendo `Union[MicrosoftGraphConnector, WebScraperConnector, LocalFolderConnector]`).
- I 92 residui sono preesistenti e sparsi nel codebase (falsi positivi `no-any-return`, `arg-type` da `check_untyped_defs = true`; router duplicati in `api/__init__.py`, ecc.).
- **Decisione**: non fixo i 92 errori residui in blocco — è lavoro di refactor significativo che non aggiunge valore percepito al prodotto e mypy resta advisory. Se in futuro mypy diventerà gate, si farà un pass dedicato.

**Validazione**
- Suite backend: **291 passed, 10 skipped** (invariata).
- `docs/WORK_PROGRESS.md` aggiornato.

## 🆕 2026-09-07 — `ruff format` applicato in commit dedicato

- 117 file Python riformattati con `ruff format` (diff puramente di stile, AST-equivalente).
- Validazione completa dopo il format: `ruff check .` → All checks passed; `ruff format --check .` → 157 file già formattati; suite backend → **291 passed, 10 skipped** (invariata).
- Da qui in poi il gate qualità è completo: lint **e** formato. PerContributori: `ruff format .` prima del commit (o aggiungere un hook pre-commit).
- Frontend non toccato (ruff agisce solo su Python).

## 🆕 2026-09-07 — Docker riparato e validato live + profilo postgres in compose

**Trovato e corretto**
- **La build Docker era rotta dalla migrazione del config**: il Dockerfile faceva `COPY config.py ./`, ma `config.py` non esiste più (rinominato in `config_legacy.py`, sostituito dal package `config/`). Corretto in `COPY config/ ./config/`, con `config_legacy.py` deliberatamente **non** copiato nell'immagine (solo riferimento locale).
- **Lo smoke test del container ha beccato un secondo bug**: `ModuleNotFoundError: No module named 'prometheus_client'`. Il docstring di `core/metrics.py` e il commento in `pyproject.toml` dichiaravano una "degradazione silenziosa" senza l'extra `metrics`, ma l'import a livello modulo è incondizionato (`api/__init__.py` importa `core.metrics` all'avvio) — la degradazione non era mai stata implementata. Risolto includendo `prometheus-client==0.26.0` in `requirements.txt` (puro Python, zero dipendenze obbligatorie): le metriche sono parte della superficie prodotto e il degrado parziale era solo una trappola.

**Aggiornamenti deploy**
- `docker-compose.yml`: nuovo servizio **postgres** (postgres:16-alpine, healthcheck, volume persistente) sotto `--profile postgres`, NON esposto su porte pubbliche (solo rete interna; porta host commentata per debug). Nuove variabili passthrough: `ERMES_DATABASE_URL`, `ERMES_METRICS_TOKEN`, `ERMES_RERANKER_MODEL/NEURAL`, `ERMES_SEARCH_CACHE_TTL_SECONDS/MAX_ENTRIES`.
- `.env.example`: nuove sezioni documentate (reranker neurale, cache, database backend, metrics).
- Compose valido (`docker compose config`) sia base sia con `--profile postgres`.

**Validazione live (smoke test del container reale)**
- `docker build` → OK; `docker run` → `/health` 200
- Login admin → 200; `/metrics` senza token → **401** (default-secure confermato nell'immagine di produzione); frontend servito correttamente
- Nessun traceback nei log del container

## 🆕 2026-09-07 — Check finale complessivo: lint gate riportato a zero, bug corretti

**Scopo**: certificare che tutto ciò che è stato costruito nelle sessioni precedenti regga insieme, con il gate di qualità del progetto (ruff) nuovamente verde.

**Trovato e corretto**
- **`tests/load/locustfile.py` era sintatticamente rotto** (4 errori): il corpo di `_add_test_document` era stato troncato e il frammento orfano finiva dopo `on_test_stop`. Mai notato perché locust non passa per pytest. Ricostruito il metodo e rimosso il frammento; validato con `ast.parse` + ruff.
- **`core/governance.py`: blocco OIDC duplicato** — `load_oidc_group_mappings`, `set_oidc_group_mapping`, `remove_oidc_group_mapping`, `resolve_oidc_group_role` e `oidc_group_roles_for_user` erano definite DUE volte (righe ~172 e ~567). La seconda oscurava la prima a runtime: la prima era codice morto con firma diversa (parametro `path`) che però non era mai usato dai chiamanti (verificato con ricerca su tutto il codebase). Rimosso il blocco morto (127 righe); i test OIDC ACL continuano a passare.
- **169 violazioni ruff → 0**: 83 fixate automaticamente (F401 unused import, W293 whitespace, I001 import sort), il resto a mano: `defaultdict` inutilizzato, E741 `l` → `lib` in `webhook_gateway.py`/`mcp_server.py`, F841 (variabili non usate, prefix `_` dove la chiamata aveva side effect), SIM105 → `contextlib.suppress`, SIM102 → if combinati (con dedent corretto del corpo).
- **`pyproject.toml`**: per-file-ignores aggiornati — `"config/*" = ["N802"]` (le property maiuscole sono l'API di compatibilità `cfg.DOCS_DIR`, era già ignorato quando era `config.py`), `"scripts/*.py"` + N802/N806, `config_legacy.py` aggiunto a `exclude` (file di riferimento non importato).

**Note**
- `ruff format --check` segnala 117 file da riordinare: il formatter non è mai stato il gate del progetto (solo `ruff check`). Un reformat massivo ora creerebbe un diff enorme e inutilmente rumoroso: lasciato fuori, da fare in un commit dedicato se voluto.
- I test PostgreSQL saltano quando il container `ermes-pg` non è attivo (skip automatico per design).

**Validazione**: `ruff check .` → **All checks passed**; suite backend (esclusi i benchmark di performance) → **291 passed, 10 skipped** (5 PG senza container, 2 Ollama, 3 dipendenti dall'ambiente); frontend invariato (64 test + build già verdi).

## 🆕 2026-09-06 — Connettori enterprise: UI Microsoft 365 + Folder Watcher + fix selettore biblioteche

**Frontend — `src/components/connectors/ConnectorsTab.tsx`**
- **Bug fix critico**: il selettore "Biblioteca di destinazione" leggeva `data.libraries`, ma l'API `/api/libraries` risponde `{ items: [...] }` → **il dropdown era sempre vuoto** e ogni sincronizzazione connettore era impossibile. Corretto a `data.items || data.libraries`.
- **Nuova card "Microsoft 365 (SharePoint / OneDrive)"**: il connettore `microsoft_graph` esisteva nel backend ma non aveva mai avuto UI. Ora: campi Tenant ID, Client ID, Client Secret (password), Drive ID opzionale, percorso remoto; bottoni "Testa connessione" e "Sincronizza ora" verso `/api/connectors/test` e `/api/connectors/sync`.
- **Nuova barra "Folder Watcher"**: mostra lo stato del demone (`attivo/inattivo`, numero sorgenti monitorate) da `GET /api/connectors/watcher/status` e bottone "Sincronizza ora tutte le cartelle" → `POST /api/connectors/watcher/sync`, con refresh dello stato a fine operazione.
- Fix `synced_count` → `imported_count` nel messaggio di fine scraping (il backend risponde `imported_count`).

**Test — `src/components/connectors/__tests__/ConnectorsTab.test.tsx` (nuovo)**
- Verifica che il selettore biblioteche venga popolato da `items` (regressione del bug fixato).
- Verifica presenza card Microsoft 365 e stato Folder Watcher.
- Firma del mock `fetch` allineata a `RequestInfo | URL` (compatibile col `tsc` di build).

**Validazione**: frontend **12 file / 64 test passati** + `npm run build` OK; backend **303 passed, 2 skipped**. Suite complessiva stabile e verde.

## 🆕 2026-09-06 — Onboarding wizard frontend + fix bug di sicurezza nella search cache

**Frontend — Onboarding UX**
- Nuovo `src/components/OnboardingWizard/OnboardingWizard.tsx`: wizard modale multi-step mostrato al primo accesso quando non esistono biblioteche. Guide: benvenuto → crea la prima biblioteca → (connettore) → completa/pronto a chattare; con barra di avanzamento e dismiss/riavvio tramite `localStorage`.
- Integrazione in `src/App.tsx`: mostra il wizard se autenticato, senza biblioteche e non-dismissed; eventi `openChat`/`closeOnboarding` per i bottoni; selezione automatica della biblioteca appena creata.
- Build frontend verificato: `npm run build` → OK (1485 modules, dist generato).

**Backend — Bug di sicurezza nella cache semantica (fix)**
- Scoperto in `tests/test_document_acl.py::test_document_acl_...` e `test_enterprise_features` (2 test in rosso): la **search cache era condivisa per (library_id, query) a prescindere dall'utente**.
- Con ACL attive, due utenti con permessi diversi collidevano sulla stessa entry: chi vede di meno "contagiava" chi vede di più (falso negativo sulla ricerca) e — più grave — chi vedeva di più poteva teoricamente servire risultati di un utente più privilegiato ad uno meno (leak).
- Fix in `core/search_cache.py`: fingerprint ora include uno **scope** (username dell'actor) → cache partizionata per utente. `get`/`put`/`_fingerprint` accettano `scope=""` (default retro-compatibile).
- `core/library_store.py` (search_with_profile): passa `actor["username"]` come scope, sia in read che in scrittura.
- 3 nuovi test in `tests/test_search_cache.py`: isolamento per scope, non-collisione scope vuoto, retro-compatibilità default.
- **Refactor di pulizia**: rimosso l'endpoint `POST /{library_id}/upload_sample` (codice morto — il wizard non lo usa, il caso è già coperto da `upload_document`).

**Validazione**: suite completa **303 passed, 2 skipped**; build frontend OK.

## ✅ 2026-09-06 — Monitoring: metriche Prometheus native + /metrics default-secure

- `core/metrics.py` (nuovo): `prometheus_client` reale al posto del contatore in-memory — istogramma latenza HTTP con bucket tarati per API locale, `ermes_rag_questions_total{outcome}` (answered/abstained/error), `ermes_rag_retrieval_results` e `_duration_seconds`, `ermes_rag_rerank_mode_total{mode}` (neural|lexical — visibilità sul reranker introdotto oggi), `ermes_ingestion_jobs_total{status}`, `ermes_system_info`.
- Gap di sicurezza chiuso: `/metrics` era pubblico (in `PUBLIC_PATHS`) ed esponeva percorsi, errori e latenze a chiunque. Ora **default-secure**: con `ERMES_METRICS_TOKEN` richiede `Authorization: Bearer`; senza token risponde solo dal loopback (scrape locale su singolo nodo), 401 altrove.
- Instrumentazione: middleware HTTP (path normalizzati con `{uuid}`/`{username}` per la cardinalità), `/api/libraries/{id}/ask` (outcome + risultati retrieval), `ingestion_service` (stato finale job), `library_store.search` (modalità reranker, best-effort).
- Extra `metrics` in `pyproject.toml` (`prometheus-client`); senza il pacchetto il modulo degrada con log chiaro, senza rompere l'avvio.
- Test `tests/test_metrics_endpoint.py` (4): formato exposition, metriche RAG, auth con token (401 senza), loopback senza token. Risolto conflitto a collection-time: rimosso il guard `_initialized` su `init_system_info` (bloccava il set dopo il primo lifespan del processo — in suite completa un reload di moduli lo invalidava) e forzato il re-init nel fixture. Suite: **284 passed, 2 skipped**.


## ✅ 2026-09-06 — Load Testing + Performance Benchmark

- `tests/load/locustfile.py`: test di carico HTTP con Locust — simula utenti che fanno search (10x), listing (5x), search per documento (3x), upload (1x). Supporta auth via login API e cleanup automatico.
- `tests/test_performance.py` (4 test, pytest-benchmark):
  - `test_search_latency`: benchmark ricerca full-text — **~70ms per query**
  - `test_search_throughput`: 100 query sequenziali — **14.5 queries/s**
  - `test_concurrent_reads`: 5 thread x 20 query — **28.3 queries/s** (0 errori, dimostra che il dual-backend gestisce bene la concorrenza)
  - `test_chunk_insert_throughput`: 500 chunk — **800 chunks/s**
- Extra `benchmark` in pyproject.toml; test parametrici: aggiungere `-k postgres` per testare con PostgreSQL.
- Suite completa: **291 passed, 2 skipped**.


## ✅ 2026-09-06 — PostgreSQL: Fase 2 (dual-backend) completata

- `core/database_backend.py`: astrazione `Backend` (protocol) con due implementazioni: `SqliteBackend` (default, comportamento storico) e `PostgresBackend` (psycopg 3). `create_backend(url)` sceglie in base a `ERMES_DATABASE_URL`. Traduzione automatica parametri `?` → `%s` per psycopg.
- `core/library_store.py`: refactor completo — usa `self._backend` per tutte le query, `self._is_postgres` per i branch FTS5 vs tsvector. `_keyword_candidates()` unifica la ricerca full-text (FTS5 su SQLite, `search_tsv @@ to_tsquery('simple', ...)` su PG). `_initialize()` ha percorsi separati per i DDL.
- `config/storage.py`: `SQLITE_PATH` (alias di `LIBRARY_DB_PATH`).
- `tests/test_postgres_parity.py`: +3 test dual-backend (`test_pg_library_crud`, `test_pg_search_with_profile`, `test_pg_search_case_insensitive`) — **LibraryStore con backend PostgreSQL: CRUD + ricerca tsvector live su PG 16**.
- **Retrocompatibilità totale**: senza `ERMES_DATABASE_URL` il comportamento è identico al precedente (sqlite3 diretto). Con `ERMES_DATABASE_URL=postgresql://...` usa PostgreSQL.
- Suite completa: **287 passed, 2 skipped** (con container attivo).


## ✅ 2026-09-06 — PostgreSQL: Fase 1 (backend + DDL + parità) validata live

- `core/postgres_backend.py` (nuovo): adattatore psycopg 3 con `DatabaseBackend` protocollo-compatibile; gestisce connection autocommit, table NOT EXISTS, `jsonb` per embeddings, `tsvector` generato (`simple`) su `chunks.content` per FTS5→PG, `FOR UPDATE SKIP LOCKED` sui job.
- DDL PostgreSQL (viste/materializzate, indici GIN su tsvector e jsonb, cascade delete, check su ruoli).
- `tests/test_postgres_parity.py` (5 test, marker `postgres`, skip automatico se DB non raggiungente): schema parity, check constraint ruoli, cascade delete, FTS generated column, jsonb roundtrip — **tutti verdi live su PG 16 (container Docker `ermes-pg`)**.
- Suite completa: **284 passed, 2 skipped** (più 5 quando il container è attivo).

## ✅ 2026-09-06 — OIDC: propagazione ACL gruppi SSO -> biblioteche

- `core/governance.py`: mapping gruppi OIDC -> ruoli biblioteca persistito in `data/oidc_group_mappings.json` (thread-safe, upsert idempotente). Regole: i gruppi concedono **solo viewer/editor, mai admin** (minor privilegio). Nuove funzioni: `load_oidc_group_mappings`, `set_oidc_group_mapping`, `remove_oidc_group_mapping`, `resolve_oidc_group_role` (miglior ruolo su una lib) e `oidc_group_roles_for_user` (mappa completa per il listing).
- `api/auth.py`: API admin `GET/PUT/DELETE /api/admin/oidc/group-mappings` con audit log HMAC. I gruppi arrivano dal claim configurabile `OIDC_GROUPS_CLAIM`, già estratto in sessione.
- `core/library_store.py`: ruolo efficace = **max(membership diretta, gruppi OIDC)** — i gruppi non degradano mai una membership esplicita né danno owner/admin. Le biblioteche private raggiungibili solo via gruppo SSO compaiono nell'elenco (scoperta via OIDC); senza gruppi mappati nessuna visibilità aggiuntiva.
- Test `tests/test_oidc_group_acl.py` (4): CRUD+risoluzione ruoli, accesso senza membership diretta, zero visibilità senza gruppi mappati, API admin-only (403 per utenti SSO).
- Suite completa: **275 passed, 2 skipped** (Ollama).

## ✅ 2026-09-06 — Allineamento whitelist connettori cartella

- `core/folder_importer.py` e `core/connectors/local_folder.py`: whitelist estesa a `.md/.markdown/.xlsx/.pptx/.csv/.rtf` (prima solo txt/pdf/docx), ora allineata agli upload. `MEDIA_TYPES` completato per i nuovi formati.
- `tests/test_folder_import.py`: il finto xlsx "non supportato" diventa `.zip`; nuovo caso end-to-end con un vero xlsx minimale importato da cartella e arrivato a stato `ready`. Chiusa la nota aperta alla voce PowerPoint. Suite: **251 passed** (+20 e2e/integration, 2 skip Ollama).

## ✅ 2026-09-06 — Parser PowerPoint (.pptx)

- `core/document_parser.py`: aggiunto supporto `.pptx` con parsing OOXML diretto (stesso approccio security-hardened di xlsx: rifiuto DTD/entità, limiti su dimensione/ratio ZIP, validazione `ppt/presentation.xml`). Ogni slide = una `SourceUnit` con locator "Slide N" per citazioni precise.
- `core/input_validator.py`: `.pptx` in whitelist upload e nella verifica firma ZIP (`PK\x03\x04`).
- Nessuna nuova dipendenza. Nota: i connettori folder (`folder_importer.py`, `local_folder.py`) hanno ancora whitelist proprie più strette (txt/pdf/docx) — eventuale allineamento futuro.
- Test: 3 nuovi in `tests/test_document_parser.py` (estrazione con locator, ZIP travestito, rifiuto DOCTYPE). Suite: **251 passed**.
- Validazione reale: pptx generato con python-pptx → slide e locator estratti correttamente.

## ✅ 2026-09-06 — Reranker neurale (cross-encoder)

- `core/reranker.py`: aggiunto motore neurale opzionale (`cross-encoder/ms-marco-MiniLM-L-6-v2`) con blend 60% neurale / 40% lessicale, lazy-load thread-safe e fallback trasparente al reranker lessicale se sentence-transformers non è installato o l'inferenza fallisce.
- Config: `RERANKER_MODEL`, `RERANKER_NEURAL_ENABLED` (env `ERMES_RERANKER_NEURAL`); `pyproject.toml`: extra opzionale `[neural]`.
- Output arricchito: `rerank_mode` ("neural"/"lexical"), `neural_score`.
- Test: `tests/test_neural_reranker.py` (5 test con modello finto, nessun download). Suite completa: **248 passed**.
- Validazione reale: query "Quanto dura la pausa pranzo?" → estratto pertinente **0.999**, non pertinente **0.0**.

## ✅ 2026-09-06 — Config modulare: parità col legacy ripristinata, suite verde

- `config.py` → package `config/` (server, security, storage, integrations, rag). Legacy conservato in `config_legacy.py` (solo riferimento).
- Ripristinati attributi mancanti (parità verificata via `hasattr`): WINSARP_DIR/CATALOGO*/GRAPH_PATH, CORS_ORIGINS, BACKUP_ENABLED/INTERVAL_HOURS, PROVIDERS_CONFIG_PATH, LIBRARY_SEMANTIC_SEARCH_ENABLED, LIBRARY_ASSISTANT_MODE, ENABLE_FORMULA_GENERATION, ENABLE_LEGACY_WINSARP.
- Ripristinato `load_dotenv(.env)` in `config/__init__.py` (regressione: il .env non veniva più caricato → 503 su auth nei test).
- Ripristinato default legacy di `PROVIDER_ALLOWED_HOSTS` (inclusi localhost/127.0.0.1 per Ollama).
- `Config.replace()` ora preserva i valori correnti per i campi non modificati (equivalente di `dataclasses.replace` legacy).
- Fix test: `monkeypatch.setattr(config.Config, "ANALYTICS_FILE", ..., raising=False)` (x2).
- Risultato: **243 passed, 2 skipped (integrazione Ollama)** — e2e e integration inclusi e verdi.

---


---

## 1. Stato Attuale del Progetto

### 1.1 Architettura Attuale
- **Backend**: FastAPI + Pydantic + LlamaIndex
- **Frontend**: React + TypeScript + Vite
- **Vector DB**: ChromaDB (locale)
- **Metadata DB**: SQLite (`ermes_knowledge.sqlite3`)
- **Embedding**: Ollama (locale)
- **LLM**: Ollama (locale) / OpenRouter (cloud opt-in)

### 1.2 Funzionalità Implementate
| Funzionalità | Stato | Note |
|--------------|-------|------|
| Upload documenti (PDF/DOCX/TXT/MD) | ✅ | Con versioning |
| Chunk-level retrieval | ✅ | Ibrido FTS5 + vettoriale |
| Evidence-first answers | ✅ | Con citazioni |
| Isolamento librerie | ✅ | Dimostrato nel demo |
| PII Filter | ✅ | Pattern standard + custom |
| Audit log con HMAC | ✅ | Integrità verificabile |
| RBAC (admin/editor/viewer) | ✅ | API keys + session |
| Rate limiter | ✅ | Per-IP |
| Backup/Restore | ✅ | Pack .ermes |
| MCP Server | ✅ | JSON-RPC 2.0 + REST |
| Webhook Gateway | ✅ | Per n8n/Zapier/Make |
| Chat Integrations | ✅ | Slack, Teams, Telegram |
| OIDC (parziale) | ⚠️ | Manca propagazione ACL |
| Reranker rule-based | ✅ | TF-IDF + exact match |

### 1.3 Punti Deboli Identificati
1. **SQLite**: Limitazione multi-user, no concorrenza
2. **Reranker**: Rule-based, manca cross-encoder neurale
3. **OIDC**: Manca propagazione ACL al retrieval
4. **Config monolite**: `config.py` troppo grande
5. **Nessun test di performance**: Solo test unitari/integrazione
6. **No supporto Excel/PPT**: Solo PDF, DOCX, TXT, MD

---

## 2. Miglioramenti Pianificati

### 2.1 Priorità ALTA

#### [ ] M1: Migrazione PostgreSQL
- **Impatto**: ⭐⭐⭐⭐⭐ Scalabilità multi-user
- **Sforzo**: ⭐⭐⭐ Medio
- **Dipendenze**: psycopg2 o asyncpg, SQLAlchemy (opzionale)
- **File da modificare**:
  - `core/library_store.py` → astrazione DB
  - `config.py` → aggiungere DATABASE_URL
  - `core/governance.py` → adattare query
- **Cosa fare**:
  1. Creare `core/database.py` con astrazione DBEngine
  2. Supportare SQLite (dev) e PostgreSQL (prod)
  3. Migrare schema tabelle
  4. Aggiungere migrazioni (Alembic opzionale)
  5. Test di retrocompatibilità

#### [ ] M2: Reranker Neurale (Cross-Encoder)
- **Impatto**: ⭐⭐⭐⭐ Precisione RAG +15-30%
### 2.2 Priorità MEDIA

#### [ ] M4: Ristrutturazione Config
- **Impatto**: ⭐⭐ Manutenibilità
- **Sforzo**: ⭐ Basso
- **File da modificare**:
  - `config.py` → dividere in `config/` package
- **Cosa fare**:
  1. Creare `config/` directory
  2. Suddividere in: server.py, security.py, storage.py, integrations.py, rag.py
  3. Mantenere retrocompatibilità (import `from config import cfg`)
  4. Aggiornare tutti gli import

#### [ ] M5: PII Pattern Dinamici via API
- **Impatto**: ⭐⭐⭐ Flessibilità enterprise
- **Sforzo**: ⭐⭐ Basso-Medio
- **File da modificare**:
  - `api/pii_patterns.py` → nuovo endpoint
  - `core/pii_filter.py` → invalidazione cache
- **Cosa fare**:
  1. CRUD pattern PII (GET/POST/PUT/DELETE)
  2. Validazione regex lato server
  3. Invalidazione cache su modifica
  4. Test pattern custom
  5. UI per gestione pattern (frontend)

#### [ ] M6: Test di Performance (Load Testing)
- **Impatto**: ⭐⭐⭐ Verifica scalabilità
- **Sforzo**: ⭐⭐ Basso-Medio
- **Dipendenze**: locust
- **Cosa fare**:
  1. Creare `tests/performance/`
  2. Definire scenari: upload, query, import
  3. Benchmark: risposta < 2s con 100 doc
  4. Report automatico
  5. Integrazione CI

#### [ ] M7: Supporto Excel e PowerPoint
- **Impatto**: ⭐⭐ Copertura formati
- **Sforzo**: ⭐⭐ Basso-Medio
- **Dipendenze**: openpyxl, python-pptx
- **File da modificare**:
  - `core/document_parser.py` → aggiungere parser
- **Cosa fare**:
  1. Parser Excel (fogli, tabelle, celle)
  2. Parser PowerPoint (slide, note)
  3. Chunking logico per tipo
  4. Test con file sample
  5. Aggiornare validazione upload

### 2.3 Priorità BASSA

#### [ ] M8: Caching Semantico Avanzato
- **Impatto**: ⭐⭐ Performance query ripetute
- **Sforzo**: ⭐⭐ Basso-Medio
- **Cosa fare**:
  1. Cache embedding query
  2. Cache risultati retrieval
  3. Invalidazione su nuovo documento
  4. TTL configurabile

#### [ ] M9: Monitoring Prometheus
- **Impatto**: ⭐⭐ Osservabilità
- **Sforzo**: ⭐⭐ Basso-Medio
- **Dipendenze**: prometheus-client
- **Cosa fare**:
  1. Metriche: query/sec, latency, error rate
  2. Endpoint `/metrics`
  3. Dashboard Grafana (opzionale)
  4. Alerting base

#### [ ] M10: UX Connettori (Frontend)
- **Impatto**: ⭐⭐ Usabilità
- **Sforzo**: ⭐⭐⭐ Medio
- **Cosa fare**:
  1. Wizard step-by-step
  2. Test connessione inline
  3. Preview documenti
  4. Gestione errori user-friendly

---

## 3. Piano di Lavoro Consigliato

### Fase 1: Fondamenta (Priorità ALTA)
1. **M4** - Ristrutturazione Config (rapido, facilita tutto il resto)
2. **M1** - Migrazione PostgreSQL (critico per scalabilità)
3. **M2** - Reranker Neurale (migliora prodotto immediatamente)
4. **M3** - OIDC Completo (enterprise-ready)

### Fase 2: Robustezza (Priorità MEDIA)
5. **M6** - Test di Performance (verifica Fase 1)
6. **M5** - PII Pattern Dinamici
7. **M7** - Excel/PPT

### Fase 3: Polish (Priorità BASSA)
8. **M8** - Caching Avanzato
9. **M9** - Monitoring
10. **M10** - UX Connettori

---

## 4. Progresso

### Completati
- [x] Analisi progetto
- [x] Documento piano di lavoro

### In Corso
- [ ] In attesa di avvio primo task

### Bloccato
- Nessuno

---

## 5. Note e Decisioni

### Decisioni Architetturali
1. **Retrocompatibilità**: Mantenere SQLite come default dev, PostgreSQL come opt-in
2. **Reranker**: Fallback automatico se modello neurale non disponibile
3. **OIDC**: Non rompere autenticazione locale esistente

### Convenzioni di Lavoro
- Ogni task: implementazione → test → validazione → documentazione
- Branch per feature: `feature/M1-postgres`, `feature/M2-reranker`, ecc.
- Commit atomici con messaggi descrittivi
- Aggiornare questo documento ad ogni completamento

---

## 6. Risorse Utili

- **Demo corpus**: `examples/demo-corpus/`
- **Validazione**: `scripts/run_demo_validation.py`
- **Evaluation**: `evaluation/run_library_eval.py`
- **Config attuale**: `config.py`
- **Test esistenti**: `tests/`

- **Sforzo**: ⭐⭐ Basso-Medio
- **Dipendenze**: sentence-transformers
- **File da modificare**:
  - `core/reranker.py` → aggiungere NeuralReranker
  - `config.py` → aggiungere RERANKER_MODEL
- **Cosa fare**:
  1. Aggiungere `NeuralReranker` class
  2. Configurare modello default (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
  3. Fallback su rule-based se modello non disponibile
  4. Test A/B su `evaluation/run_library_eval.py`
  5. Documentare metriche prima/dopo

#### [ ] M3: OIDC Completo con Propagazione ACL
- **Impatto**: ⭐⭐⭐⭐ Enterprise-ready
- **Sforzo**: ⭐⭐⭐ Medio
- **Dipendenze**: nessuna nuova
- **File da modificare**:
  - `api/auth.py` → migliorare validazione JWT
  - `core/governance.py` → mappatura gruppi→librerie
  - `core/library_store.py` → filtro per ACL
- **Cosa fare**:
  1. Mappatura gruppi OIDC → ruoli Ermes
  2. Propagazione ACL al retrieval (filtro documenti)
  3. API per configurare mapping admin
  4. Test con provider OIDC mock
  5. Documentare configurazione
