# 📘 Ermes Knowledge (Ermes-Librarian) — Documento Descrittivo Completo di Progetto

> **Versione:** 2.2.6 Enterprise Ready  
> **Stato:** Produzione / On-Premise & Cloud Privato  
> **Repository:** `c:\Progetti\ProgettoRAG_DEV`  
> **Licenza:** Open Source / MIT con conformità Enterprise  

---

## 1. Executive Summary & Visione di Prodotto

**Ermes Knowledge** è una piattaforma enterprise autonoma e modulare di **Retrieval-Augmented Generation (RAG)**, progettata per consentire ad aziende, enti e organizzazioni di interrogare il proprio patrimonio documentale interno in linguaggio naturale, ottenendo risposte **istantanee, accurate, prive di allucinazioni e rigorosamente supportate da citazioni verificabili alla fonte**.

A differenza delle soluzioni basate su chatbot cloud commerciali (es. ChatGPT, Copilot generici), Ermes Knowledge è sviluppata seguendo il paradigma **Local-First & Data Sovereignty**:
- **Zero data-leakage**: nessun documento o query abbandona il perimetro aziendale a meno che non sia esplicitamente configurato un connettore cloud approvato.
- **Evidence-First**: nessuna risposta viene generata senza una prova documentale esplicita; se l'informazione non è presente nei documenti autorizzati, il sistema dichiara con precisione di non poter rispondere.
- **Isolamento e Sicurezza Rigorosa**: controllo accessi basato su ruoli (RBAC), integrazione Single Sign-On (SSO / OIDC), mascheramento dati sensibili (DLP) e registro di audit crittograficamente immutabile (hash-chaining SHA-256).

---

## 2. Il Problema di Mercato Risolto

Nelle moderne organizzazioni, oltre l'80% delle informazioni risiede in **documenti non strutturati** (PDF di procedure, contratti, specifiche tecniche DOCX, schede prodotto XLSX, note e policy interne). Questo genera tre criticità strutturali:

1. **Frammentazione e Silos Informativi**: i dipendenti spendono ore a ricercare manuali su cartelle di rete condivise (SMB/NAS), portali SharePoint e allegati email, spesso consultando versioni obsolete.
2. **Inaffidabilità dei Motori di Ricerca Tradizionali**: la classica ricerca per sole parole chiave fallisce di fronte a sinonimi, acronimi aziendali o domande complesse in linguaggio naturale.
3. **Rischi dei Chatbot Cloud e Allucinazioni**: inviare documenti riservati a servizi cloud esterni viola il GDPR e il segreto industriale; inoltre, i modelli LLM generici tendono a "inventare" dettagli plausibili ma falsi (allucinazioni), inaccettabili in ambito legale, tecnico o finanziario.

**La Soluzione Ermes**: unire la precisione della ricerca ibrida (BM25 lessicale + vettori semantici densi + reranking neurale) con un modulo di verifica delle evidenze che garantisce risposte esatte, verificabili con un clic sul documento e sulla pagina d'origine.

---

## 3. I Cinque Principi Architetturali Fondamentali

1. **Local-First e Sovranità del Dato**:
   La piattaforma funziona al 100% offline su server on-premise (con modelli locali come Ollama o vLLM). L'adozione di API esterne è un'opzione esplicita, auditata e configurabile.
2. **Evidence-First (Verificabilità Assoluta)**:
   Ogni affermazione prodotta dall'assistente è associata a una citazione puntuale (nome documento, numero pagina, frammento testuale). Senza evidenza documentale sufficiente, il sistema si astiene.
3. **Isolamento Rigoroso tra Librerie (Zero Cross-Contamination)**:
   La ricerca è confinata alla libreria selezionata prima che il contesto raggiunga l'LLM. Una domanda posta nella libreria "Amministrazione" non potrà mai visualizzare evidenze della libreria "Risorse Umane".
4. **Documenti come Input Non Fidato (Prompt Injection Defense)**:
   Il testo estratto dai documenti viene trattato rigorosamente come dato in sola lettura, sanificato e confinato per impedire tentativi di prompt injection indiretta.
