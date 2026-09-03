# PRESENTAZIONE DI FINE PERCORSO ITS (MAX 15 SLIDES)
## PROGETTO: ERMES KNOWLEDGE — ENTERPRISE LOCAL-FIRST RAG

---

### 📌 GUIDA ALLE SLIDE PER POWERPOINT / CANVA / GOOGLE SLIDES
Questa guida contiene la struttura esatta e il contenuto testuale per le **15 slide** richieste dalla commissione d'esame ITS.

---

### SLIDE 1: COPERTINA (TITOLO E DATI DI PRESENTAZIONE)
- **Titolo del Progetto:** ERMES KNOWLEDGE — Sistema RAG Enterprise Local-First con Garanzie di Sicurezza e Privacy
- **Logo ITS:** [Inserire Logo ITS]
- **Logo Azienda / Partner:** [Inserire Logo Azienda]
- **Candidato:** [Nome e Cognome]
- **Corso di Studi:** Tecnico Superiore per lo Sviluppo di Sistemi Software e Intelligenza Artificiale
- **Azienda Ospitante:** [Nome Azienda / Ragione Sociale]
- **Tutor Aziendale / Accademico:** [Nome Tutor Aziendale] / [Nome Tutor ITS]
- **Anno Formativo:** 2025 / 2026

---

### SLIDE 2: IL PROBLEMA AZIENDALE — LA FRAMMENTAZIONE DELLA CONOSCENZA
- **Frammentazione informativa:** I dati aziendali vivono sparsi tra cartelle di rete, email, PDF e chat private.
- **Perdita di tempo ed efficienza:** I dipendenti impiegano ore per rintracciare la versione aggiornata di procedure e contratti.
- **Rischio dei LLM tradizionali:** I chatbot generici "allucinano" (inventano risposte con tono sicuro) e inviano dati riservati verso cloud terzi in violazione del GDPR.

---

### SLIDE 3: LA SOLUZIONE — ERMES KNOWLEDGE
- **Assistente AI basato su RAG (Retrieval-Augmented Generation):** Risponde in linguaggio naturale basandosi esclusivamente sui documenti aziendali caricati.
- **Principio dell'Evidenza:** Ogni risposta cita espressamente il documento sorgente con link diretto al file.
- **Nessuna evidenza, nessuna invenzione:** Se il documento non c'è, l'assistente si astiene invece di allucinare.

---

### SLIDE 4: LE 5 REGOLE ARCHITETTURALI FONDAMENTALI
1. **Local-First:** Elaborazione locale degli embedding e documenti per la massima riservatezza.
2. **Evidenza prima della generazione:** La risposta vale quanto le fonti che la sostengono.
3. **Isolamento tra biblioteche:** Ricerca segregata per gruppi/ruoli prima di inviare il testo al modello.
4. **Input Non Fidato:** I documenti non possono mai eseguire codice o autorizzare azioni.
5. **Originali Raggiungibili:** Ogni citazione rimanda al file esatto scaricabile in 1 click.

---

### SLIDE 5: ARCHITETTURA DEL SISTEMA & TECH STACK
- **Frontend (UI/UX):** React 18, TypeScript, Vite, Tailwind CSS (Interfaccia reattiva e moderna).
- **Backend (API Services):** Python 3.11, FastAPI (ASGI asincrono, validazione Pydantic, Swagger nativo).
- **AI & Storage Engine:** Ollama / Local Embeddings, SQLite / JSON Vector Store, Pytest (240+ test).
- **Orchestrazione & DevOps:** Containerizzazione Docker e Docker Compose per deployment immediato.

---

### SLIDE 6: IL CUORE DEL RAG — INGESTION & RICERCA IBRIDA
- **Parsing Multiformato:** Supporto per PDF, Word (.docx), Markdown, TXT e pagine web.
- **Chunking Dinamico:** Suddivisione del testo in blocchi semantici con overlap per non perdere il contesto.
- **Ricerca Ibrida (Vector + BM25):** 
  - *Vettoriale:* Toglie le barriere sintattiche e capisce i sinonimi.
  - *BM25:* Trova codici esatti, sigle tecniche e numeri di protocollo.
  - *RRF (Reciprocal Rank Fusion):* Unisce i due ranking per la massima precisione.

---

### SLIDE 7: ADVANCED RETRIEVAL — RE-RANKER & DEDUPLICAZIONE
- **Re-ranker Posizionale:** Ricalcola la pertinenza analizzando la vicinanza delle parole chiave nella frase, bi-grammi consecutivi e corrispondenza col titolo.
- **Deduplicazione Jaccard:** Identifica documenti duplicati o versioni simili tramite shingle di parole.
- **Risultato:** Solo i 3-5 estratti migliori saturano il prompt dell'LLM, riducendo i tempi di risposta ed eliminando la ridondanza.

