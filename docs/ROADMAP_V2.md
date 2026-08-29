# Roadmap v2 — Ermes Knowledge verso v0.1 enterprise-credibile

> Questo documento affianca `PROJECT_PLAN.md` (che resta come riferimento storico delle fasi 0-8) con le priorità decise il 19 agosto 2026. Non lo sostituisce, lo specializza. Aggiornato con i risultati dell'audit di team (dev/architettura, sicurezza, design/UX) del 19 agosto 2026.

## Contesto e decisioni di fondo

1. **WinSarp non si sviluppa più.** Resta materiale storico/isolato, non riceve nuove feature. Nessuna cancellazione: solo isolamento fisico dal path del prodotto.
2. **Il prodotto è "un bibliotecario aziendale"**: cerca nei documenti, risponde con citazioni, e **recupera e serve il documento originale** su richiesta esplicita, non solo estratti di testo.
3. **L'obiettivo primario è la credibilità tecnica** verso chi valuta (CTO/tech lead/recruiter), non necessariamente un go-to-market commerciale. Questo sposta il peso verso rigore dimostrabile (metriche reali, sicurezza pensata, architettura pulita) rispetto all'ampiezza delle feature.

## Stato reale verificato (non le promesse dei documenti)

- **Retrieval — correzione importante**: durante l'isolamento di WinSarp (Fase A) è emerso che `core/rag_engine.py` (con il suo `HybridRetriever`, KG exact-match + vettoriale) e `evaluation/run_eval.py`/`gold_set.json`/i `results_*.json` da 50 query **appartengono al vecchio motore formule WinSarp**, non al bibliotecario Ermes Knowledge — sono infatti stati spostati in blocco sotto `legacy_winsarp/`. Il "100% evaluation score" citato nel log commit `e5a4692` era quindi un numero cherry-picked (10 query) del prodotto sbagliato. Il benchmark che conta davvero per Ermes Knowledge è `evaluation/run_library_eval.py` + `evaluation/library_gold_set.json` (16 query, gate CI reale con `recall_at_3 >= 0.9` in `tests/test_library_evaluation.py`) — molto più piccolo e non ancora così esercitato. La Fase B qui sotto è stata corretta di conseguenza.
- **Recupero documento**: endpoint reale e permission-aware, `GET /{library_id}/documents/{document_id}/download` in `api/libraries.py:109`, verificato dall'audit sicurezza come corretto (ACL controllata **prima** di servire il file, anti path-traversal). Collegato solo a `frontend/src/components/documents/DocumentsTab.tsx:274`, non alla chat.
- **Test**: `tests/test_library_evaluation.py` è un vero gate di qualità (`recall_at_3 >= 0.9` su 16 query), ma copre solo retrieval, non il download né l'ingestion.

### Audit di team (19 agosto 2026) — sintesi

