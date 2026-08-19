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
- [x] **[architect]** `api.py` (root, -452 righe): confermato un vero shim di compatibilità che re-esporta `app` dal pacchetto `api/`, non codice morto o migrazione a metà — verificato che nessun import vivo dipenda dal vecchio monolite.
- [x] **[architect/qa]** `core/governance.py`: estensione RBAC per-utente (API key hashate, scritture atomiche, file lock) — verificata **collegata davvero** a `api/auth.py`/`api/users.py` (non codice orfano) e coperta da `tests/test_enterprise.py`/`test_api_user_rotation.py`, entrambi verdi. Trovato e corretto un bug minore collegato: lo scheduler di backup in `api/__init__.py` loggava `result.get("file", ...)` ma `create_backup()` ritorna `"name"` — il log stampava sempre "?".
- [x] **[qa]** `core/backup_manager.py`: lock a thread + scrittura atomica sul restore, verificato collegato a endpoint admin-only e a uno scheduler in background. **Lacuna segnalata, non chiusa ora**: `tests/test_backup_manager.py` non copre il nuovo percorso di restore atomico/locking — serve una sessione QA dedicata.
- [x] Durante la revisione, trovati e spostati in `legacy_winsarp/` altri contenuti WinSarp mal etichettati sotto `core/`: `core/evaluation/` (formula_validator.py, semantic_evaluator.py) e `core/templates/` (master_patterns.json, few_shot_examples.json) — 26 test in `tests/test_evaluation.py` spostati con loro; import della copia spostata corretto dopo un giro di verifica con `pytest --collect-only`.
- [x] Trovati ed eliminati 7 file duplicati morti in root (nessun importatore): `governance.py`, `rate_limiter.py`, `theme.py`, `sidebar_ui.py`, `welcome_ui.py`, `monitor_dashboard.py`, `chat_ui.py`; più `frontend/src/App.jsx`/`main.jsx` (prototipo JS pre-TypeScript, `index.html` carica già `main.tsx`) e un `package.json`/`package-lock.json` orfano in root (dipendenza Monaco Editor del vecchio FormulaEditor).
- [x] Committato tutto in 8 commit coerenti per area (CI/Docker/setup, backend, frontend, test, doc di strategia) invece di un commit monolitico.

**Non chiuso, segnalato per una sessione dedicata**: `tests/test_e2e_api.py::test_e2e_rbac_full_flow` passa da solo ma fallisce nella suite completa — un problema di isolamento tra test (probabile stato globale di `config`/env condiviso tra moduli di test), non un bug di prodotto. `legacy_winsarp/tests/test_composer.py` ha un `KeyError` preesistente non collegato allo spostamento di oggi (dati di pattern già vuoti prima).

**Uscita**: raggiunta — nessun diff pendente sconosciuto; CI, Docker e governance committati e verificati, non solo "lasciati lì".

### Fase B — Retrieval onesto e misurato (~1-1.5 settimane)

> Corretta dopo la Fase A: il target è `core/library_store.py` (ricerca del bibliotecario) e `evaluation/run_library_eval.py`, non il vecchio `rag_engine.py`/`run_eval.py` ormai in `legacy_winsarp/`.

- [ ] Pubblicare in `docs/RETRIEVAL_EVALUATION.md` il numero reale e attuale di `run_library_eval.py` (oggi 16 query, `recall_at_3`), non un numero del motore formule legacy.
- [ ] Valutare se la ricerca di `core/library_store.py` (oggi full-text/morfologica, vedi `search_with_profile`) beneficia di un vero componente vettoriale/ibrido dedicato al bibliotecario — è un lavoro nuovo, non un porting dell'`HybridRetriever` legacy (che resta nel suo perimetro isolato).
- [ ] Aggiungere la metrica **citation coverage** allo script `run_library_eval.py`.
- [ ] Espandere il golden set library oltre le attuali 16 query, con casi realistici del corpus demo (Fase D).

**Uscita**: un numero di qualità retrieval che regge a una domanda diretta in colloquio tecnico.

### Fase C — Recupero documento come feature di prima classe (~4-5 giorni)

