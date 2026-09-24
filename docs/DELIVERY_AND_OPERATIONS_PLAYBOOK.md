# ERMES Librarian — Delivery, Deployment & Operations Playbook

Questo documento è il **manuale operativo e di delivery aziendale** per ingegneri DevOps, Solution Architects, IT Operation Engineers e Delivery Managers responsabili dell'implementazione, manutenzione e gestione in produzione della piattaforma **ERMES Librarian**.

---

## 1. Modelli di Delivery Tecnico

ERMES supporta tre architetture di deployment certificate per soddisfare ogni tipologia di cliente, dal piccolo studio professionale all'istituto bancario multi-sede.

```
                    ┌─────────────────────────────────────────┐
                    │       ERMES Delivery Continuum          │
                    └─────────────────────────────────────────┘
                                         │
         ┌───────────────────────────────┼──────────────────────────────┐
         ▼                               ▼                              ▼
  [Modello 1: Small/Med]        [Modello 2: Managed VPC]      [Modello 3: Enterprise K8s]
  Docker Compose On-Prem         Private Cloud (AWS/GCP/Azure)  Kubernetes Helm Chart
  • Server Linux Standalone      • Istanza EC2/GCE/VM           • Multi-replica API + HPA
  • Zero-config SQLite/Postgres  • Managed PostgreSQL (RDS)     • Decoupled Worker Ingestion
  • Setup in 30 minuti           • S3 / GCS Storage             • OIDC / SCIM + Prometheus
```

---

### Modello 1: On-Premise Docker Appliance (Small / Medium)
Ideale per clienti con requisiti di sovranità del dato, server locale on-premise o ambienti air-gapped/firewalled.

- **Stack**: Docker Engine 24+ e Docker Compose V2.
- **Componenti containerizzati**:
  - `ermes-api`: Web server FastAPI con Uvicorn (HTTP port 8000).
  - `ermes-ui`: Frontend SPA Vite/React servito via NGINX (HTTP port 3000 o 80).
  - `ermes-worker`: Processo di background ingestion asincrono (`scripts/run_worker.py`).
  - `postgres` (opzionale): PostgreSQL 16 con estensione pgvector, oppure SQLite su volume persistente.
- **Requisiti Hardware Minimi**:
  - CPU: 4 vCPU
  - RAM: 8 GB (16 GB consigliati se si utilizzano reranker o embedding locali)
  - Storage: 100 GB SSD NVMe
  - SO: Ubuntu 22.04 LTS / Debian 12 / RHEL 9

#### Procedura di Deployment Modello 1:
```bash
# 1. Clona o trasferisci il pacchetto di release
tar -xzvf ermes-librarian-v1.0.0.tar.gz
cd ermes-librarian

# 2. Configura le variabili d'ambiente
cp deploy/docker/.env.example .env
nano .env  # Inserisci le chiavi OpenAI/Azure/Ollama e JWT_SECRET

# 3. Avvia lo stack
docker compose up -d

# 4. Verifica lo stato dei container
docker compose ps
curl http://localhost:8000/api/v1/health
```

---

### Modello 2: Managed Private Cloud / Dedicated VPC (Medium / Large)
Ideale per clienti enterprise che richiedono un'istanza dedicata e isolata ospitata su cloud (AWS, Google Cloud o Microsoft Azure) gestita tramite SLA di supporto.

- **Architettura**:
  - Compute: Macchina virtuale dedicata (es. AWS `c6i.xlarge` o GCP `c3-standard-4`) o container group (ECS / Cloud Run).
  - Database: Managed PostgreSQL (AWS RDS / GCP Cloud SQL) con backup automatizzati Point-In-Time Recovery (PITR).
  - Storage Documentale: Bucket crittografato (AWS S3 con SSE-KMS o Google Cloud Storage).
  - Networking: VPC isolata con Security Groups ristretti e certificato TLS/SSL gestito tramite Let's Encrypt o AWS ACM.

---

### Modello 3: Enterprise Kubernetes via Helm (Enterprise / Tier 3)
Architettura cloud-native conforme agli standard di sicurezza bancari e corporate IT, con alta affidabilità, autoscaling orizzontale e separazione dei privilegi.

- **Helm Chart**: Localizzato in `deploy/helm/ermes-knowledge`.
- **Caratteristiche di Sicurezza & Resilienza**:
  - **Non-root execution**: Tutti i pod girano con UID 10001 (`appuser`), `readOnlyRootFilesystem: false` (o true con mount effimeri), `allowPrivilegeEscalation: false`, `capabilities: drop: [ALL]`.
  - **Horizontal Pod Autoscaling (HPA)**: Scala da 2 a 10 repliche API in base al carico CPU/Memoria.
  - **Decoupled Worker Deployment**: L'ingestion asincrona ad alta intensità computazionale è isolata su nodi worker dedicati (`worker-deployment.yaml`), garantendo che il parsing di PDF da centinaia di pagine non degradi la latenza delle risposte agli utenti.
  - **Ingress TLS**: Supporto nativo per ingress-nginx o traefik con terminazione TLS automatica via `cert-manager`.