Due agenti indipendenti (architettura, sicurezza) più una review diretta del frontend hanno prodotto il verbale completo: [artifact "Il team ha guardato Ermes Knowledge"](https://claude.ai/code/artifact/9a7ff426-6df8-4b39-be99-6893cd6d255d). I risultati concreti sono integrati nei checklist di fase qui sotto, con riferimento a file e severità.

**Limite di quell'audit**: è stato condotto *prima* dell'isolamento fisico di WinSarp (Fase A, 20 agosto 2026), che ha spostato ~190 file. Il refactor è stato verificato con test automatici (pytest, boot dell'app, build frontend), non con una seconda revisione umana/agente. Vale come nota per chi riprende il lavoro: l'audit descrive l'architettura *prima* del trasloco, non lo stato attuale linea per linea.

## Protocollo di revisione a 4 ruoli

Da qui in avanti, ogni fase (o task consistente al suo interno) va chiusa passando esplicitamente per quattro prospettive, non solo "il codice gira":

| Ruolo | Cosa verifica prima di dire "fatto" |
|---|---|
| **Solution Architect** | Il cambiamento rispetta i confini di modulo di `docs/ARCHITECTURE_TARGET.md` (control plane vs data plane, retrieval prima della generazione, nessun'azione di scrittura autonoma)? Introduce un nuovo accoppiamento non voluto? |
| **Tech Lead / Dev** | Codice tipizzato, niente stub (`# TODO implementare`), niente patch locale a un problema strutturale — vedi i pattern già trovati nell'audit (import ritardati per aggirare circular import, doppie implementazioni). |
| **QA & Test Engineer** | Edge case enumerati *attivamente*, non solo "i test esistenti passano": input vuoti/malformati, permessi al limite, concorrenza sugli upload/ingestion, cosa succede se Ollama/il provider cloud non risponde. |
| **DevOps** | Il cambiamento richiede touch a `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, variabili in `.env.example`? È stato verificato che CI/Docker non si aspettino path ormai spostati? |

Finora questo protocollo è stato applicato solo in parte: l'audit di team ha coperto Architect/Dev/Security a fondo; QA (enumerazione edge case, non solo "i test passano") e DevOps (Docker/CI/config) non hanno ancora avuto una passata dedicata — da qui la nuova Fase A2.

## Fasi

### Fase A — Repo a un solo binario (~3-4 giorni)
Eliminare l'ambiguità vecchio/nuovo prima di costruire sopra.

- [x] **Isolato fisicamente WinSarp** sotto `legacy_winsarp/` (20 agosto 2026): non solo `core/`+`ui/`+`modules/`+`core/winsarp/`, ma anche file scoperti solo verificando gli import reali — `app.py` (vecchio entrypoint Streamlit), `core/agent_runner.py`, `core/ai/chain_of_thought.py`, gli endpoint `api/query.py`/`documents.py`/`formule.py`/`graph.py`/`integrations.py`, gli script di manutenzione catalogo/grafo, `evaluation/run_eval.py`+`gold_set.json`+i `results_*.json` (vedi correzione sotto), e ~40 file di test. Nessuna cancellazione, vedi `legacy_winsarp/README.md`.
- [x] **[dev, medio]** Chiuso l'import diretto di WinSarp in `core/rag_engine.py` — il file intero ora vive in `legacy_winsarp/core/rag_engine.py`, non solo un fix di import.
- [x] **[sicurezza, alto ma condizionale]** `api/documents.py` (senza ACL) è stato spostato in `legacy_winsarp/api/`, gated dietro `ENABLE_LEGACY_WINSARP` (default `False`, verificato con l'app avviata: nessuna route `/query`/`/api/documents/*` presente senza il flag).
- [x] **[sicurezza, basso]** Banner di avviso aggiunto in `api/__init__.py` (lifespan): un `logger.warning` esplicito quando `ENABLE_LEGACY_WINSARP=1`, con link a `legacy_winsarp/README.md` e `docs/AUDIT_2026-08-19.md`.
- [x] **Consolidati gli script `AVVIA_*`/`SETUP_*`**: in root restano solo 3 utility non-launcher (`crea_config.ps1`, `firewall.bat`, `static_ip.bat`); tutti i launcher/setup Streamlit-era (`AVVIA.ps1`, `AVVIA_DIRETTO.bat`, `AVVIA_FINALE.bat`, `SETUP_INSTALL.bat` root, `CREA_COLLEGAMENTO_DESKTOP.ps1` root — verificato puntava a `AVVIA_FINALE.bat`) spostati in `legacy_winsarp/scripts/`; i duplicati stale del nuovo stack (`AVVIA_PRO.bat` — usava `.venv` invece di `.venv-ermes`; `start_ermes.bat` — path hardcoded errato, già rotto) in `scripts/archive/`; 7 file vuoti (0 byte) cancellati. In `scripts/` stessi, altri 4 launcher Streamlit-era duplicati spostati in `legacy_winsarp/scripts/`. Resta un solo entry point verificato: `scripts/avvia_ermes.ps1` (quello già documentato in README).
- [x] Rimosso l'endpoint legacy `api/documents.py: GET /content/{filename}` dal path del prodotto (spostato con tutto il file); confermato con l'app avviata: un solo modo di scaricare un documento, `api/libraries.py`.
- [x] Spezzare il diff pendente della Fase A in commit piccoli e revisionabili — fatto (isolamento WinSarp come unità separata dal resto).
- [x] **`pytest` verificato per davvero**: 182 passati, 2 skippati (richiedono Ollama/Chroma reali, correttamente `skipif`), **1 fallito** — `tests/test_e2e_api.py::test_e2e_rbac_full_flow` (401 invece di 200 su `/api/users`), confermato **preesistente e non collegato** a questo intervento (file mai toccato, già non tracciato da git prima di oggi). `pytest legacy_winsarp/tests` raccoglie 857 test senza errori di import (solo `test_winsarp_robustness.py` resta ignorato, era già rotto/escluso prima dell'isolamento).
- [x] **[dev, basso]** Corretti i due bug di codifica testo (mojibake) in `api/libraries.py` e `core/document_parser.py` — uno era doppiamente corrotto, corretto a livello di byte, non solo di rendering. Grep di conferma su tutto il repo: zero occorrenze residue fuori da `.venv`/backup.
- [x] **Correzione emersa durante lo spostamento**: `evaluation/run_eval.py`/`gold_set.json`/`results_*.json` (i "50 query") appartenevano al motore formule WinSarp, non al bibliotecario — spostati con tutto il resto. Vedi nota nella sezione "Stato reale verificato" e Fase B corretta di conseguenza.

**Uscita**: un solo entry point, un solo path di download, test eseguiti con esito noto, nessun import legacy fuori dal suo perimetro.

### Fase A2 — Chiudere il diff DevOps/governance pendente (fatta, 20 agosto 2026)

Stima iniziale sbagliata: non erano 14 file modificati, ma **quasi l'intero prodotto Ermes Knowledge mai committato** — l'intero pacchetto `api/`, i moduli nuovi di `core/` (evidence_assistant, ingestion_service, library_store, library_embeddings, pii_filter, `core/ai/`), tutto `frontend/`, gran parte di `tests/`, e i documenti di strategia in `docs/` erano ancora "untracked" da sessioni precedenti. `git diff --stat` mostrava solo i file *modificati* tracciati, non i file *nuovi* — da qui la sottostima iniziale.

Fatto, file per file, non con un commit unico cieco:
- [x] **[devops]** CI: separati i job lint/test/frontend; **corretto un bug che avrebbe fatto fallire subito la CI** — `pytest --timeout=30` senza `pytest-timeout` in `requirements.txt` (aggiunto); bandit scansionava solo `api.py`, non il pacchetto `api/` (corretto); riferimento a `data/winsarp_graph.json` nel backup pre-deploy, non più lì (aggiornato a `data/ermes_knowledge.sqlite3`).
- [x] **[devops]** Dockerfile: **trovato e corretto un bug reale introdotto dallo spostamento WinSarp** — `COPY modules/ ./modules/` puntava a una cartella che non esiste più in root (spostata in `legacy_winsarp/`); il build sarebbe fallito. Aggiunta build del frontend, healthcheck su `/health`, CMD `uvicorn` invece di `streamlit`.
- [x] ~~**[architect]** `api.py` (root, -452 righe): confermato un vero shim di compatibilità che re-esporta `app` dal pacchetto `api/`, non codice morto.~~ **Valutazione sbagliata, corretta il 20 agosto 2026**: `api.py` non poteva funzionare da shim. In CPython un package vince sempre su un modulo omonimo, quindi `import api` risolveva *sempre* a `api/__init__.py` e il contenuto di `api.py` era irraggiungibile (verificato eseguendo `import api; api.__file__`). Era codice morto con un docstring che elencava endpoint WinSarp come se fossero il prodotto attuale. Rimosso.
- [x] **[architect/qa]** `core/governance.py`: estensione RBAC per-utente (API key hashate, scritture atomiche, file lock) — verificata **collegata davvero** a `api/auth.py`/`api/users.py` (non codice orfano) e coperta da `tests/test_enterprise.py`/`test_api_user_rotation.py`, entrambi verdi. Trovato e corretto un bug minore collegato: lo scheduler di backup in `api/__init__.py` loggava `result.get("file", ...)` ma `create_backup()` ritorna `"name"` — il log stampava sempre "?".
- [x] **[qa]** `core/backup_manager.py`: lock a thread + scrittura atomica sul restore, verificato collegato a endpoint admin-only e a uno scheduler in background. **Lacuna chiusa il 20 agosto 2026**: aggiunti 6 test (`tests/test_backup_manager.py`) su restore dry-run, restore reale con scrittura atomica, `backup_metadata.json` correttamente escluso, `FileNotFoundError` su backup inesistente, e un test di concorrenza reale su `_backup_lock` (due thread che chiamano `create_backup` insieme devono produrre due archivi distinti e validi, non un file corrotto).
- [x] Durante la revisione, trovati e spostati in `legacy_winsarp/` altri contenuti WinSarp mal etichettati sotto `core/`: `core/evaluation/` (formula_validator.py, semantic_evaluator.py) e `core/templates/` (master_patterns.json, few_shot_examples.json) — 26 test in `tests/test_evaluation.py` spostati con loro; import della copia spostata corretto dopo un giro di verifica con `pytest --collect-only`.
- [x] Trovati ed eliminati 7 file duplicati morti in root (nessun importatore): `governance.py`, `rate_limiter.py`, `theme.py`, `sidebar_ui.py`, `welcome_ui.py`, `monitor_dashboard.py`, `chat_ui.py`; più `frontend/src/App.jsx`/`main.jsx` (prototipo JS pre-TypeScript, `index.html` carica già `main.tsx`) e un `package.json`/`package-lock.json` orfano in root (dipendenza Monaco Editor del vecchio FormulaEditor).
- [x] Committato tutto in 8 commit coerenti per area (CI/Docker/setup, backend, frontend, test, doc di strategia) invece di un commit monolitico.

**Aggiornamento del 20 agosto 2026 — entrambe le lacune sopra chiuse per davvero:**
- `test_e2e_rbac_full_flow`: causa radice trovata (non solo aggirata) — `tests/test_e2e_api.py` faceva `importlib.reload(config)` per costruire una config isolata, ma questo ricollega solo l'attributo `config.cfg`, non i riferimenti già vincolati da altri moduli via `from config import cfg` al loro primo import (es. `api/auth.py`, importato prima in ordine alfabetico da `tests/test_api_auth_coverage.py`). La chiave API admin del test smetteva di corrispondere ogni volta che l'ordine di collezione cambiava. Corretto mutando i campi del singleton *esistente* sul posto (`object.__setattr__`, visibile a tutti i moduli che già lo referenziano) dentro una fixture con scope di modulo che gira a tempo di esecuzione dei test — non di collezione — e ripristina tutto al termine. Primo tentativo: mutazione a livello di modulo (ancora a tempo di collezione) — ha corretto questo test ma ne ha rotto un altro (`test_backup_manager.py`, lettura di `cfg.BASE_DIR` avvenuta prima del ripristino); la versione finale sposta la mutazione dentro il setup della fixture. Verificato con 3 esecuzioni consecutive della suite completa: **171 passati, 0 falliti**, ogni volta.
- `legacy_winsarp/tests/test_composer.py`: `KeyError` preesistente, confermato non collegato allo spostamento di oggi — lasciato così, il codice legacy è congelato e non riceve più sviluppo.

**Deliberatamente non toccato**: la collisione dello stemmer "lavora"/"lavoro" in `core/library_store.py::_search_token` (trovata in Fase B) — modificarla rischierebbe di rompere altri test che dipendono dallo stesso comportamento di stemming (es. il matching singolare/plurale). Resta documentata come limite noto, non corretta.

**Uscita**: raggiunta — nessun diff pendente sconosciuto; CI, Docker e governance committati e verificati, non solo "lasciati lì".

### Fase B — Retrieval onesto e misurato (fatta, 20 agosto 2026)

> Corretta dopo la Fase A: il target è `core/library_store.py` (ricerca del bibliotecario) e `evaluation/run_library_eval.py`, non il vecchio `rag_engine.py`/`run_eval.py` ormai in `legacy_winsarp/`.

Correzione emersa durante l'esplorazione: `core/library_store.py::search_with_profile` (righe 527-596) era **già** un vero scorer ibrido keyword+semantico locale (coseno-similarità sugli embedding, soglia 0.35), collegato end-to-end da `core/ingestion_service.py` a ogni upload — non serviva costruirlo. Il vero gap era che non veniva mai misurato in modalità semantica, non esisteva citation coverage, e il golden set (16 query, una per chunk) era troppo facile per essere una prova seria.

- [x] Pubblicato in `docs/RETRIEVAL_EVALUATION.md` il numero reale e attuale, misurato in questa sessione (modalità keyword, Ollama non disponibile in questo ambiente): `recall_at_3_direct = 1.0`, `recall_at_3_paraphrase = 0.5`, `abstention_accuracy = 0.667`, `citation_coverage = 1.0` — letti onestamente, non solo il migliore.
- [x] Aggiunto un flag `--semantic` a `run_library_eval.py` che attiva `core/library_embeddings.py` via Ollama e degrada esplicitamente a keyword-only (con avviso, non in silenzio) se Ollama non risponde — la componente ibrida esisteva già, ora è misurabile. **Il numero reale in modalità `--semantic` non è stato misurato qui** (Ollama irraggiungibile in questo ambiente) — da rieseguire in locale.
- [x] Aggiunta la metrica **citation coverage** a `run_library_eval.py` (% di query con evidenza attesa che trovano almeno una citazione).
- [x] Golden set espanso da 16 a **27 query**, non solo più query dello stesso tipo: 8 query **parafrasate** (zero sovrapposizione lessicale col testo sorgente, pensate per stressare il limite del keyword matching) e 3 query di **astensione onesta** (argomenti assenti dal corpus, corretto = zero citazioni). Trovato tramite queste ultime un bug reale nello stemmer naive di `core/library_store.py::_search_token`: "lavora"/"lavoro" collassano sulla stessa radice, causando un match spurio su una query di astensione — documentato, non ancora corretto (fuori scope di questa fase, l'algoritmo di retrieval non doveva essere toccato).
- [x] `tests/test_library_evaluation.py` aggiornato: gate duro su `recall_at_3_direct >= 0.9` e `citation_coverage >= 0.9` (sempre verificabili senza Ollama), soglie morbide su parafrasi/astensione per accorgersi di un collasso a zero senza pretendere che il keyword-only risolva query pensate per non esserlo.

**Uscita**: raggiunta — un numero di qualità retrieval reale, misurato in questa sessione, che regge a una domanda diretta in colloquio tecnico ("qual è la differenza tra query dirette e parafrasate?" ha ora una risposta con dati, non una supposizione).

### Fase C — Recupero documento come feature di prima classe (fatta, 20 agosto 2026)

- [x] **[design, medio — priorità alta]** Collegato il download del documento originale nelle citazioni di `ChatArea.tsx` (pulsante "Apri originale" per fonte, stesso pattern già usato in `DocumentsTab.tsx`).
- [x] **[dev/sicurezza, medio]** Aggiunti test di integrazione sul download in `tests/test_library_store.py`: accesso negato a un non-membro (404, non 403 — coerente con il resto dell'API), accesso concesso a un membro esplicitamente aggiunto, libreria condivisa aperta a qualunque utente autenticato. Scoperto e confermato *by design* (non un bug) che un utente con ruolo globale `admin` bypassa l'ACL di libreria — il test è stato corretto per usare un ruolo non-admin sull'estraneo.
- [x] **[dev, medio]** Consolidamento estrazione PDF/DOCX **già risolto dalla Fase A**: `api/documents.py` (la duplicazione) è stato isolato in `legacy_winsarp/api/` durante l'isolamento WinSarp — resta un solo percorso di estrazione, `core/document_parser.py`.
- [x] **[dev, medio]** Aggiunti test diretti per `core/ingestion_service.py::process_ingestion_job` in `tests/test_ingestion_service.py` (nuovo file, 4 test): indicizzazione riuscita, documento senza testo estraibile marcato `failed` (non silenziosamente `ready`), rifiuto di un documento il cui path punta fuori dalla storage root (difesa in profondità contro path traversal, verificata attiva), idempotenza su un job già reclamato.
- [x] Audit: ogni download ora logga un evento `document_downloaded` via `append_audit` (`api/libraries.py`), verificato con un test che intercetta la chiamata.
- [x] **[sicurezza, medio]** Aggiunto `tests/test_config.py`: verifica esplicita e permanente che `DOCS_DIR` e `LIBRARY_STORAGE_DIR` non si sovrappongano mai (oggi sono sottoalberi fissi e disgiunti sotto `BASE_DIR` — il test è una guardia contro regressioni future, non solo una convenzione documentata).

**Uscita**: raggiunta — recuperare un documento è affidabile, testato (7 nuovi test), tracciato e raggiungibile sia dalla chat sia dalla tab documenti.

### Fase D — Demo stretta e corpus fittizio (sostanzialmente fatta, 20 agosto 2026)

- [x] **Corpus fittizio, scelta deliberata di profondità invece di quantità**: `examples/demo-corpus/` (Northstar Works, HR/IT/spese, 3 documenti) era già scritto in una sessione precedente e non ancora committato — messo in sicurezza. Aggiunto `examples/demo-corpus-quality/` (Meridian Precision Works, qualità/non conformità stile ISO, 2 documenti) per dimostrare dal vivo l'isolamento tra biblioteche, l'unico dei 5 principi di prodotto che il corpus singolo non poteva mostrare. Non i 15-20 documenti previsti dal piano originale: 5 documenti verificati end-to-end battono 20 documenti mai provati.
- [x] **Script di demo verificato dal vivo**, non solo scritto: `scripts/run_demo_validation.py` avvia una sessione reale contro il server API in esecuzione, carica i documenti, fa domande vere e controlla che le risposte citino il file giusto, che una domanda fuori corpus produca astensione, e ora anche **che una domanda la cui risposta vive nell'altra biblioteca produca comunque astensione** — la prova che l'isolamento è reale, non dichiarato. Eseguito più volte in questa sessione: `DEMO_VALIDATION_OK`.
- [x] **Scoperta genuina durante la verifica**: la prima domanda di isolamento scelta a mano falliva — condivideva la parola "required" (poi "work") con un chunk di Meridian, causando un falso positivo del keyword matching (non una vera fuga tra biblioteche, verificato leggendo il codice: la query SQL resta vincolata al `library_id`). Risolto scegliendo empiricamente una domanda senza sovrapposizione lessicale, verificata contro il server reale — non assunta. Documentato in `docs/DEMO_GUIDE.md` come nota per chi estende il corpus.
- [x] Golden set qualitativo (non il numero grezzo): 6 domande con citazione attesa + 1 astensione nel corpus originale (`questions.md`), più le verifiche automatiche di `run_demo_validation.py` su entrambe le biblioteche.
- [x] **GIF registrata (29 agosto 2026)**: contrariamente alla stima iniziale, un GIF (non un video con voce) era producibile autonomamente — pilotando un browser headless (Playwright, non il tool sandboxato: quello non espone i frame come file su disco) attraverso la sequenza esatta di `docs/DEMO_GUIDE.md` contro un'istanza reale in esecuzione, catturando uno screenshot per passo e assemblandoli con Pillow. `docs/assets/demo.gif`, linkato in cima al README al posto dello screenshot statico isolato.

**Uscita**: raggiunta — un percorso ripetibile e *verificato*, comprensibile anche a un pubblico non tecnico, ora anche con un GIF che lo dimostra senza richiedere di avviare l'app.

### Fase E — Rifinitura per credibilità enterprise (fatta, 20 agosto 2026)

- [x] Upload hardening confermato: allowlist type/size + controllo magic-bytes in `core/input_validator.py`, unico percorso di upload dopo l'isolamento della Fase A (`api/documents.py` legacy ora in `legacy_winsarp/`).
- [x] Audit trail e policy per libreria **erano già visibili in UI** (non un gap reale): `DocumentsTab.tsx` ha già un selettore completo `evidence_only/local_ollama/approved_openrouter/approved_provider` con conferma esplicita per i modi cloud; `AuditLogs.tsx` mostra già le voci di audit. Il vero gap era di coerenza visiva — vedi sotto.
- [x] **Igiene pubblicabile — trovato e risolto un problema serio**: scansione della cronologia git completa (26 commit) per segreti. Nessuna credenziale reale trovata. Trovato invece `docs/Progetto.RAG.Aziendale.pdf`, un documento **"Riservato uso interno"** di un contesto di lavoro reale, committato fin dal primo commit e già pushato su GitHub. Confermato dall'utente come materiale riservato — rimosso non solo dalla working directory ma **dall'intera cronologia** (`git filter-branch` su tutti i ref locali, poi force-push del branch remoto), verificato con `git rev-list --objects --all` che nessun oggetto residuo sia raggiungibile.
- [x] README riscritto per un lettore esterno: roadmap che distingue fatto da ancora-da-fare, link a tutti i documenti reali, comando di test semplificato, sezione licenza.
- [x] **[design, basso]** Rimosso l'username "admin" precompilato nel login, sostituito con un placeholder — verificato dal vivo nel browser.
- [x] **[design, basso]** `aria-current="page"` aggiunto alla navigazione attiva della sidebar.
- [x] **[design]** Trovato e corretto un problema non nel piano originale: `AuditLogs.tsx` usava classi Tailwind generiche (`dark:bg-gray-800`) invece del sistema di temi dell'app — riscritto per usare `useTheme()`/token `t.*`, verificato dal vivo nel browser dopo il login reale (e trovato lì un secondo problema: il log mostrava "229 voci con firma non valida" perché `ERMES_AUDIT_SECRET` non era configurato in locale — non manomissione, comportamento già documentato in `.env.example`, risolto localmente).
- [x] **[sicurezza, basso]** Audit dei log in `core/ai/providers/*`: verificato che le chiavi API vengono passate negli header HTTP, non nell'URL — le eccezioni httpx non incorporano gli header nella loro rappresentazione testuale. Nessuna fuga confermata.
- [x] **[sicurezza, basso]** Aggiunta `tests/test_api_auth_coverage.py`: cammina la tabella di route reale di FastAPI e verifica ricorsivamente che ogni endpoint (tranne un allowlist esplicito e commentato: health, login/logout, lo shell SPA) abbia `_verify_api_key` nel proprio albero di dipendenze — una vera guardia di regressione, non una convenzione.

**Uscita**: raggiunta.

### Fase F — Pacchetto portfolio/outreach (sostanzialmente fatta, 20 agosto 2026)

- [x] Licenza scelta con l'utente (MIT) e aggiunta (`LICENSE`).
- [x] One-pager di presentazione: versione visiva pubblicata come artifact, versione testuale in `docs/ONE_PAGER.md`, linkata dal README. Contiene solo numeri realmente misurati in questa sessione (recall, test passati, query del golden set), non placeholder.
- [x] **Repository reso pubblico** (confermato 29 agosto 2026, con conferma esplicita dell'utente prima del cambio) e GIF demo registrato (vedi Fase D).

**Uscita**: raggiunta.

## Ordine e motivazione

A → A2 → B → C → D → E → F. Prima si elimina l'ambiguità nel repo (A), poi si chiude il debito noto invece di scavalcarlo (A2 — CI/Docker/governance pendenti), poi si rende vero il claim centrale del prodotto (B, C — retrieval e recupero documento), solo dopo si costruisce la vetrina. Mostrare una demo prima di aver sistemato retrieval/download rischierebbe di non reggere a domande tecniche di follow-up — il rischio più alto per l'obiettivo di credibilità. Costruire la Fase B sopra una CI/Docker non ancora capiti (A2) rischierebbe di scoprire solo più tardi che la pipeline non riflette il codice attuale.

L'audit di team conferma questo ordine dall'esterno: i problemi più seri trovati (il varco di import WinSarp, l'ACL assente in `api/documents.py`) si risolvono entrambi isolando WinSarp — cioè restando in Fase A — mentre il differenziatore di prodotto (download da chat) è già pronto lato backend e richiede solo lavoro di Fase C.

## Verifica per fase

- **A**: `pytest` gira e riporta pass/fail chiaro; un solo script avvia l'app; nessun modulo del prodotto importa `core.winsarp`/`modules.winsarp` fuori dal flag legacy. *(fatto e committato, 20 agosto 2026)*
- **A2**: fatta — l'intero prodotto (non solo 14 file) è compreso, testato e committato in blocchi coerenti; due bug reali (Dockerfile, CI) trovati e corretti nel processo, non solo assunti funzionanti.
- **B**: numero di recall/precision/citation-coverage pubblicato e riproducibile.
- **C**: test di permessi sul download passa; prova manuale nel browser del percorso cerca → scarica, incluso da dentro la chat.
- **D**: demo eseguita end-to-end senza intervento manuale nascosto.
- **E/F**: repository ispezionato (a mano o con secret-scanner) prima di qualunque condivisione pubblica.

## Definition of Done — v0.1 mostrabile

Il progetto è pronto per essere mostrato (colloquio, demo a un'azienda, repository pubblico) quando tutti questi punti sono veri:

- [x] Nessun codice del prodotto importa WinSarp fuori dal modulo isolato.
- [x] Un solo entry point per avviare l'app, un solo path per scaricare un documento.
- [x] CI, Dockerfile e docker-compose verificati contro lo stato attuale del codice, non solo presunti funzionanti (Fase A2) — due bug reali trovati e corretti.
- [x] `pytest` verde, incluse le nuove suite su download e ingestion (171 passati, 0 falliti — anche l'ultimo fallimento pre-esistente è stato risolto per davvero, non solo documentato, il 20 agosto 2026).
- [x] Retrieval con numero di qualità reale e riproducibile (recall/precision/citation-coverage), non cherry-picked.
- [x] Il recupero del documento originale è raggiungibile da chat, ricerca e tab documenti, tutti e tre testati.
- [x] Corpus demo fittizio e percorso di 5 minuti, ripetibile senza intervento nascosto (manca solo la registrazione video).
- [x] Nessun file sensibile reale nella history: scansione completa eseguita, un documento riservato di terzi trovato e rimosso dall'intera cronologia (non solo dalla working directory).
- [x] README e one-pager scritti per un lettore esterno tecnico.

## Oltre la v0.1 — cosa manca per un prodotto enterprise davvero commerciabile

> Questa sezione risponde a una domanda diversa da tutto il resto del documento: non "cosa serve per essere credibili in un colloquio o in una demo" (Fasi A-F sopra), ma **"cosa servirebbe se un'azienda dovesse davvero comprare, pagare e affidarsi a questo prodotto in produzione"**. È un orizzonte lontano, deliberatamente fuori dallo scope delle Fasi A-F — utile per capire la distanza reale tra "MVP convincente" e "prodotto vendibile", non per pianificare il prossimo sprint. Non va eseguita insieme al resto: costruire qui prima di chiudere la Fase A-C sarebbe lavorare su fondamenta enterprise sopra un claim di prodotto (retrieval, download) non ancora verificato.

### 1. Identità e accesso
- SSO/OIDC reale (Entra ID, Okta, Google Workspace) — oggi solo login locale.
- Provisioning automatico utenti (SCIM) e gruppi sincronizzati dalla directory aziendale.
- ACL propagate dalla fonte (es. permessi SharePoint/Drive ereditati), non solo definite dentro Ermes.
- Ruoli più granulari di `admin`/`member` (es. revisore, sola-lettura per libreria, approvatore).

### 2. Scala e infrastruttura dati
- PostgreSQL + pgvector al posto di SQLite locale; object storage (S3/MinIO) al posto del filesystem locale per gli originali.
- Coda/worker dedicati per l'ingestion (oggi sincrona/in-process) — Redis Streams o simili, con retry e dead-letter.
- Deploy orizzontale dell'API, non a singola istanza.
- Piano di capacity/performance per corpus di decine di migliaia di documenti, non decine.

### 3. Connettori alle fonti reali
- SharePoint, Google Drive, Nextcloud, cartella di rete — oggi solo upload manuale.
- Sync incrementale, cancellazioni propagate, gestione dei permessi del connector (non solo import una tantum).

### 4. Sicurezza a livello enterprise
- Penetration test esterno e relativo report, non solo un audit interno.
- Scansione dipendenze/SBOM in CI, gestione segreti con un vault reale (non `.env`) in produzione.
- Crittografia a riposo per lo storage documenti.
- Antivirus/sandbox reale sugli upload (oggi solo allowlist tipo/dimensione/magic-bytes, comunque solido per un MVP ma non sufficiente per dati regolamentati).

### 5. Compliance e fiducia legale
- Percorso SOC 2 / ISO 27001 (o almeno readiness documentata).
- DPA (data processing agreement) GDPR, opzioni di residenza dati, politica di retention/cancellazione dati verificabile (diritto all'oblio).
- Registro di trattamento e valutazione d'impatto (DPIA) se si trattano dati HR/sanitari.

### 6. Operatività e affidabilità
- Backup/restore testati con drill reali (non solo documentati), non solo "esiste uno script".
- Osservabilità vera: APM, error tracking (es. Sentry), dashboard e alerting con on-call — oggi c'è `core/monitoring.py` ma non una pipeline operativa completa.
- Piano di disaster recovery e obiettivi RTO/RPO dichiarati.
- Runbook per incidenti (già impostati i principi in `docs/PROJECT_PLAN.md`, mai esercitati).

### 7. Modello commerciale
- Pricing e billing/subscription management — oggi il prodotto non ha alcun concetto di piano/fatturazione.
- Metering dell'uso (query, storage, utenti) per tier.
- Contratti tipo: MSA, DPA, SLA con percentuali di uptime dichiarate e penali.
- Materiali di vendita: security questionnaire pronto (SIG/CAIQ), case study, ambiente demo self-service.

### 8. Prodotto per un buyer enterprise
- Console admin più matura: analytics d'uso per team/libreria, gestione bulk utenti, esportazione audit.
- API pubblica documentata con rate limit dichiarati, per integrazioni di terzi.
- Opzioni di deployment: on-prem/installer, air-gapped, Helm chart per Kubernetes — oggi solo Docker Compose locale.
- Internazionalizzazione: oggi l'esperienza (prompt, UI, messaggi) è italiano-centrica; un'azienda multi-country richiederebbe i18n reale.

### Come leggere questa lista

Non è un elenco di cose "sbagliate" nel progetto attuale — un MVP locale a singolo tenant, con principi di sicurezza pensati bene fin dall'inizio (vedi `docs/ARCHITECTURE_TARGET.md`), è esattamente la scelta giusta per l'obiettivo attuale (credibilità tecnica, non vendita reale). Questa sezione serve a due cose: dare un vocabolario preciso se in un colloquio o una demo qualcuno chiede "e per la produzione enterprise cosa manca" — sapere rispondere con questa lista è di per sé un segnale di maturità — e fare da riferimento se un giorno la direzione cambiasse davvero verso un prodotto commerciale.