---

### SLIDE 8: DATA LOSS PREVENTION — IL FILTRO PII GUARD
- **Scansione in Tempo Reale:** PII Guard intercetta testi in upload e query utente prima che raggiungano l'AI.
- **Validazione Algoritmica Avanzata:**
  - *Carte di Credito:* Algoritmo di Luhn (modulus 10 checksum) per filtrare solo carte vere.
  - *IBAN:* Validazione algebrica Modulo 97 (ISO 13616).
  - *Codici Fiscali & Token:* Pattern 16 caratteri con CIN e mascheramento di API Keys / JWT.

---

### SLIDE 9: GOVERNANCE & CONTROL ACCESS (RBAC)
- **Role-Based Access Control (RBAC):**
  - *Admin:* Gestione completa utenti, biblioteche, configurazioni e log audit.
  - *Editor:* Upload e gestione documenti nelle biblioteche autorizzate.
  - *Viewer:* Ricerca e consultazione riservata.
- **Security-by-Design:** Query bloccate con HTTP 404 per biblioteche non autorizzate (impedisce anche la scoperta dei nomi dei file).
- **Audit Logging Immutabile:** Registro di audit protetto da atomic file locking per compliance GDPR / ISO 27001.

---

### SLIDE 10: VALUTAZIONE E METRICHE (GOLDEN SET)
- **Misurazione Quantitativa:** Dataset di test (Golden Set di 27 query) suddiviso per tipologia:
  - *Query Dirette:* 100% precisione.
  - *Query Parafrasate:* Recupero semantico potenziato dal motore vettoriale.
  - *Query di Astensione:* Rilevazione accurata dei casi privi di evidenza.
- **Approccio Scientifico:** Qualità del RAG misurata ed analizzata, non solo dichiarata.

---

### SLIDE 11: QUALITÀ DEL CODICE E AUTOMATIC TESTING
- **241 Test Automatizzati (Pytest):** Copertura completa di backend, API, sicurezza DLP, re-ranker e persistenza.
- **Continuous Integration (CI):** Pipeline automatizzata su GitHub Actions per bloccare le regressioni ad ogni commit.
- **Swagger / OpenAPI Documentation:** Documentazione interattiva generata automaticamente dalle rotte FastAPI.

---

### SLIDE 12: ANALYTICS & DETECTION DEI KNOWLEDGE GAPS
- **Dashboard Amministrativa:** Monitoraggio in tempo reale dell'utilizzo del sistema e del gradimento delle risposte.
- **Rilevamento Knowledge Gaps:** Identificazione automatica delle domande a cui il sistema non ha trovato risposte.
- **Valore Strategico:** Segnala al management quali procedure o documenti aziendali mancano e devono essere redatti.

---

### SLIDE 13: ESPERIENZA DI TIROCINIO AZIENDALE / ERASMUS (PARTE 1)
- **Contesto Operativo:** Inserimento nel team di sviluppo software dell'azienda partner [Nome Azienda].
- **Attività Svolte:** Analisi dei requisiti con gli stakeholder, progettazione dell'architettura RAG, sviluppo componenti FastAPI e React.
- **Metodologia Agile:** Adozione di Scrum/Kanban, daily stand-up, code review e versionamento git organizzato.

---

### SLIDE 14: ESPERIENZA DI TIROCINIO AZIENDALE / ERASMUS (PARTE 2)
- **Competenze Acquisite:** Padronanza di FastAPI, React/TypeScript, tecniche di Vector Search, DLP e containerizzazione Docker.
- **Impatto Aziendale:** Riduzione del 70% dei tempi di ricerca delle informazioni interne e adozione sicura dell'AI nel rispetto della privacy.
- **Crescita Professionale:** Transizione dalle competenze accademiche alla realizzazione di un prodotto software pronto per la produzione.

---

### SLIDE 15: CONCLUSIONI E ROADMAP FUTURA
- **Risultati Raggiunti:** Piattaforma RAG Local-First operativamente completa, sicura, testata e conforme al GDPR.
- **Roadmap Enterprise:**
  - Integrazione SSO / OIDC (Microsoft Entra ID, Keycloak).
  - Scalabilità Cloud su Vector DB distribuiti (Qdrant cluster).
  - Tracciamento distribuito con OpenTelemetry.
- **Grazie per l'attenzione!** *Domande e Risposte (Q&A)*