#### Procedura di Installazione Helm:
```bash
# 1. Crea il namespace dedicato
kubectl create namespace ermes-system

# 2. Configura i secret (DB credentials, API Keys, JWT, OIDC)
kubectl create secret generic ermes-secrets \
  --namespace ermes-system \
  --from-literal=database-url="postgresql://ermes_user:SecureP@ss@postgres.internal:5432/ermes_db" \
  --from-literal=jwt-secret="enterprise-secure-jwt-random-token-64-chars" \
  --from-literal=openai-api-key="sk-proj-xxxxxx"

# 3. Personalizza il file values-enterprise.yaml
# Modifica ingress host, repliche e risorse

# 4. Esegui il deploy via Helm
helm upgrade --install ermes-knowledge ./deploy/helm/ermes-knowledge \
  --namespace ermes-system \
  -f deploy/helm/ermes-knowledge/values.yaml \
  -f deploy/helm/ermes-knowledge/values-enterprise.yaml

# 5. Verifica il rollout
kubectl rollout status deployment/ermes-knowledge -n ermes-system
kubectl rollout status deployment/ermes-knowledge-worker -n ermes-system
```

---

## 2. Pre-Flight Commissioning Checklist

Prima di consegnare l'ambiente al cliente o dichiarare la piattaforma operativa in produzione, il Delivery Engineer deve completare e siglare la seguente checklist:

| Check | Descrizione | Comando / Verifica | Esito |
|---|---|---|---|
| **P-01** | Porta 8000 (API) e 3000/443 (UI) raggiungibili | `curl -I http://<host>:8000/api/v1/health` | [ ] PASS |
| **P-02** | Security Headers HTTP OWASP presenti | `curl -s -D - http://<host>:8000/api/v1/health \| grep -E "X-Content-Type\|X-Frame"` | [ ] PASS |
| **P-03** | Database backend connesso con successo | Endpoint `/health` riporta `"database": "ok"` | [ ] PASS |
| **P-04** | Storage provider configurato e con quote valide | Endpoint `/health` riporta `"storage": "ok"` | [ ] PASS |
| **P-05** | Credenziali Admin predefinite modificate | Reset password utente default `admin@ermes.local` | [ ] PASS |
| **P-06** | Rate Limiting attivo ed effettivo | Eseguiti >60 req/min su `/api/v1/query` restituisce 429 | [ ] PASS |
| **P-07** | Corpus Demo / Storico Ingestionato | Eseguito `python scripts/seed_demo_corpus.py` | [ ] PASS |
| **P-08** | Smoke Test di Runtime Concluso con 0 Errori | `python scripts/smoke_test_runtime.py --base-url http://<host>:8000` | [ ] PASS |
| **P-09** | Validazione Demo & Acceptance Completa | `python scripts/validate_demo_readiness.py --base-url http://<host>:8000` | [ ] PASS |
| **P-10** | Backup schedulato e test di ripristino simulato | Snapshot DB e cartella uploads/ archiviati | [ ] PASS |

---

## 3. Guida all'Ingestion Iniziale e Popolamento Documentale

Per massimizzare il valore percepito dall'acquirente fin dal primo giorno ("Time-to-Value"), non consegnare mai un sistema vuoto. Popolare il sistema con i documenti aziendali del cliente o un corpus demo qualificato:

### Opzione A: Popolamento Rapido con Demo Corpus Realistico
```bash
# Esegue il seed di documenti tecnici, compliance e policy con account demo
python scripts/seed_demo_corpus.py --corpus demo_enterprise --target-files 25
```

### Opzione B: Importazione Massiva dei Documenti del Cliente
1. Raccogliere la documentazione aziendale (PDF, DOCX, XLSX, TXT, Markdown).
2. Posizionare i file nella directory temporanea di staging del server.
3. Utilizzare le API batch o il Connector Scheduler per importare e indicizzare automaticamente i contenuti con metadata e permessi di dipartimento corretti:
```bash
python scripts/run_connector_scheduler.py --once --source-dir /mnt/customer_docs/ingestion
```

---

## 4. Runbook Operativo e Manutenzione

### 4.1 Backup & Disaster Recovery (RPO < 1 ora, RTO < 30 minuti)

#### Backup di PostgreSQL (Tier Medium/Enterprise):
```bash
# Dump compresso del database relazionale, vettoriale e audit log
pg_dump -h <db-host> -U ermes_user -d ermes_db -F c -b -v -f /backups/ermes_db_$(date +%Y%m%d_%H%M%S).dump

# Sincronizzazione della directory storage documenti verso S3/Cloud Storage
aws s3 sync /var/ermes/storage s3://ermes-customer-backups/storage/ --delete
```