- [ ] **[design, medio — priorità alta]** Collegare il download del documento originale nelle citazioni di `ChatArea.tsx`: l'endpoint è già pronto e verificato sicuro, manca solo il pulsante/link. È il differenziatore di prodotto deciso in questa revisione ed è il pezzo più economico da chiudere.
- [ ] **[dev/sicurezza, medio]** Test di integrazione sul download: accesso negato a non-membri, libreria privata vs condivisa, versione corretta servita — oggi non esiste nessun test a questo livello.
- [ ] **[dev, medio]** Consolidare l'estrazione testo PDF/DOCX: `api/documents.py` reimplementa l'estrazione invece di riusare `core/document_parser.py` — due implementazioni indipendenti che possono divergere.
- [ ] **[dev, medio]** Aggiungere test diretti per `core/ingestion_service.py` (`process_ingestion_job`) — unico modulo core nel perimetro esaminato senza copertura, gestisce gli stati di errore che l'utente vede come "documento non indicizzato".
- [ ] Audit: loggare ogni download riusando il meccanismo di audit esistente (`core/governance.py`).
- [ ] **[sicurezza, medio]** Aggiungere un controllo/test esplicito che `DOCS_DIR` (legacy) e `LIBRARY_STORAGE_DIR` (nuovo) non si sovrappongano mai — oggi la separazione è per convenzione (`api/__init__.py:70` esclude a mano la cartella "libraries").

**Uscita**: recuperare un documento è affidabile, testato, tracciato e raggiungibile da ogni punto dell'app (non solo dalla tab documenti) quanto rispondere con citazioni.

### Fase D — Demo stretta e corpus fittizio (~1 settimana)

- [ ] Corpus fittizio verticale (qualità/ISO o HR, PMI manifatturiera) con 15-20 documenti realistici.
- [ ] Golden set di 15-20 domande, incluse 2-3 senza risposta (per mostrare l'astensione onesta).
- [ ] Script di demo di 5 minuti: upload → domanda con citazione → richiesta esplicita di un documento → domanda senza risposta.
- [ ] Registrazione GIF/video per uso portfolio.

**Uscita**: un percorso di 5 minuti, ripetibile, comprensibile anche a un pubblico non tecnico.

### Fase E — Rifinitura per credibilità enterprise (~1 settimana)

- [ ] Upload hardening minimo ma reale: allowlist type/size, controllo magic-bytes (già presente lato libraries — verificato solido dall'audit sicurezza; da confermare resti l'unico percorso di upload dopo la Fase A).
- [ ] Rendere visibile in UI/admin l'audit trail e la policy `evidence_only/local_ollama/approved_openrouter` per libreria.
- [ ] Igiene pubblicabile: secret scan sulla history, nessun file sensibile (`.env`, `LOCAL_LOGIN.txt`, PDF personali, dati WinSarp reali) esposto.
- [ ] README e posizionamento riscritti per un lettore esterno (recruiter/CTO).
- [ ] **[design, basso]** Rimuovere l'username "admin" precompilato nel form di login — piccolo segnale di "ambiente dev" più che di prodotto pronto per una demo esterna.
- [ ] **[design, basso]** Passata di accessibilità di base: `aria-current` sugli item di navigazione attivi nella sidebar, verifica focus/tastiera sui flussi principali (login, chat, upload).
- [ ] **[sicurezza, basso]** Audit dei log (`core/ai/providers/*`, percorsi di errore di `core/evidence_assistant.py`) per escludere fughe accidentali di segreti/PII — non verificato in questa passata.
- [ ] **[sicurezza, basso]** Valutare una regola CI/lint che impedisca nuovi endpoint sotto `api/` senza `_require_role`/`_verify_api_key`, per evitare di ripetere il pattern di `api/documents.py`.

**Uscita**: repository e demo pronti per essere mostrati senza preparazione dell'ultimo minuto.

### Fase F — Pacchetto portfolio/outreach (~3-4 giorni)

- [ ] Repository pubblico pulito, licenza scelta.
- [ ] One-pager di presentazione (problema, principi, demo, metriche retrieval).
- [ ] Video/GIF demo pubblicato assieme al repo.

**Uscita**: un link solo da mandare, che regge da solo.

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
- [ ] `pytest` verde, incluse le nuove suite su download e ingestion.
- [ ] Retrieval con numero di qualità reale e riproducibile (recall/precision/citation-coverage), non cherry-picked.
- [ ] Il recupero del documento originale è raggiungibile da chat, ricerca e tab documenti, tutti e tre testati.
- [ ] Corpus demo fittizio e percorso di 5 minuti, ripetibile senza intervento nascosto.
- [ ] Nessun file sensibile reale (`.env`, `LOCAL_LOGIN.txt`, scansioni personali, dati WinSarp veri) nella history o nella working directory prima di qualunque condivisione.
- [ ] README e one-pager scritti per un lettore esterno tecnico.

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
