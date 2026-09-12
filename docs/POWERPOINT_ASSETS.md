# 📊 Ermes Knowledge — Guida Asset & Struttura Slide per Presentazione PowerPoint

Questa guida raccoglie e organizza **tutti gli asset visivi, loghi, screenshot ad alta risoluzione e diagrammi architetturali** presenti nel repository `Ermes Knowledge (Ermes-Librarian)`, pronti per essere inseriti in una presentazione PowerPoint aziendale rivolta a stakeholder, management o reparti IT.

---

## 🗂️ Mappa Rapida dei File Immagine

| Tipologia | Percorso File | Descrizione / Utilizzo Consigliato |
|---|---|---|
| **Logo Ufficiale** | [`assets/ermes-knowledge-icon.png`](../assets/ermes-knowledge-icon.png) | Icona ad alta risoluzione di Ermes Knowledge |
| **Mascotte / Brand** | [`Ermes.png`](../Ermes.png) | Logo esteso Ermes per copertine o slide di chiusura |
| **Hero Image** | [`frontend/src/assets/hero.png`](../frontend/src/assets/hero.png) | Grafica d'impatto con tema intelligenza documentale |
| **Sfondo / Texture** | [`frontend/public/assets/ermes-knowledge-atmosphere.png`](../frontend/public/assets/ermes-knowledge-atmosphere.png) | Background moderno da usare come sfondo per slide scure |
| **Screenshot Login** | [`docs/screenshots/01-login-screen.png`](screenshots/01-login-screen.png) | Pagina di autenticazione enterprise (OIDC / SSO / Locale) |
| **Screenshot Chat** | [`docs/screenshots/02-chat-interface.png`](screenshots/02-chat-interface.png) | UI principale di chat con domande contestuali e prompt |
| **Screenshot Citazioni** | [`docs/screenshots/assistant-with-citations.png`](screenshots/assistant-with-citations.png) | Risposta RAG con citazioni documentali cliccabili e verificabili |
| **Screenshot Librerie** | [`docs/screenshots/03-libraries-management.png`](screenshots/03-libraries-management.png) | Panoramica delle librerie documentali per dipartimento |
| **Screenshot Documenti & ACL** | [`docs/screenshots/libraries-and-documents.png`](screenshots/libraries-and-documents.png) | Dettaglio documenti, ingestion, permessi e formati (PDF, DOCX, XLSX) |
| **Screenshot Analytics** | [`docs/screenshots/04-analytics-dashboard.png`](screenshots/04-analytics-dashboard.png) | Cruscotto analitico con query per libreria, latenze e token |
| **Screenshot Governance** | [`docs/screenshots/05-admin-governance.png`](screenshots/05-admin-governance.png) | Gestione utenti, ruoli RBAC (Admin, Editor, Reader) e audit |
| **Screenshot Integrità Audit** | [`docs/screenshots/audit-log-integrity.png`](screenshots/audit-log-integrity.png) | Verifica crittografica tamper-evident del registro audit |
| **Demo Animata** | [`docs/assets/demo.gif`](assets/demo.gif) | Animazione completa del flusso di interrogazione |

---

## 🖥️ Struttura Consigliata per le Slide di Presentazione (Deck Aziendale)

### Slide 1: Copertina & Titolo
* **Titolo**: *Ermes Knowledge — La Piattaforma RAG Enterprise Sovrana e Verificabile*
* **Sottotitolo**: *Accesso sicuro, istantaneo e tracciabile al patrimonio documentale aziendale*
* **Asset da inserire**:
  * [`assets/ermes-knowledge-icon.png`](../assets/ermes-knowledge-icon.png) o [`Ermes.png`](../Ermes.png) centrato o in alto a sinistra.
  * *Speaker notes*: Presentare Ermes come la soluzione enterprise per valorizzare i documenti aziendali senza rischi di data leakage o allucinazioni dei modelli.

---

### Slide 2: Il Problema e la Soluzione
* **Titolo**: *Dalla frammentazione informativa alla certezza del dato*
* **Punti Chiave**:
  * **Problema**: File sparsi tra cartelle di rete, SharePoint e NAS; perdite di tempo nella ricerca; timore di fughe dati con ChatGPT/cloud pubblici.
  * **Soluzione**: RAG privato e sovrano (on-premise o cloud privato), risposte con **citazioni esatte**, zero retention esterna.
* **Asset da inserire**:
  * [`frontend/src/assets/hero.png`](../frontend/src/assets/hero.png) a lato della slide.

---

### Slide 3: L'Esperienza Utente & Chat con Evidenze
* **Titolo**: *Interfaccia Conversazionale Evidence-First*
* **Punti Chiave**:
  * Risposte in streaming ultra-veloce (SSE).
  * Principio di verificabilità: ogni affermazione include la citazione alla pagina e al file originale.
  * Blocco automatico delle allucinazioni (se la fonte non contiene la risposta, il sistema lo dichiara).
  * Export della conversazione in Markdown e copia delle citazioni con un clic.
