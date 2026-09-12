# Guida Operativa di Distribuzione Aziendale — Ermes Knowledge

Questa guida fornisce al reparto IT, ai sistemisti e agli amministratori di sistema tutte le istruzioni necessarie per installare, configurare, proteggere e mantenere operativo **Ermes Knowledge** in ambiente aziendale.

---

## 1. Architettura e Componenti

Ermes Knowledge è una piattaforma documentale enterprise progettata secondo il paradigma **local-first** ed **evidence-first**:
- **Backend**: API REST e SSE asincrone su FastAPI / Python 3.11+.
- **Frontend**: Single Page Application reattiva in React 18 / TypeScript / Vite con TailwindCSS.
- **Motore di Ricerca Ibrido**: BM25/FTS5 (lessicale) integrato con embedding semantici e reranker neuronale/lessicale.
- **Motore di Inference (LLM)**:
  - *Default (Zero-Hardware)*: Modalità `evidence_only` (estrae solo i passaggi documentali verificati con citazioni, senza usare modelli generativi).
  - *Consigliato Locale (Massima Privacy)*: Istanza [Ollama](https://ollama.com/) on-premise con modello `qwen3.5:9b` o `qwen3.5:4b` + `nomic-embed-text` / `bge-m3`.
  - *Cloud Approvato*: OpenRouter, Azure OpenAI, Groq (richiede consenso esplicito).
- **Persistenza**:
  - *Singolo Server / On-Premise*: SQLite WAL locale (zero-config, predefinito).
  - *Cluster Distribuito*: PostgreSQL 16+ (attivabile con `ERMES_DATABASE_URL`).

---

## 2. Requisiti di Sistema

### Requisiti Minimi (Modalità Evidence-Only o con Cloud LLM)
- **CPU**: 4 vCPU
- **RAM**: 4–8 GB RAM
- **Disco**: 20 GB SSD
- **SO**: Linux (Ubuntu 22.04+ / Debian 12 / RHEL 9) oppure Windows Server 2022+ / Windows 11.

### Requisiti Consigliati (Inference Locale con Ollama)
- **CPU**: 8 vCPU
- **RAM**: 16–32 GB RAM
- **GPU**: NVIDIA RTX (minimo 8–12 GB VRAM per `qwen3.5:4b` / 16 GB per `qwen3.5:9b`) con CUDA 12+.
- **Disco**: 50–100 GB NVMe SSD.

---

## 3. Installazione e Avvio

### Opzione A: Distribuzione con Docker & Docker Compose (Consigliata)

1. Clonare il repository o copiare il pacchetto di rilascio sul server di destinazione:
   ```bash
   git clone <URL_REPOSITORY> ermes-knowledge
   cd ermes-knowledge
   ```

2. Creare e configurare il file di ambiente:
   ```bash
   cp .env.example .env
   ```

3. Modificare `.env` impostando una password amministrativa sicura:
   ```env
   ERMES_ADMIN_PASSWORD=TuaPasswordMoltoSicura!2026
   ERMES_API_KEY=ermes_chiave_segreta_generata_random
   ```

4. Avviare i container:
   ```bash
   # Avvio standard con SQLite locale:
   docker compose up -d

   # Oppure con cluster PostgreSQL dedicato:
   docker compose --profile postgres up -d
   ```

5. L'interfaccia sarà raggiungibile su `http://IP_SERVER:8502`.

---

### Opzione B: Installazione Diretta su Host / Windows Server

1. Assicurarsi di avere Python 3.11+ e Node.js 18+ installati.
2. Installare le dipendenze Python:
   ```bash
   pip install -e .
   ```
3. Compilare il frontend React:
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```
4. Verificare la configurazione:
   ```bash
   python -m config.validation
   ```
5. Avviare il server applicativo:
   ```bash
   uvicorn api:app --host 0.0.0.0 --port 8502 --workers 2
   ```

---

## 4. Configurazione della Sicurezza e Conformità GDPR

### Autenticazione & Ruoli (RBAC)
- **admin**: Accesso completo a gestione utenti, chiavi API, impostazioni DLP, provider LLM e backup.
- **editor**: Creazione biblioteche, caricamento/eliminazione documenti, gestione glossario.
- **viewer**: Sola consultazione e ricerca documentale sulle biblioteche assegnate.

### Protezione Dati Personali (DLP & Filtri PII)
In `.env` è possibile abilitare il mascheramento preventivo dei dati sensibili prima di qualsiasi elaborazione:
```env
ERMES_PII_FILTER_ENABLED=1
ERMES_DLP_AUDIT_ENABLED=1
```
Il modulo maschera in tempo reale:
- Codici Fiscali italiani
- Numeri di carta di credito (con validazione algoritmo di Luhn)
- Codici IBAN
- Token JWT e API Key
- Indirizzi email e numeri di telefono

### Autenticazione Centralizzata SSO / OIDC (Microsoft Entra ID / Azure AD)
Per consentire l'accesso aziendale con credenziali Microsoft 365:
```env
ERMES_OIDC_ENABLED=1
ERMES_OIDC_ISSUER=https://login.microsoftonline.com/<TENANT_ID>/v2.0
ERMES_OIDC_CLIENT_ID=<CLIENT_ID_APP>
ERMES_OIDC_CLIENT_SECRET=<CLIENT_SECRET>
ERMES_OIDC_AUDIENCE=<CLIENT_ID_APP>
```
I gruppi di sicurezza Azure AD possono essere mappati direttamente su ruoli e biblioteche tramite il pannello amministrativo.

---

## 5. Gestione del Glossario Aziendale & Sinonimi

Per far comprendere a Ermes la terminologia interna (sigle, acronimi, gergo contrattuale come *DDT, TFR, CCNL, WFH, DVR*):
1. Accedere a **Impostazioni Sistema** > **Glossario Aziendale & Sinonimi Dinamici**.
2. Inserire il termine e le sue espansioni equivalenti (es. `DDT` -> `documento di trasporto, bolla di consegna`).
3. Il motore espanderà automaticamente le query degli utenti durante la ricerca, massimizzando il ritrovamento dei documenti.
4. Il file è persistito in `config/synonyms.json` (personalizzabile con `ERMES_SYNONYMS_FILE`).

---

## 6. Connessione a Cartelle di Rete (NAS / SMB / SharePoint)

1. **Cartelle Condivise di Rete**:
   - Nel tab **Connettori**, inserire il percorso UNC o il mount locale (es. `\\nas-server\procedure_aziendali` o `/mnt/nas/procedure`).
   - Il daemon **Folder Watcher** integrato esegue periodicamente la scansione rilevando nuovi file o revisioni aggiornate in background.
2. **Microsoft SharePoint / OneDrive**:
   - Configurare in `.env` le credenziali `MS_GRAPH_TENANT_ID`, `MS_GRAPH_CLIENT_ID`, `MS_GRAPH_CLIENT_SECRET` e `MS_GRAPH_DRIVE_ID`.

---

## 7. Backup, Disaster Recovery e Monitoraggio

### Backup Automatico
Il sistema include uno scheduler di backup automatico configurato in `.env`:
```env
ERMES_BACKUP_ENABLED=1
ERMES_BACKUP_INTERVAL_HOURS=24
```
Gli archivi compressi cifrabili vengono salvati in `data/backups/` e contengono il database SQLite, i metadati, il glossario e la configurazione utenti.

### Monitoraggio Prometheus
Ermes espone metriche native per Prometheus su `/metrics`:
- Latenza di ricerca e recupero passaggi (`ermes_rag_retrieval_seconds`).
- Numero di query e tasso di astensione (`ermes_rag_questions_total`).
- Frequenza richieste HTTP e codici di stato (`http_requests_total`).
```env
ERMES_METRICS_TOKEN=tuo_token_segreto_prometheus
```

---

## 8. Checklist di Collaudo Finale prima del Go-Live

- [ ] `.env` configurato con password non di default (`CHANGE_ME` rimosso).
- [ ] Test di configurazione superato (`python -m config.validation`).
- [ ] Almeno una biblioteca tematica creata e popolata con documenti aziendali.
- [ ] Eseguita una query di test verificando la presenza delle citazioni e l'assenza di allucinazioni.
- [ ] Testata l'astensione (domanda fuori contesto: l'assistente deve dichiarare l'assenza di evidenza).
- [ ] Account utenti/editor configurati o SSO OIDC abilitato.
- [ ] Backup schedulato e verificato nella directory `data/backups/`.
