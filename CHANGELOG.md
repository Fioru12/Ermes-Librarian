# Changelog

Registro leggibile del lavoro su questo progetto. Per il dettaglio fase-per-fase con motivazioni, vedi [docs/ROADMAP_V2.md](docs/ROADMAP_V2.md); per i finding tecnici completi, [docs/AUDIT_2026-08-19.md](docs/AUDIT_2026-08-19.md) e [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md); per il registro operativo delle sessioni, [docs/WORK_PROGRESS.md](docs/WORK_PROGRESS.md).

## 2026-09-18 — v2.2.5: Clone pulito Linux verificato in CI e profilo "verified" con Ollama dichiarato

- **Smoke test Compose in CI** (`compose-smoke` in `.github/workflows/ci.yml`): su `ubuntu-latest` costruisce l'immagine, avvia `app` con `docker compose up --no-deps` (nessun Ollama: il default non usa modelli), attende `/health` = `healthy` ed esegue `scripts/run_demo_validation.py` contro il container (5 documenti, 4 risposte citate, 1 astensione, isolamento tra biblioteche). Fino a oggi il Dockerfile veniva costruito e pubblicato ma l'immagine non veniva mai avviata da nessun job, e il percorso README era stato verificato solo su Windows. Bloccante per `pre-deploy-backup` e `docker`.
- **Bug: il container partiva con il reranker acceso.** `docker-compose.yml` impostava `ERMES_RERANKER_ENABLED=${...:-1}` mentre il config e il README dicono `0` — il reranker è misurato peggiore in ogni configurazione (`docs/RETRIEVAL_EVALUATION.md`). Il deploy Docker shippava esattamente la configurazione bocciata. Ora il default è `0`, e il servizio `app` ha un `image:` esplicito (`ermes-knowledge:local`) invece del nome derivato dalla cartella.
- **Profilo "verified"** (`docker-compose.verified.yml`): risposta al limite dichiarato "l'astensione degrada a scala". Invece di continuare a cercare un segnale senza modello (quattro già misurati e scartati), il modello diventa un requisito: un servizio one-shot `ollama-pull` scarica `qwen3.5:4b` e `nomic-embed-text`, e `app` parte solo a pull completato con `ERMES_EVIDENCE_VERIFIER=1` e `local_ollama`. Le variabili `ERMES_EVIDENCE_VERIFIER*` e `ERMES_CONVERSATION_MEMORY` sono ora passate dal compose base (prima non erano impostabili in container).
- README: sezione Docker riscritta con comandi `bash`, riferimento al job CI e al profilo verified; la nota su "abstention degrades" rimanda al profilo.

Correzioni da una revisione esterna del codice (stesso giorno), verificate una per una prima di intervenire:

- **Ollama e OpenRouter irraggiungibili in container.** `config/integrations.py` leggeva `ERMES_OLLAMA_HOST`, `ERMES_OPENROUTER_API_KEY`, `ERMES_OPENROUTER_BASE_URL`; compose, `.env.example`, CI e test scrivono i nomi senza prefisso. In Docker Ollama restava a `localhost:11434` e la chiave OpenRouter non arrivava mai — invisibile perché senza modello la modalità `evidence_only` è comunque `healthy`. Ora si onorano entrambi i nomi (prefissato vince). `tests/test_compose_env_is_read.py` legge il blocco `environment` di `app` in `docker-compose.yml` e pretende che ogni nome sia letto da `config/` così com'è: il test precedente controllava solo `ERMES_*`.
- **Cookie di sessione mai `Secure` in Docker.** Il flag dipendeva dal bind (`0.0.0.0` → mai Secure) e `0.0.0.0` è ciò che compose imposta. Ora dipende dalla richiesta: HTTPS diretto o `X-Forwarded-Proto: https` dal proxy; `ERMES_COOKIE_SECURE=1|0` forza. `tests/test_session_cookie_secure.py`.
- **`.env` fuori dai backup e dall'artifact CI.** `core/backup_manager.py` includeva `.env` (password admin, chiavi provider, client secret OIDC) in un archivio non cifrato; `pre-deploy-backup` lo copiava in un artifact scaricabile per 30 giorni. `security/` resta nel backup, perché senza la chiave di firma l'audit ripristinato non è verificabile; RUNBOOK aggiornato.
- **Import di Knowledge Pack indurito.** Il nome file veniva dal manifest senza sanitizzazione; ogni membro del tar veniva letto in memoria senza limite; la rotta era l'unica con upload senza `rate_limited`. Ora: `sanitize_upload_name` sul nome (stesse regole di un upload), limite per membro (= `ERMES_ADMIN_MAX_UPLOAD_MB`), totale (×20) e numero (5000) controllati sull'intestazione **prima** di leggere, archivio scritto su disco a blocchi con cap, `Depends(rate_limited)`.
- **Documentazione allineata al codice.** `DESCRIZIONE_PROGETTO.md` dichiarava PBKDF2/Argon2 (è SHA-256 salato iterato), hash-chain (è HMAC per voce), `404` per ogni negazione (è `401`/`403`/`404` a seconda del caso) e il reranker neurale come componente attivo (è spento per misura). Versione unica `2.2.5` in `pyproject.toml`, `api/__init__.py`, `api/mcp_server.py`, `DESCRIZIONE_PROGETTO.md` (erano 2.1.0 / 2.2.4 / 2.2.6). Badge README "88 Pytest" (ne vengono raccolti 588+) sostituito da un badge che punta alla CI.
- `d3` e `@types/d3` rimossi dal frontend: nessun import in `src/`.

Colmati tre vuoti rispetto ai RAG open-source comparabili (Onyx, RAGFlow, Kotaemon):

- **OCR per PDF scansionati** (`core/ocr.py`). Il gancio precedente (`pytesseract` sulle immagini incorporate) non aveva dipendenza dichiarata, binario nel Dockerfile né test, e su molti PDF da scanner la pagina non è un'immagine estraibile: un documento scansionato veniva indicizzato con zero passaggi in silenzio. Ora ogni pagina senza livello testo viene rasterizzata (`pypdfium2`, nessuna dipendenza di sistema) e letta da Tesseract (`ita+eng`, nel Dockerfile). `ERMES_OCR_ENABLED/LANG/MAX_PAGES/DPI`; oltre il limite di pagine il salto è nel log; senza binario `/health` è `degraded` con la ragione. `tests/test_pdf_ocr.py` (motore sostituito, rasterizzazione reale).
- **Metriche RAGAS sul golden set** (`evaluation/ragas_report.py`): context precision/recall e MRR nella definizione di Es et al. 2023, più precisione dell'astensione e tasso di false astensioni, per confrontare Ermes con altri progetti. Shipped default, k=3: precision 0.792, recall 0.833, MRR 0.792, astensione 1.000. Faithfulness e answer relevancy dichiaratamente non misurate (nessuna generazione in evidence_only). `tests/test_ragas_report.py` verifica le formule a mano e che il run riproduca i fatti del README.
- **README**: la domanda "dov'è la ricerca vettoriale?" ha ora una risposta in cima, prima dei numeri, invece di lasciarla scoprire a chi legge.

Secondo blocco della stessa revisione, sempre verificato prima:

- **Postgres era rotto oltre lo schema, e i test lo nascondevano.** `PostgresBackend.transaction()` consegnava la connessione psycopg nuda a un centinaio di `connection.execute("... ?")` di `LibraryStore` scritti per sqlite3: psycopg rifiuta `?`. I tre test di parità a livello store passavano in CI perché il fixture impostava `ERMES_DATABASE_URL` *dopo* la costruzione di `cfg` (frozen) e apriva SQLite senza saperlo. Ora `transaction()` yielda `PostgresConnectionAdapter` (traduzione `?`→`%s` su `execute`/`executemany`, righe dict come promesso dalla docstring di `_connection`), `executemany` traduce anche nel backend (passava `None` e non toccava la query), `INTEGRITY_ERRORS` copre sqlite3 e psycopg, `LibraryStore(database_url=...)` esplicito, e il fixture **asserisce** `_is_postgres`. Due parity test nuovi percorrono add/replace/members/delete su Postgres reale in CI; `tests/test_postgres_adapter.py` verifica la traduzione senza server. Non provato in locale (nessun Postgres): la prova è la CI.
- **Argon2id per le password locali** (`argon2-cffi`), come la documentazione dichiarava da tempo. Gli hash SHA-256 salati esistenti restano validi e vengono riscritti al primo accesso riuscito (o da `ensure_default_admin`); utente inesistente → verifica di un hash fittizio per non rivelare il nome dal tempo di risposta. `tests/test_password_argon2.py`.
- **`/v1/...` senza rate limit**: le copie delle rotte non ereditavano `dependencies`, cioè `rate_limited`. Ora sì; test in `test_rate_limiting_applied.py`.
- **Cache di ricerca**: restituiva il riferimento interno (i chiamanti annotano i risultati sul posto → la seconda richiesta vedeva le annotazioni della prima) e non veniva invalidata da `replace_document_index` / `store_chunk_embeddings` (stesso numero di documenti, chunk diversi → citazioni vecchie fino alla scadenza). Ora copia profonda in uscita e invalidazione in entrambi. Test in `test_search_cache.py` e `test_library_store.py`.
- **Audit append sotto `FileLock`**, come users.json e api keys: due processi che scrivono insieme producevano righe intrecciate, cioè voci che non verificano.

CI resa un gate anche per ciò che finora era solo scritto:

- **E2E Playwright eseguiti davvero.** Esistevano da mesi con `test.skip(!PASSWORD)`: in CI nessuna istanza, nessuna password, sempre saltati. Ora girano dentro `compose-smoke` contro il container, dopo il caricamento del corpus demo, con trace caricate come artifact in caso di fallimento. Il primo run reale ha trovato un'asserzione invecchiata (testo di una card rimosso dalla UI) — corretta. 4/4 verdi anche in locale contro l'app nativa.
- **gitleaks** sull'intera history (job `secrets`, bloccante per il deploy) e **Trivy** sull'immagine appena costruita (advisory, come pip-audit e per la stessa ragione).

**Coda di indicizzazione locale** (`core/ingestion_worker.py`), senza broker: i job erano già persistiti e reclamati atomicamente, mancava la politica attorno. Ora: concorrenza limitata (`ERMES_INGESTION_WORKERS`, default 2 — prima cento upload erano cento parser in parallelo), retry con attesa per le sole cause transitorie (`ERMES_INGESTION_MAX_ATTEMPTS`, `ERMES_INGESTION_RETRY_SECONDS`; un documento illeggibile non viene riprovato), colonna `attempts` in `ingestion_jobs` (migrazione SQLite e Postgres), e recupero all'avvio dei job lasciati in `processing` da un crash — `recover_stale_ingestion_jobs` esisteva con "Startup calls this" nella docstring e non era chiamata da nessuno. Il contratto dello store (claim/finish/requeue) è quello che un worker separato userebbe. 5 test in `tests/test_ingestion_worker.py` (retry, no-retry, tetto tentativi, concorrenza, recupero).

Frontend:

- **Lint riattivato e in CI.** `npm run lint` esisteva ma non girava in CI e falliva con 2 errori reali (`ConnectorsTab`: funzioni usate in un effect prima della dichiarazione). `no-explicit-any` e `no-unused-vars` erano spente: i 23 `any` erano tutti `catch (err: any)` per leggere `.message` — sostituiti da `lib/errors.ts::errorMessage(unknown)`; le 8 variabili inutilizzate erano `catch (e)` vuoti. Ora entrambe le regole sono attive (nei test `any` resta lecito per i mock) e il lint è bloccante in CI.
- **Code splitting**: ogni tab è un chunk caricato alla prima visita (`React.lazy` + `Suspense`). Bundle iniziale da 301 KB a 187 KB.
- `window.open` con `noopener,noreferrer` sull'export biblioteca.
- **Primi test su `App`** (`src/__tests__/App.test.tsx`, 6): gate di autenticazione (login riuscito/rifiutato, `credentials: include`), parsing dello stream SSE con `ReadableStream` costruito a mano e spezzato a metà evento (status → citations → answer → done, stato ripulito a fine stream), cronologia limitata alle ultime tre domande dell'utente senza risposte, `Stop` che aborta la richiesta, errore HTTP che lascia un messaggio leggibile. Fino a oggi `App` aveva zero test e gli E2E che avrebbero coperto lo stesso percorso si auto-saltavano.