* **Asset da inserire**:
  * [`docs/screenshots/02-chat-interface.png`](screenshots/02-chat-interface.png)
  * Inset / zoom su [`docs/screenshots/assistant-with-citations.png`](screenshots/assistant-with-citations.png).

---

### Slide 4: Gestione della Conoscenza e Ingestion Multi-Formato
* **Titolo**: *Librerie Dipartimentali & Pipeline di Ingestion*
* **Punti Chiave**:
  * Segmentazione della conoscenza per team (HR, Legal, R&D, Operations).
  * Supporto nativo per PDF, DOCX, XLSX, TXT, Markdown, HTML.
  * Riconoscimento acronimi e glossario dinamico aziendale (es. "SLA" -> "Service Level Agreement").
  * File watcher automatico su cartelle condivise (SMB/NAS).
* **Asset da inserire**:
  * [`docs/screenshots/03-libraries-management.png`](screenshots/03-libraries-management.png)
  * [`docs/screenshots/libraries-and-documents.png`](screenshots/libraries-and-documents.png)

---

### Slide 5: Architettura Tecnica & Sovranità dei Dati
* **Titolo**: *Architettura Enterprise Resiliente & Decoupled*
* **Punti Chiave**:
  * **Separazione Control Plane vs Data Plane**: i documenti e gli indici restano isolati.
  * **Retrieval Ibrido**: BM25 Lessicale + Vector Search + Reranker neurale Cross-Encoder.
  * **Modelli Flessibili**: Esecuzione 100% locale su GPU/CPU (Ollama, vLLM) oppure connettori enterprise (Azure OpenAI, AWS Bedrock, Mistral).
* **Asset / Diagramma consigliato**:

```
[ Browser Web / API Client ]
             │ (HTTPS / OIDC)
      ┌──────▼───────────────────────┐
      │  FastAPI Gateway & Auth RBAC │
      └──────┬───────────────────────┘
             ├──────────────────────────┬────────────────────────┐
             ▼                          ▼                        ▼
    [ Hybrid Retrieval ]      [ Dynamic Glossary ]       [ Ingestion Pipeline ]
  (BM25 + Vector + Rerank)    (Config/Synonyms Engine)  (Docling, OCR, Chunker)
             │
             ▼
    [ Evidence Verifier ] ──► [ LLM Sovrano / Ollama / API ]
             │
             ▼
    [ Risposta Verificata con Citazioni Puntuali ]
```

---

### Slide 6: Sicurezza, Governance & Audit Trail Immutabile
* **Titolo**: *Sicurezza Fail-Closed, RBAC e Conformità GDPR*
* **Punti Chiave**:
  * Controllo accessi a grana fine (Admin, Editor, Reader) e ACL per documento.
  * Integrazione nativa SSO/OIDC (Microsoft Entra ID, Keycloak, Google Workspace).
  * **Audit Log Crittografico**: ogni query e accesso è registrato in una catena hash immutabile (anti-manomissione).
  * DLP & Guardrails: mascheramento automatico PII / codici fiscali / IBAN.
* **Asset da inserire**:
  * [`docs/screenshots/05-admin-governance.png`](screenshots/05-admin-governance.png)
  * Inset su [`docs/screenshots/audit-log-integrity.png`](screenshots/audit-log-integrity.png).

---

### Slide 7: Analytics, Monitoraggio e Controllo dei Costi
* **Titolo**: *Osservabilità Completa e Metriche Operative*
* **Punti Chiave**:
  * Monitoraggio delle domande frequenti, latenze p95 e volumi di traffico.
  * Tracciamento consumo token ed efficienza del retrieval.
  * Esportazione metriche compatibile con Prometheus / Grafana.
* **Asset da inserire**:
  * [`docs/screenshots/04-analytics-dashboard.png`](screenshots/04-analytics-dashboard.png)

---

### Slide 8: Deployment e Integrazione Aziendale
* **Titolo**: *Installazione Semplice, Flessibile e Standalone*
* **Punti Chiave**:
  * **Docker Compose**: Avvio con un singolo comando (`docker compose up -d`).
  * **Bare-metal Windows / Linux**: Funziona direttamente come servizio di sistema o task scheduler.
  * Requisiti di sistema scalabili (da un singolo mini-PC / VM per piccoli uffici a cluster con GPU per migliaia di utenti).
  * Backup & Disaster Recovery con script automatizzati.

---

### Slide 9: Demo Live / Conclusione & Q&A
* **Titolo**: *Ermes Knowledge: Il Tuo Esperto Aziendale Sempre Disponibile*
* **Asset da inserire**:
  * [`docs/assets/demo.gif`](assets/demo.gif) o demo live del browser.
  * Logo [`Ermes.png`](../Ermes.png).