5. **Tracciabilità Crittografica Immutabile**:
   Ogni query, upload, modifica o download è registrato in un file di audit protetto da concatenazione crittografica di hash SHA-256. Qualsiasi manomissione esterna rende l'intero log invalido e rilevabile istantaneamente.

---

## 4. Architettura di Sistema

Ermes Knowledge applica una rigida separazione tra il **Control Plane** (identità, autorizzazioni, policy, audit e metadati) e il **Data Plane** (file originali, parser, indici vettoriali, motori di ricerca e modelli di linguaggio):

```
                        ┌────────────────────────────────────────────────────────┐
                        │              Browser Web / SPA (React 18)              │
                        └───────────────────────────┬────────────────────────────┘
                                                    │ (HTTPS / SSE / REST)
                        ┌───────────────────────────▼────────────────────────────┐
                        │             API Gateway & Auth (FastAPI)               │
                        │    OIDC / SSO • RBAC • Rate Limiting • DLP Guardrail   │
                        └──────┬──────────────────────┬───────────────────┬──────┘
                               │                      │                   │
                               ▼                      ▼                   ▼
                     ┌──────────────────┐   ┌──────────────────┐  ┌───────────────┐
                     │ Control Plane    │   │  Ingestion &     │  │  Governance   │
                     │ SQLite/Postgres  │   │  Background      │  │  & Audit      │
                     │ Metadati, ACL,   │   │  Worker (Docling,│  │  (SHA-256     │
                     │ Librerie, Utenti │   │  OCR, Watcher)   │  │  Hash Chain)  │
                     └──────────────────┘   └─────────┬────────┘  └───────────────┘
                                                      │
                                                      ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   DATA PLANE (Retrieval & RAG)                              │
 │                                                                                             │
 │   ┌───────────────────────────┐      ┌──────────────────────────┐                           │
 │   │  BM25 Lexical Index       │      │  Dense Vector Index      │                           │
 │   │  (Keyword & Exact Match)  │      │  (Cosine Semantic Match) │                           │
 │   └─────────────┬─────────────┘      └────────────┬─────────────┘                           │
 │                 │                                 │                                         │
 │                 └───────────────┬─────────────────┘                                         │
 │                                 ▼                                                           │
 │                ┌──────────────────────────────────┐                                         │
 │                │ Reciprocal Rank Fusion & Rerank │                                         │
 │                │ (Cross-Encoder Neural Reranker)  │                                         │
 │                └────────────────┬─────────────────┘                                         │
 │                                 ▼                                                           │
 │                ┌──────────────────────────────────┐                                         │
 │                │ Concurrency Evidence Verifier    │ ◄── [ ThreadPoolExecutor ]              │
 │                │ (Strict Grounding & Threshold)   │                                         │
 │                └────────────────┬─────────────────┘                                         │
 │                                 ▼                                                           │
 │                ┌──────────────────────────────────┐                                         │
 │                │ Local LLM (Ollama) / Cloud Model │                                         │
 │                └────────────────┬─────────────────┘                                         │
 └─────────────────────────────────┼───────────────────────────────────────────────────────────┘
                                   │
                                   ▼
          Risposta Streaming SSE con Citazioni e Pagine Verificabili
```

---

## 5. La Pipeline RAG End-to-End

Il ciclo di vita dell'informazione in Ermes Knowledge si articola in 7 fasi altamente ottimizzate:

### Fase 1: Ingestion & Parsing Multi-Formato
- Supporto nativo per **PDF** (digitali e scansionati via OCR), **DOCX**, **XLSX**, **TXT**, **Markdown** e **HTML**.
- Motore di parsing basato su **Docling** e parser specializzati per fogli di calcolo e documenti d'ufficio.
- Estrazione automatica dei metadati: numero di pagina, capitolo, autore, data di creazione e hash SHA-256 del file.

### Fase 2: Chunking Semantico & Normalizzazione
- Segmentazione del testo in frammenti (chunk) con sovrapposizione bilanciata (overlap) per preservare il contesto sintattico.
- Mantenimento delle coordinate di origine: ogni chunk conserva l'esatto riferimento alla pagina e al paragrafo.

