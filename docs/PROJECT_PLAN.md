# Piano operativo — da Ermes RAG a Ermes Knowledge

**Obiettivo:** trasformare il repository in un bibliotecario aziendale local-first, semplice da installare e affidabile nel cercare/interrogare documenti con fonti verificabili.

**Principio guida:** una versione piccola, funzionante e dimostrabile vale più di una piattaforma enterprise incompleta.

## 1. Definition of product

Alla fine della v0.1 una PMI deve poter avviare Ermes con Docker, creare una biblioteca, caricare documenti, indicizzarli, cercarli e fare domande ricevendo citazioni al file e alla pagina. Può scegliere un LLM locale oppure configurare un provider API esterno. Un amministratore vede stato dell'import e può gestire le biblioteche.

Non promettiamo ancora: SSO, SharePoint sync, multi-tenancy SaaS, agenti, workflow complessi o automazioni di scrittura.

## 2. Destinazione architetturale

```text
Web app
   ↓
API Ermes
   ├── biblioteca/documenti/utenti
   ├── ricerca e assistente con citazioni
   ├── provider LLM locale/API
   └── job di ingestion
        ↓
PostgreSQL + pgvector   MinIO/S3   Parser documenti   Ollama (opzionale)
```

Il database contiene metadati, utenti, biblioteche, versioni e permessi. I file originali stanno in object storage. Il vector index serve alla ricerca e può essere ricostruito; non è la fonte di verità.

## 3. Regole di lavoro

1. Una sola UI React e una sola API FastAPI; nessun doppione Streamlit/entrypoint parallelo nel prodotto.
2. I riferimenti al precedente verticale restano fuori dall'esperienza pubblica e dal core. Prima della release si eseguirà una scansione case-insensitive di nomi, contenuti e asset per isolarli in un modulo privato/archiviato o rimuoverli.
3. Ogni funzionalità nuova ha test e una definizione di completamento; non si accumulano feature "quasi pronte".
4. I segreti non entrano mai in Git, log, backup o artefatti CI.
5. Prima di aggiungere un connector business si valida il flusso con upload e filesystem.
6. Le risposte AI non devono essere restituite senza fonte, salvo una risposta esplicita di astensione.

## 4. Piano a fasi

Le durate sono indicative e presuppongono lavoro individuale costante. Ogni fase si chiude solo al superamento dei criteri di uscita.

### Fase 0 — Decisioni e inventario

**Scopo:** decidere il perimetro e conoscere davvero l'attuale repository prima di spostare codice.

**Attività**

- scegliere nome provvisorio, descrizione one-line e pubblico target: PMI con documenti/procedure interne;
- creare una mappa dei componenti attuali: da mantenere, adattare, archiviare o eliminare;
- inventariare e isolare riferimenti al precedente verticale e qualsiasi asset non destinato alla demo;
- scegliere se creare una nuova branch/repository prodotto oppure eseguire una migrazione in-place;
- scegliere il corpus demo fittizio e le 20–30 domande gold;
- definire licenza, privacy statement e limiti di prodotto.

**Deliverable:** ADR iniziali, inventario componenti, backlog v0.1 prioritizzato, demo corpus fittizio.

**Criterio di uscita:** tutti sanno spiegare in una frase cosa fa la v0.1 e cosa non fa.

### Fase 1 — Pulizia e foundation del repository

**Scopo:** avere una base avviabile, coerente e sicura.

**Attività**

- rendere React/Vite l'unica UI e FastAPI l'unica API pubblica;
- spostare/archiviare codice WinSarp senza cancellazioni irreversibili finché non è verificato;
- eliminare file vuoti, launcher duplicati, artefatti runtime e documentazione incoerente;
- definire layout target (`apps/api`, `apps/web`, `packages`, `docs`, `infra`, `tests`), anche se la migrazione è graduale;
- correggere import/API e rendere i test rilevanti verdi;
- una configurazione unica, porte coerenti, `.env.example` e Compose dev;
- attivare formatter/linter/test/secret scan come gate reali.

**Deliverable:** `docker compose up` avvia web, API e dipendenze; CI senza bypass.

**Criterio di uscita:** una persona nuova avvia il progetto seguendo README senza istruzioni private.

### Fase 2 — Modello del bibliotecario

**Scopo:** introdurre il dominio generico senza dipendere dal vecchio motore formule.

**Entità minime**

- `User`: amministratore o membro;
- `Library`: spazio documentale privato o condiviso;
- `Document`: identità logica del file;
- `DocumentVersion`: file, hash, data, stato e origine;
- `IngestionJob`: import in attesa, in corso, completato o fallito;
- `Citation`: riferimento a documento/versione/pagina/estratto.

**Attività**

