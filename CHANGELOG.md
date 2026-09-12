# Changelog

Registro leggibile del lavoro su questo progetto. Per il dettaglio fase-per-fase con motivazioni, vedi [docs/ROADMAP_V2.md](docs/ROADMAP_V2.md); per i finding tecnici completi, [docs/AUDIT_2026-08-19.md](docs/AUDIT_2026-08-19.md) e [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md); per il registro operativo delle sessioni, [docs/WORK_PROGRESS.md](docs/WORK_PROGRESS.md).

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