- **Motivo del feedback negativo → Knowledge Gaps.** Il pollice giù in chat apre quattro motivi (informazione mancante, fonte non pertinente, risposta poco chiara, altro); il motivo viaggia come `comment` del feedback, `get_knowledge_gaps` lo aggrega per domanda (deduplicato, vuoti ignorati) e il cruscotto lo mostra come chip accanto alla domanda. Test: backend (aggregazione e caso senza motivo), `ChatArea` (menu → POST con `comment`), e l'asserzione sul modal citazione aggiornata al nuovo testo "Copia estratto".

- **SSO nel browser, davvero** (`frontend/src/lib/oidc.ts`). Il bottone "Accedi con SSO" mostrava una notifica e si fermava: il backend verificava già firma, `iss` e `aud` dell'`id_token`, ma nessuno glielo consegnava. Ora: Authorization Code + PKCE (client pubblico, niente secret nel browser), discovery da `issuer`, `state` e `nonce` verificati prima di passare il token a `/api/auth/oidc/session`, codice rimosso dall'URL. 8 test unitari senza provider + 2 su `App` (avvio del flusso, ritorno dal provider senza mostrare il form).
- **Logout** (`Esci` nella sidebar): l'endpoint esisteva, la UI no. Chiude la sessione server, azzera lo stato client, aborta una risposta in corso.

Verificato e **non** corretto perché il claim non regge: lo streaming SSE non "sovrascrive i chunk" — il server manda un solo evento `answer` con la risposta completa (`api/libraries.py`), lo stream è di stati; `striprtf` assente da `requirements.txt` ha un fallback esplicito in `core/document_parser.py`. Rimandati (richiedono più di un giorno): adapter Postgres per le ~25 query via `_connection()` con `?` (oggi rotte su PG, confermato), migrazione ad Argon2, backup cifrati.

## 2026-09-12 — v2.2.4: Gestione UI Glossario Dinamico e UX Citazioni Avanzate