- usare SQLite come storage locale di bootstrap per la v0.1 in sviluppo, dietro al contratto `LibraryStore`; introdurre PostgreSQL con migrazioni prima del pilot multiutente;
- introdurre MinIO/S3 per i file originali;
- API per creare/elencare biblioteche e documenti;
- autenticazione locale semplice ma fail-closed; utenti demo creati solo in development;
- UI biblioteche e lista documenti.

**Deliverable:** una biblioteca esiste, ha documenti e metadati persistenti.

**Criterio di uscita:** riavvio del sistema senza perdita di biblioteche, documenti o utenti. La UI rifiuta l'accesso se non Ã¨ configurata una password locale o una Bearer API key.

### Fase 3 — Ingestion affidabile

**Scopo:** rendere i file leggibili e tracciabili.

**Attività**

- upload streaming con limiti, allowlist tipi e nomi sicuri;
- conservazione dell'originale su MinIO/S3;
- parsing iniziale di PDF, DOCX, XLSX, TXT e Markdown;
- job asincrono e stato visibile nella UI;
- estrazione pagine/sezioni, hash, lingua e metadati;
- nuova versione quando cambia lo stesso documento; possibilità di reindex;
- gestione errori e quarantena; OCR solo come job opzionale in questa fase.

**Deliverable:** upload → job → documento consultabile, con errore comprensibile quando il parsing fallisce.

**Criterio di uscita:** i formati dichiarati nel README sono importati e testati con file demo.

### Fase 4 — Ricerca e citazioni

**Scopo:** rendere utile il bibliotecario anche senza LLM.

**Attività**

- baseline completata: chunk persistenti per documento, ricerca locale e citazione con documento, versione e locator del passaggio;
- full-text search e ricerca vettoriale/ibrida;
- chunking con page/section locator;
- filtri per biblioteca, tipo, data e tag;
- pagina risultato con estratto e apertura dell'originale;
- citazioni formalizzate nell'API;
- golden set con metriche `recall@k`, `citation coverage` e latenza.

**Deliverable:** ricerca testuale e semantica che restituisce documenti e passaggi, non una chat generica.

**Criterio di uscita:** il golden set raggiunge la soglia definita e ogni risultato indica fonte/versione.

### Fase 5 — Assistente evidence-first

**Scopo:** aggiungere IA senza perdere affidabilità.

**Attività**

- adapter LLM per Ollama locale;
- adapter per endpoint OpenAI-compatible, opzionale e configurato via secret;
- retrieval prima della generazione, con soli chunk autorizzati nel contesto;
- prompt e schema risposta con citazioni obbligatorie;
- astensione quando mancano fonti sufficienti;
- UI assistente che presenta risposta, fonti, pagina ed estratto in modo cliccabile;
- feedback "utile/non utile" e tracciamento anonimo/minimizzato.

**Deliverable:** chat con fonti utilizzabile su corpus demo.

**Criterio di uscita:** nessuna risposta del golden set è mostrata come fondata senza almeno una citazione valida.

### Fase 6 — Uso da PMI: permessi e operatività

**Scopo:** rendere l'installazione usabile da un piccolo team.

**Attività**

- ruoli `admin` e `member`;
- biblioteche private/condivise e enforcement server-side dei permessi;
- audit essenziale di login, upload, delete, reindex, configurazione provider;
- dashboard con job, errori e ultimo sync;
- backup dei metadati e file; restore documentato e testato;
- policy semplice `local_only` vs `external_api_allowed` per biblioteca.

**Deliverable:** due utenti vedono solo ciò che devono vedere; admin può capire lo stato dell'istanza.

**Criterio di uscita:** test di autorizzazione, backup e restore superati in CI/integration.

### Fase 7 — Demo, documentazione e release v0.1

**Scopo:** renderlo presentabile su GitHub e provabile da aziende.

**Attività**

- corpus demo di un'azienda immaginaria: HR, IT, qualità e manuale prodotto;
- demo video/GIF: import, ricerca, citazioni, accesso negato, provider locale/API;
- README in inglese, guida deploy e threat model;
- OpenAPI, CONTRIBUTING, SECURITY, LICENSE, NOTICE e changelog;
- test E2E browser, container/dependency scans, SBOM;
- release `v0.1.0` con limitazioni dichiarate e roadmap pubblica.

**Deliverable:** repository condivisibile e demo auto-consistente.

**Criterio di uscita:** un valutatore tecnico riesce a installare, provare e comprendere il valore senza supporto diretto.

### Fase 8 — Validazione e integrazioni

**Scopo:** evitare di costruire feature richieste solo in teoria.

**Attività**

- far provare il prodotto a 3–5 persone/PMI con un corpus non sensibile o demo;
- raccogliere frizioni: formato, ricerca, fonti, prestazioni, privacy e installazione;
- scegliere **un solo** primo connector in base alle prove: filesystem, SharePoint, Google Drive o Nextcloud;
- implementare sync incrementale, cancellazione e permessi del connector scelto;
- solo dopo, valutare Teams/Slack per notifiche e OIDC/SSO per identity aziendale.