### Fase 3: Indicizzazione Ibrida Doppia
- **Indice Lessicale BM25**: garantisce l'individuazione di codici prodotto, numeri di articolo, date, codici fiscali e nomi propri.
- **Indice Vettoriale Denso**: estrazione dei vettori di embedding semantici tramite modelli all'avanguardia (es. `all-MiniLM-L6-v2` o `bge-m3`), calcolando la somiglianza del coseno.

### Fase 4: Query Expander & Glossario Aziendale Dinamico
- Modulo di espansione terminologica con caricamento dinamico e prioritario di acronimi e sinonimi (`config/synonyms.json`).
- Permette all'utente di definire acronimi aziendali (es. "DURC", "SLA", "PDR") che vengono tradotti ed espansi automaticamente durante la ricerca.

### Fase 5: Retrieval Ibrido e Reranking Neurale
- **Reciprocal Rank Fusion (RRF)**: fusione dei punteggi lessicali e semantici per produrre una prima graduatoria di candidati.
- **Cross-Encoder Reranker**: modello neurale di scoring profondo che valuta la pertinenza effettiva di ciascun frammento rispetto alla domanda dell'utente, filtrando il rumore.

### Fase 6: Evidence Verifier Concorrente
- Verifica multi-thread ad alte prestazioni (`ThreadPoolExecutor`) con connection pooling HTTP: verifica che i passaggi selezionati contengano prove logiche per rispondere alla domanda prima di invocare il modello generativo.
- Se il punteggio di rilevanza scende sotto la soglia di sicurezza, il sistema attiva il meccanismo di astensione evitando la risposta allucinata.

### Fase 7: Sintesi e Streaming SSE Real-Time
- Connessione **Server-Sent Events (SSE)** al canale `/api/libraries/{id}/ask/stream`.
- La risposta viene trasmessa a schermo token-per-token in tempo reale, accompagnata dai badge cliccabili delle citazioni.

---

## 6. Funzionalità Avanzate per l'Uso Aziendale

### Sincronizzazione Automatica Cartelle (Folder Watcher / NAS)
Un servizio daemon monitora cartelle locali o condivisioni di rete aziendali (cartelle SMB su Windows/Linux). Ogni nuovo documento inserito viene automaticamente indicizzato e sincronizzato nella libreria associata senza alcun intervento manuale.

### Gestione Permessi e Multi-Libreria (RBAC & ACL)
- **Ruoli di Sistema**:
  - `Admin`: Configurazione globale, gestione utenti, audit log, connettori e impostazioni.
  - `Editor`: Creazione librerie, caricamento ed eliminazione documenti, gestione glossario.
  - `Reader`: Sola lettura, interrogazione delle librerie autorizzate, download documenti citati.
- **Isolamento Documentale**: le librerie possono essere pubbliche per l'intera azienda o ristrette a specifici gruppi e utenti.

### Protezione Dati (DLP & Anti-PII)
Filtro automatico in entrata e in uscita per il mascheramento di dati personali e finanziari (Codici Fiscali italiani, numeri di carte di credito, IBAN, numeri di telefono).

### Esperienza Utente Moderna e Produttiva
- **Export Chat in Markdown**: salvataggio completo della conversazione, comprensivo di fonti e metadati temporali, per report o verbali di riunione.
- **Nuova Chat Istantanea**: reset dello stato conversazionale con un clic senza dover ricaricare la pagina web.
- **Pannello Citazioni Interattivo**: finestra modale con chiusura rapida (tasto ESC o click esterno), testo completo dell'evidenza e pulsante per copiare la citazione.
- **Filtri Documentali**: ricerca rapida per nome e filtri con pillole cliccabili per formato file (PDF, DOCX, XLSX, TXT).

---

## 7. Sicurezza, Governance & Audit Immutabile

La sicurezza di Ermes Knowledge è progettata secondo i principi di **Defense in Depth** e **Fail-Closed**:

| Componente di Sicurezza | Implementazione in Ermes |
|---|---|
| **Autenticazione** | Supporto nativo OIDC (Microsoft Entra ID, Keycloak, Google Workspace) + credenziali locali hashate con PBKDF2/Argon2. |
| **Fail-Closed Authorization** | Un utente non autenticato o non autorizzato riceve un codice HTTP `404 Not Found` (invece di `403 Forbidden`) per prevenire l'enumerazione di risorse riservate. |
| **Audit Log Tamper-Evident** | Ogni evento scrive un record concatenato crittograficamente con hash SHA-256 del record precedente (`audit.jsonl`). Una pagina dedicata ne valida costantemente l'integrità. |
| **Protezione RootFS Read-Only** | Compatibilità completa con container Docker immutabili (`read_only: true`): file temporanei e lock di sincronizzazione posizionati in cartelle scrivibili dedicate. |
| **Multi-Process FileLock** | Concorrenza di scrittura protetta su Windows e Linux per utenti, audit log e sinonimi. |

---

## 8. Stack Tecnologico

### Backend
- **Linguaggio & Framework**: Python 3.12, FastAPI, Uvicorn, Pydantic v2.
- **Database & Persistenza**: SQLite con WAL mode (predefinito zero-config) o PostgreSQL con estensione `pgvector`.
- **Retrieval & NLP**: Rank-BM25, Sentence-Transformers (PyTorch), HuggingFace Cross-Encoders, Docling, PyMuPDF, OpenPyXL, python-docx.
- **LLM Engine**: Ollama (locale), vLLM, oppure connettori OpenAI-compatible / Azure / Anthropic.

### Frontend
- **Linguaggio & Framework**: TypeScript, React 18, Vite.
- **Design & Stile**: Tailwind CSS, Lucide Icons, Dark & Light theme responsive.
- **Comunicazione**: Fetch API, EventSource (SSE), Axios per streaming e upload concorrenti.

### Qualità del Codice & CI/CD
- **Testing**: 88+ test Pytest (unitari, d'integrazione, concorrenza, sicurezza e parità env), 68+ test Vitest frontend, suite E2E Playwright.
- **Linter & Formatter**: Ruff (0 errori, regole PEP8 e type-check rigorosi).
- **Validazione OpenAPI**: 185 route con contratti API completamente tipizzati.

---

## 9. Modalità di Installazione & Esecuzione

### Opzione A: Docker Compose (Consigliata per Produzione)
È sufficiente un singolo comando per avviare l'intero stack (Backend, Frontend e reverse proxy):
```bash
docker compose up -d
```
L'applicazione risponderà all'indirizzo `http://localhost:8000` (o porta configurata nel file `.env`).

### Opzione B: Installazione Locale Standalone (Windows / Linux)
1. **Configurazione Ambiente Python**:
   ```powershell
   python -m venv .venv-ermes
   .venv-ermes\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Avvio Backend**:
   ```powershell
   uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
   ```
3. **Avvio Frontend**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

---

## 10. Indice della Documentazione del Progetto

Per consultare approfondimenti specifici, fare riferimento ai file dedicati nella cartella `docs/`:

- 📖 **Guida Operativa Aziendale**: [`docs/GUIDA_OPERATIVA_AZIENDA.md`](GUIDA_OPERATIVA_AZIENDA.md) — Istruzioni per sistemisti IT, deploy Docker, configurazione Active Directory / OIDC e backup.
- 📊 **Catalogo Asset per Presentazioni**: [`docs/POWERPOINT_ASSETS.md`](POWERPOINT_ASSETS.md) — Mappatura degli screenshot e loghi per slide deck commerciali o executive.
- 🛡️ **Modello delle Minacce**: [`docs/THREAT_MODEL.md`](THREAT_MODEL.md) — Analisi dei vettori di attacco (STRIDE) e misure di mitigazione implementate.
- 🔧 **Manuale Operativo e Troubleshooting**: [`docs/RUNBOOK.md`](RUNBOOK.md) — Procedure di disaster recovery, diagnostica e monitoraggio dello stato di salute.
- 📈 **Valutazione del Retrieval**: [`docs/RETRIEVAL_EVALUATION.md`](RETRIEVAL_EVALUATION.md) — Metriche di accuratezza su golden dataset, benchmarking e percentuali di astensione.
- 📑 **Tesina e Specifiche Dettagliate**: [`docs/TESINA_FINALE_ITS_ERMES.md`](TESINA_FINALE_ITS_ERMES.md) — Documentazione accademica e tecnica approfondita su tutti i moduli dell'architettura.