- **Pannello UI Glossario & Sinonimi Dinamici**: in [`frontend/src/components/settings/SynonymsSettingsPanel.tsx`](file:///c:/Progetti/ProgettoRAG_DEV/frontend/src/components/settings/SynonymsSettingsPanel.tsx) e integrato in [`SettingsTab.tsx`](file:///c:/Progetti/ProgettoRAG_DEV/frontend/src/components/settings/SettingsTab.tsx), introdotta la gestione visiva completa del glossario aziendale: conteggio metriche, visualizzazione a chip dei sinonimi personalizzati, modulo per l'inserimento di nuovi acronimi/espansioni per amministratori ed editor, eliminazione rapida con conferma e sezione collassabile per esplorare i termini predefiniti di sistema.
- **UX Dettaglio Citazione Avanzata**: in [`ChatArea.tsx`](file:///c:/Progetti/ProgettoRAG_DEV/frontend/src/components/chat/ChatArea.tsx), arricchito il modal di consultazione delle evidenze con:
  - Chiusura rapida tramite tasto `Escape` e click all'esterno dell'overlay;
  - Pulsante dedicato "Copia citazione" con feedback visivo (`Copiato!` con spunta verde);
  - Area di lettura ingrandita e scrollabile per estratti lunghi con backdrop blur.
- **Suite di Test Frontend Estesa**: aggiunti test unitari in `SynonymsSettingsPanel.test.tsx` e `ChatArea.test.tsx`, portando la suite frontend a 68/68 test Vitest superati e bundle Vite generato in meno di 2 secondi.

## 2026-09-12 — v2.2.3: Glossario Aziendale Dinamico e Sinonimi Personalizzati

- **Glossario Dinamico & Query Expansion Personalizzata**: `core/query_expander.py` è stato potenziato per supportare dizionari personalizzati persistiti su file JSON (`config/synonyms.json`, configurabile tramite `ERMES_SYNONYMS_FILE`). I sinonimi personalizzati dell'organizzazione/biblioteca vengono uniti a quelli base con priorità e deduplicazione automatica, consentendo di comprendere all'istante acronimi e terminologie proprietarie o gergali (es. *TFR, CCNL, DDT, CIG, CUP, GDPR, DVR, smart working*).
- **Matching a frasi multi-parola e Ordinamento per Lunghezza**: la pipeline di espansione valuta i termini ordinandoli per lunghezza decrescente, garantendo che le locuzioni composte (es. "lavoro agile", "conto corrente", "documento di trasporto") vengano espanse correttamente prima dei singoli termini che le compongono.
- **Concorrenza multi-processo atomica & Cache su mtime**: la lettura e scrittura del glossario aziendale sono protette da `FileLock` con percorsi canonici e scrittura atomica (tempfile + replace). Il caricamento sfrutta una cache in memoria invalidata automaticamente solo in caso di modifica del timestamp `mtime` su disco, garantendo zero overhead in fase di query.
- **API REST Amministrativa Protetta (`/api/synonyms`)**: aggiunto il router `api/synonyms.py` con endpoint `GET /api/synonyms` (lettura per utenti autenticati), `POST /api/synonyms` (creazione/aggiornamento per ruoli `editor` e `admin`) e `DELETE /api/synonyms/{term}` con validazione rigorosa e audit logging tracciato nel log di sicurezza.
- **Suite di Test Dedicata**: aggiunti test completi in `tests/test_query_expander.py` e `tests/test_synonyms_api.py` a copertura di tutte le operazioni CRUD, persistenza, lock concorrente e controlli di ruolo RBAC.

## 2026-09-12 — v2.2.2: Esportazione Chat in Markdown e Filtri Documenti Avanzati

- **Esportazione conversazioni in Markdown**: in `ChatArea.tsx` aggiunto il pulsante "Esporta .md" che genera e scarica istantaneamente l'intera cronologia della conversazione con intestazione della biblioteca, data/ora, domande, risposte formattate e citazioni/passaggi verificati.
- **Pulsante Nuova Chat**: aggiunta l'azione rapida "Nuova chat" che consente all'utente di azzerare la cronologia della sessione attiva e avviare una nuova consultazione senza dover ricaricare la pagina web.
- **Filtri avanzati documenti per formato e nome**: in `DocumentsTab.tsx` aggiunta una toolbar di filtraggio rapido per estensione (`Tutti`, `PDF`, `DOCX`, `PPTX`, `XLSX`, `TXT`, `MD`) e campo di ricerca istantaneo per nome file, facilitando l'esplorazione e la gestione di biblioteche con decine o centinaia di documenti.

## 2026-09-12 — v2.2.1: Robustezza concorrenza governance e UX Copia Rapida

- **Locking multi-processo e container-safety in Governance**: `core/governance.py` ora utilizza un gestore `_get_file_lock` con caching singleton per percorso canonico, garantendo rientranza per-thread e mutua esclusione atomica fra più worker (es. `uvicorn --workers N`). Il lock di `api_keys.json` è stato spostato dalla directory sorgente `core/` alla directory dati scrivibile `cfg.SECURITY_DIR`, eliminando errori in container con filesystem root in sola lettura (`read-only rootfs`). Esteso il FileLock a `users.json` e `oidc_group_mappings.json`.
- **UX Copia Risposta negli appunti**: in `ChatArea.tsx` aggiunto il pulsante "Copia" accanto ai controlli di feedback delle risposte dell'assistente, con feedback visivo temporaneo ("Copiato!" con icona di spunta verde) per esportare agilmente le risposte documentate verso ticket, email e documentazione.
- **Test suite di concorrenza**: aggiunti test in `tests/test_governance.py` per verificare rientranza e persistenza dei lock.

## 2026-09-12 — v2.2.0: Streaming SSE end-to-end, verifier parallelo e ottimizzazioni di latenza

- **Streaming SSE end-to-end**: aggiunto l'endpoint `POST /api/libraries/{id}/ask/stream` basato su Server-Sent Events (`text/event-stream`). L'interfaccia React consuma lo stream e mostra in tempo reale le fasi intermedie ("Ricerca evidenze nei documenti…", "Verifica passaggi con il modello…", "Composizione della risposta…") prima di far comparire subito le citazioni e il testo, eliminando la percezione di attesa statica.
- **Verifica evidenze concorrente**: `core/evidence_verifier.py` valuta i passaggi candidati in parallelo tramite `ThreadPoolExecutor`, abbattendo i tempi del 60-70% quando ci sono più citazioni candidate pur mantenendo la compatibilità fail-open, l'ordine di pertinenza, la quarantena e i filtri PII.
- **Connection pooling HTTP**: `core/evidence_assistant.py` e `core/evidence_verifier.py` riutilizzano un client `httpx.Client` thread-safe con pooling delle connessioni per chiamate Ollama e OpenRouter, riducendo l'overhead di hand-shake TCP ripetuto.
- **Repository Hygiene & Allineamento**: aggiornato `docker-compose.yml` rimuovendo commenti obsoleti e documentando le integrazioni webhook chat native (Slack/Teams/Telegram); organizzati gli script di rete Windows sotto `scripts/windows/` e spostato `crea_config.ps1` legacy in `legacy_winsarp/scripts/`.
- **Frontend polish**: risolto il warning di input controllato React nel test Vitest di `Input.tsx`; la suite frontend passa a 64 test con zero warning.

## 2026-09-07 — v2.1.0: RAG più preciso, multi-backend, sicurezza SSO e osservabilità

- **Config modulare**: `config.py` monolite diviso nel package `config/` (server, security, storage, integrations, rag) con parità completa degli attributi verificata via confronto automatico. Durante la migrazione trovate e corrette tre regressioni silenziose, la più grave: **il `.env` non veniva più caricato** (in produzione si sarebbe perso `ADMIN_PASSWORD` e i segreti Slack/Teams/Telegram senza accorgersene).
- **Reranker neurale (cross-encoder)**: `ms-marco-MiniLM-L-6-v2` valuta (query, passaggio) insieme; blend 60/40 col reranker lessicale esistente, lazy-load thread-safe e fallback trasparente se `sentence-transformers` non è installato (`pip install .[neural]`). Discriminazione reale misurata: 0.999 sull'estratto pertinente, 0.0 su quello fuori tema.
- **Parser PowerPoint**: `.pptx` supportato con parsing OOXML diretto (zero nuove dipendenze, stessi guard di sicurezza del parser xlsx: DTD rifiutati, limiti zip). Ogni slide diventa un'unità citabile con locator "Slide N". Whitelist dei connettori cartella/NAS allineata agli upload (ora anche `.md/.xlsx/.pptx/.csv/.rtf`), con test end-to-end di un xlsx importato da cartella fino a "ready".
- **OIDC → ACL**: i gruppi SSO possono concedere ruoli viewer/editor sulle biblioteche via mapping amministrabile (`/api/admin/oidc/group-mappings`, con audit log). La membership diretta vince sempre sui gruppi; i gruppi non possono mai dare admin. Un utente vede anche le biblioteche raggiungibili solo via gruppo (scoperta SSO).
- **Fix di sicurezza nella cache di ricerca**: la cache era condivisa per `(library_id, query)` a prescindere dall'utente — con ACL attive chi vedeva di più poteva "servire" risultati a chi vede di meno. Ora lo scope è per utente.
- **Dual-backend SQLite/PostgreSQL**: `ERMES_DATABASE_URL` commuta il backend (psycopg 3, jsonb per gli embedding, tsvector per il full-text, `FOR UPDATE SKIP LOCKED` sui job). SQLite resta il default: i deploy esistenti non cambiano nulla. Piano di migrazione completo in [docs/POSTGRES_MIGRATION_PLAN.md](docs/POSTGRES_MIGRATION_PLAN.md), parità verificata con test live (auto-skip senza DB).
- **Monitoring Prometheus**: metriche native (latenze, domande RAG, modalità rerank, esiti ingestion) su `/metrics`, che ora **richiede autenticazione** — prima era pubblico ed esponeva percorsi, errori e latenze.
- **Load testing**: scenario Locust (search/listing/upload con utenti auto-registrati) e benchmark pytest: ricerca ~70ms, 14.5 q/s single-thread, 28 q/s concorrenti con 0 errori, ~800 chunk/s in insert.
- **UX**: wizard di onboarding al primo accesso; card connettore Microsoft 365 (SharePoint/OneDrive) con test connessione e sync; barra di stato del Folder Watcher con sync globale. Fix: il selettore "Biblioteca di destinazione" era sempre vuoto (leggiva `data.libraries` invece di `data.items`).
- **Gate di qualità riportato a zero**: 169 violazioni ruff → 0. Nel passaggio trovati due bug reali: il locustfile era sintatticamente rotto (mai visto da pytest) e `core/governance.py` conteneva un blocco OIDC duplicato (la seconda definizione oscurava la prima; rimosso il dead code).

## 2026-09-03 — Integrazioni Enterprise & Agenti AI

- **Connettore Cartelle NAS / Locali (`LocalFolderConnector`)**: implementata la scansione ed ingestion automatica da percorsi locali e mount di rete SMB/NFS (`core/connectors/local_folder.py`), con dispatching dinamico su `POST /api/connectors/test` e `POST /api/connectors/sync`.
- **Server MCP (Model Context Protocol)**: esposta l'interfaccia MCP nativa (`api/mcp_server.py`) su `/api/mcp/rpc` (JSON-RPC 2.0) e `/api/mcp/tools` (REST), consentendo a Claude Desktop, Cursor, Antigravity e LangChain di interrogare Ermes in modalità evidence-first.
- **Gateway Webhook per Automazioni (n8n / Zapier / Make)**: implementati gli endpoint `/api/integrations/automation/ask` e `/api/integrations/automation/ingest` in `api/webhook_gateway.py` con autenticazione via API Key.
- **Adattatore Telegram Bot Webhook**: aggiunto l'endpoint `/api/integrations/telegram` in `api/chat_webhooks.py` con verifica del token segreto `X-Telegram-Bot-Api-Secret-Token` per risposte RAG su Telegram.
- **Nuova Scheda UI React "Connettori & Automazioni"**: sviluppato il componente [`frontend/src/components/connectors/ConnectorsTab.tsx`](file:///c:/Progetti/ProgettoRAG_DEV/frontend/src/components/connectors/ConnectorsTab.tsx) per testare e sincronizzare cartelle NAS, avviare lo scraper web, visualizzare snippet JSON per MCP Server ed esempi per n8n.
- **Suite di Test**: 248 test backend (`pytest`) e 62 test frontend (`vitest`) superati con esito 100% positivo.

## 2026-08-20

- **Revisione sistematica del codice** ([docs/CODE_REVIEW.md](docs/CODE_REVIEW.md)): partita da tre bug nello script di avvio che si sono rivelati la stessa causa radice — il *fallimento silenzioso*, cioè un controllo che riporta successo senza aver verificato nulla. Cercata quella categoria in tutto il repository invece dei tre casi singoli.
- **Trovata e corretta una build Docker rotta per chiunque cloni il repository**: `COPY data/ ./data/` copiava una cartella non tracciata (contiene solo il database runtime). Funzionava in locale, falliva su clone pulito.
- **Rimosso `api.py` dalla root**: codice irraggiungibile, non uno shim come valutato in precedenza — in CPython il package `api/` vince sempre sul modulo omonimo. Valutazione precedente corretta agli atti nella roadmap.
- **Rimosso `openapi.json` versionato**: documentava 44 endpoint inesistenti e ne ometteva 38 reali. Il contratto vero è servito a runtime su `/openapi.json`.
- **Rimosse 1.389 righe di codice morto** in `core/` e i 25 test che lo coprivano: il 14% della suite verificava codice che il prodotto non esegue mai.
- **Corretti due gate di CI che non potevano fallire** (`mypy || true`, `bandit || true`) e le loro esclusioni verso cartelle non più esistenti.
- **Riscritta `DEVELOPER.md`**, che descriveva l'architettura WinSarp; spostati sotto `legacy_winsarp/docs/` quattro documenti WinSarp che vivevano in root e in `docs/`.
- **Corretti gli script di collegamento sul Desktop**, che non creavano alcun collegamento e puntavano a percorsi hardcoded errati.
- **Chiusa una lacuna in `.gitignore`**: la regola `*.env` matcha solo i file che *finiscono* in `.env`, quindi un `.env.test` restava tracciabile. Sostituita con `.env.*` (più `!.env.example`) e aggiunta una regola per le scansioni PDF personali.
- File tracciati in root da 37 a 18. Suite verde a ogni passo, 92 route invariate.

- **Trovato e risolto un bug reale di isolamento tra test** (`tests/test_e2e_api.py`): un `importlib.reload(config)` a tempo di collezione lasciava alcuni moduli agganciati alla config vecchia a seconda dell'ordine di raccolta dei test, causando un fallimento intermittente. Corretto mutando il singleton esistente dentro una fixture a tempo di esecuzione, con ripristino garantito. Verificato 3 volte di fila: 171 test passati, 0 falliti.
- Chiusa la lacuna di test su `core/backup_manager.py`: aggiunti test su restore (dry-run e reale), scrittura atomica, ed exclusione dei metadati, più un test di concorrenza reale su `_backup_lock`.
- Favicon collegato: esisteva già un logo brandizzato (`frontend/public/favicon.svg`) mai wireato — l'app usava un'emoji placeholder.
- **Recuperati file persi per un incidente durante la pulizia della cronologia git**: un'operazione di `git stash` + riscrittura della history + garbage collection ha temporaneamente reso irraggiungibili alcuni file non tracciati (`Ermes.ico`, `Ermes.png`, la scansione PDF personale, alcuni documenti legacy). Recuperati integralmente da un commit "orfano" rimasto nel repository prima che venisse definitivamente rimosso.
- Riorganizzati tre documenti legacy WinSarp trovati in root (`REQUIREMENTS_MATRIX.md`, `GO_LIVE_CHECKLIST.md`, `README_ENTERPRISE.md`) sotto `legacy_winsarp/`.

## 2026-08-19 — sessione principale

- **Isolamento completo di WinSarp**: l'intero motore formule legacy (core, UI Streamlit, endpoint, script, dati di valutazione, ~45 file di test) spostato sotto `legacy_winsarp/`, dietro un flag esplicito (`ENABLE_LEGACY_WINSARP`, spento di default). Nessuna cancellazione.
- **Commit del prodotto reale per la prima volta**: gran parte del backend (`api/`, moduli nuovi di `core/`) e l'intero frontend React non erano mai stati committati — messi in sicurezza dopo revisione, non alla cieca.
- **Trovati e corretti due bug che avrebbero rotto CI/Docker**: un `COPY` nel Dockerfile puntava a una cartella spostata; la CI usava un flag pytest senza la dipendenza corrispondente.
- **Scansione completa della cronologia git per segreti**: nessuna credenziale reale trovata. Trovato un documento di lavoro riservato committato dal primo commit — rimosso dall'intera cronologia (non solo cancellato), con force-push.
- **Retrieval misurato onestamente**: golden set espanso da 16 a 27 query (dirette, parafrasate, di astensione); numeri pubblicati con i limiti espliciti, non solo il caso migliore.
- **Aggiunto il recupero del documento originale in chat** (non solo dalla tab documenti), con audit log su ogni download.
- **Corpus demo con due biblioteche**, per dimostrare dal vivo l'isolamento tra biblioteche — non solo dichiararlo.
- Licenza MIT, one-pager di presentazione, guardia di regressione che blocca la CI se un endpoint viene spedito senza autenticazione.

## Prima del 2026-08-19

Vedi `git log` per la cronologia del progetto prima di questo lavoro di consolidamento (introduzione dell'HybridRetriever, upgrade modelli, framework di valutazione iniziale).