**Deliverable:** primo feedback reale e prima integrazione guidata da domanda verificata.

**Criterio di uscita:** un utente esterno completa un caso d'uso senza assistenza dello sviluppatore.

## 5. Ordine delle integrazioni

| Priorità | Integrazione | Quando | Ragione |
|---:|---|---|---|
| 1 | Ollama | Fase 5 | modalità locale e demo privata |
| 2 | API OpenAI-compatible | Fase 5 | scelta del cliente senza lock-in |
| 3 | MinIO/S3 | Fase 2 | gestione corretta degli originali |
| 4 | Filesystem/watch folder | Fase 3 o 8 | prima sorgente reale più semplice |
| 5 | SharePoint **oppure** Drive/Nextcloud | Fase 8 | deciso dai tester, non per intuizione |
| 6 | Teams/Slack | dopo connector | notifiche, non knowledge source iniziale |
| 7 | OIDC/Entra/AD | dopo pilot | SSO e gruppi aziendali |
| 8 | MCP read-only | dopo API stabile | connettere altri assistant in sicurezza |

## 6. Cose da non fare per ora

- migrare subito ogni file/cartella del vecchio progetto;
- sostituire contemporaneamente Chroma, UI, API, parser e auth senza milestone;
- promettere GDPR/ISO/enterprise readiness senza evidenza;
- supportare più vector DB e più queue nella v0.1;
- aggiungere agenti con azioni di scrittura;
- costruire un connector SharePoint prima di avere upload/ingestion affidabili;
- costruire una knowledge graph prima di una ricerca con fonti solida.

## 7. Definition of Done v0.1

La v0.1 è completata quando tutti questi punti sono veri:

- [ ] installazione Docker riproducibile su macchina pulita;
- [ ] utente crea biblioteca e carica PDF/DOCX/XLSX/TXT/MD;
- [ ] file conservato, parsato, versionato e ricercabile;
- [ ] ricerca mostra passaggio, documento, versione e pagina;
- [ ] assistente locale risponde solo con citazioni o si astiene;
- [ ] provider esterno è opzionale e chiaramente configurato;
- [ ] autorizzazione server-side tra admin/member e biblioteche;
- [ ] import/reindex/errori sono visibili;
- [ ] golden set e test di sicurezza fondamentali sono verdi;
- [ ] demo corpus, README, licenza e guida deploy sono pronti;
- [ ] nessuna parte del precedente verticale è visibile nella demo pubblica o nel core.

## Stato dell'implementazione (MVP locale, 31 luglio 2026)

Il flusso verticale iniziale e' ora presente e verificato: autenticazione locale, biblioteca privata/condivisa con controllo server-side, upload di PDF/DOCX/XLSX/TXT/Markdown, conservazione dell'originale separata dal corpus legacy, job persistente di ingestion, chunk con locator, ricerca locale, versioni e ripristino. L'assistente interroga esclusivamente la biblioteca selezionata e restituisce citazioni; quando non trova passaggi, si astiene.

L'LLM e' volutamente **spento per default** (`evidence_only`). `local_ollama` invia al solo server Ollama configurato i pochi estratti gia' recuperati. Per il cloud, il proprietario della biblioteca sceglie in modo esplicito `approved_openrouter` oppure un `approved_provider` configurato dall'amministratore; entrambe le opzioni richiedono `ERMES_LIBRARY_CLOUD_CONSENT=1`. Il retrieval invia il contesto solo al provider selezionato e non esiste fallback automatico cloud o tra provider.

Restano necessari prima di qualificare il progetto come v0.1 pubblicabile: retrieval vettoriale/ibrido e golden set, ACL a gruppi, sessioni/audit durevoli, storage S3/MinIO, antivirus/OCR/quarantena, Compose riproducibile, corpus demo fittizio, CI quality/security gates e rimozione/archiviazione verificata di ogni materiale non pubblicabile.

## 8. Primo sprint suggerito

Non implementare ancora il vector DB nuovo né i connector. Il primo sprint deve produrre chiarezza e un avvio stabile:

1. creare branch di lavoro e backup logico del repository attuale;
2. inventariare i moduli e decidere cosa archiviare;
3. rendere verde l'avvio API/test essenziale e togliere UI/endpoint WinSarp dal menu pubblico;
4. stabilire una singola porta, una singola entrypoint e Compose;
5. aggiungere biblioteche e documenti persistenti (SQLite locale), upload validato e parsing iniziale; migrare a PostgreSQL/MinIO quando il flusso Ã¨ stabilizzato;
6. creare il corpus demo fittizio e cinque query gold.

Al termine, il progetto non è ancora ricco di funzioni, ma ha una direzione, confini puliti e una base su cui costruire senza ricreare il caos.