#### Backup di SQLite (Tier Small On-Premise):
```bash
# SQLite online safe backup via VACUUM INTO
sqlite3 /var/ermes/data/ermes.db "VACUUM INTO '/backups/ermes_$(date +%Y%m%d_%H%M%S).sqlite';"
tar -czvf /backups/storage_$(date +%Y%m%d_%H%M%S).tar.gz /var/ermes/storage
```

#### Procedura di Restore:
```bash
# 1. Arresta il traffico API
docker compose stop ermes-api ermes-worker

# 2. Ripristina il database
pg_restore -h <db-host> -U ermes_user -d ermes_db -v -c /backups/ermes_db_YYYYMMDD_HHMMSS.dump

# 3. Ripristina i file
aws s3 sync s3://ermes-customer-backups/storage/ /var/ermes/storage

# 4. Riavvia i servizi
docker compose start ermes-api ermes-worker
curl http://localhost:8000/api/v1/health
```

---

### 4.2 Migrazione da SQLite a PostgreSQL
Quando un cliente Small cresce verso il tier Medium/Enterprise, il passaggio da SQLite a PostgreSQL avviene senza perdita di dati tramite il tool integrato:

```bash
# Esecuzione della migrazione con validazione checksum e report
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path /var/ermes/data/ermes.db \
  --postgres-url postgresql://ermes_user:SecureP@ss@postgres.internal:5432/ermes_db \
  --verify \
  --report-out /var/ermes/migration_report.json
```

---

### 4.3 Monitoraggio e Metriche in Produzione
ERMES espone metriche Prometheus al path `/api/v1/metrics`:
- `ermes_http_requests_total`: Contatore delle richieste HTTP suddiviso per route, metodo e status code.
- `ermes_http_request_duration_seconds`: Istogramma delle latenze end-to-end (p50, p95, p99).
- `ermes_ingestion_tasks_total`: Conteggio dei documenti processati, completati e falliti.
- `ermes_retrieval_latency_seconds`: Tempo speso nel vector search e re-ranking.
- `ermes_llm_tokens_total`: Monitoraggio del consumo token (prompt e completion) per controllo costi.

Endpoint di controllo salute da configurare in UptimeRobot / Datadog / CloudWatch:
- **Liveness probe**: `GET /api/v1/health` (restituisce 200 OK se l'applicazione risponde).
- **Readiness probe**: `GET /api/v1/health?deep=true` (verifica connettività DB, vector store e filesystem).

---

### 4.4 Procedura di Aggiornamento Software (Zero-Downtime)

#### In Kubernetes (Rolling Update):
```bash
# 1. Aggiorna il tag immagine nei values o via CLI
helm upgrade ermes-knowledge ./deploy/helm/ermes-knowledge \
  --namespace ermes-system \
  --reuse-values \
  --set image.tag=v1.1.0

# 2. Monitora l'avanzamento dei pod
kubectl rollout status deployment/ermes-knowledge -n ermes-system
```

#### In Docker Compose (Blue/Green manuale o Fast Restart):
```bash
# 1. Effettua il pull della nuova immagine
docker compose pull ermes-api ermes-worker

# 2. Riavvia con ricreazione dei container mantenendo i volumi persistenti
docker compose up -d --no-deps ermes-api ermes-worker

# 3. Verifica l'allineamento dello schema
docker compose exec ermes-api python scripts/smoke_test_runtime.py --base-url http://localhost:8000
```

---

## 5. Matrice di Troubleshooting & Risoluzione Rapida Incidenti

| Sintomo | Causa Probabile | Azione Correttiva Immediata |
|---|---|---|
| **HTTP 401 Unauthorized persistente** | Token JWT scaduto o `JWT_SECRET` modificato | Rigenerare token con credenziali o riverificare la coerenza di `JWT_SECRET` nelle variabili d'ambiente. |
| **HTTP 429 Too Many Requests** | Limite rate limiting superato da IP o utente | Verificare chi sta inviando richieste massive; se legittimo, aumentare temporaneamente `RATE_LIMIT_PER_MINUTE` in `.env`. |
| **Incomplete Ingestion / Documenti in Pending** | Worker arrestato o memoria insufficiente | Verificare lo stato del container `ermes-worker` con `docker compose logs -f ermes-worker`; verificare RAM disponibile sul server. |
| **Errore connessione LLM (Timeout / 502)** | Rate limit provider AI o credenziali scadute | Controllare quote sul portale OpenAI/Azure o stato del container Ollama locale (`systemctl status ollama`). |
| **Database Lock su SQLite** | Concorrenza di scrittura elevata su SQLite | Verificare che WAL mode sia abilitata; consigliare il passaggio a PostgreSQL con `scripts/migrate_sqlite_to_postgres.py`. |

---
*Documento redatto dal team Senior Architecture & DevOps — Versione 1.0 Enterprise.*
