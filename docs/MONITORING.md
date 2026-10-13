# Monitoraggio

Ermes funziona senza alcuno strumento di monitoraggio. Questa guida descrive cosa espone l'applicazione, come vederlo con uno stack gratuito e come collegarlo a quello che un'azienda ha già.

## Cosa espone l'applicazione

| Segnale | Dove | Per chi |
|---|---|---|
| Metriche Prometheus | `GET /metrics` | chi gestisce l'infrastruttura |
| Salute del sistema | `GET /health` e pagina **Stato sistema** nell'interfaccia | amministratore |
| Registro di audit con catena SHA-256 | interfaccia amministrazione; inoltro a Syslog RFC 5424 o webhook HTTPS firmato | sicurezza e conformità |
| Log applicativi | file in `logs/`; in container sono in formato JSON (`ERMES_LOG_FORMAT=json`) | chi raccoglie i log |
| Tracing delle chiamate al modello | Langfuse, opzionale (`docker-compose.langfuse.yml`) | sviluppatori |

### Metriche (`core/metrics.py`)

- `ermes_http_requests_total` e `ermes_http_request_duration_seconds`: richieste e latenza.
- `ermes_rag_questions_total{outcome}`: domande per esito `answered`, `abstained` o `error`.
- `ermes_rag_retrieval_results`, `ermes_rag_retrieval_duration_seconds`, `ermes_rag_rerank_mode_total`: qualità e tempi del recupero.
- `ermes_evidence_verifier_total{outcome}`: quando il verificatore è `unavailable` le risposte non vengono controllate e l'astensione non è garantita. È la metrica da tenere d'occhio.
- `ermes_prompt_injection_flagged_total`, `ermes_question_rewrite_total`, `ermes_ingestion_jobs_total{status}`, `ermes_system_info`.

`/metrics` da un altro host richiede `ERMES_METRICS_TOKEN` (header `Authorization: Bearer ...`). Senza token risponde solo al loopback.

## Profilo opzionale: Prometheus, Alertmanager, Grafana

Tutti strumenti gratuiti e open source. Non fanno parte dell'installazione normale: si aggiungono con un secondo file di compose.

```bash
export ERMES_METRICS_TOKEN=$(openssl rand -hex 24)
export GRAFANA_ADMIN_PASSWORD='scegli-una-password'
export ALERT_WEBHOOK_URL='https://...'     # facoltativo
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

| Servizio | Indirizzo | Contenuto |
|---|---|---|
| Grafana | http://localhost:3001 (utente `admin`) | dashboard "Ermes Knowledge - Enterprise Monitoring", già collegata |
| Prometheus | http://localhost:9090 | metriche e regole di alert |
| Alertmanager | http://localhost:9093 | alert attivi e invii |

Scelte di sicurezza:
- Token e password sono obbligatori e senza valore di ripiego: senza le variabili Compose si ferma.
- Le tre porte sono pubblicate solo su `127.0.0.1`. Per aprirle alla rete mettile dietro il reverse proxy con autenticazione.
- L'URL del webhook è un segreto: entra da variabile d'ambiente, non finisce nel repository.

Senza `ALERT_WEBHOOK_URL` gli alert sono comunque visibili in Alertmanager e Grafana, ma non vengono inviati.

### Alert inclusi (`deploy/monitoring/alerts.yml`)

| Alert | Quando scatta | Gravità |
|---|---|---|
| `ErmesDown` | `/metrics` non risponde da 2 minuti | critica |
| `ErmesHighErrorRate` | oltre il 5% di errori 5xx per 10 minuti | critica |
| `ErmesSlowRequests` | il 95% delle richieste supera 3 s per 10 minuti | avviso |
| `ErmesEvidenceVerifierDegraded` | il verificatore non risponde | avviso |
| `ErmesQuestionErrors` | più di 5 domande in errore in 15 minuti | avviso |
| `ErmesIngestionFailures` | più di 3 documenti non indicizzati in 30 minuti | avviso |
| `ErmesHighAbstentionRate` | oltre il 50% di rifiuti per un'ora | informativa |

Le soglie sono un punto di partenza: adattale ai tuoi volumi. Per i passi da fare quando un alert scatta vedi [RUNBOOK.md](RUNBOOK.md), sezione "When something is wrong".

### Notifiche su Slack, Teams, Discord

Alertmanager invia un JSON generico. Per Slack, Teams o Discord usa un relay (n8n, Zapier o un piccolo servizio) che traduce il formato, oppure il receiver nativo di Alertmanager: modifica `deploy/monitoring/alertmanager.yml` aggiungendo `slack_configs` o `msteams_configs`.

## Se l'azienda ha già un proprio stack

Non serve il profilo qui sopra.

- **Prometheus esistente:** aggiungi un job che legge `/metrics` con il token, importa `deploy/monitoring/alerts.yml` come file di regole e `deploy/monitoring/grafana-dashboard.json` in Grafana.
- **Kubernetes:** il chart Helm è in `deploy/helm/ermes-knowledge/`.
- **SIEM (Splunk, Wazuh, Graylog, Elastic):** il registro di audit può essere inoltrato in tempo reale, in modo non bloccante (la copia locale resta la fonte di verità):
  - Syslog RFC 5424 su UDP: `ERMES_AUDIT_SYSLOG_HOST`, `ERMES_AUDIT_SYSLOG_PORT` (default 514), `ERMES_AUDIT_SYSLOG_FACILITY` (default `local0`);
  - webhook HTTPS: `ERMES_AUDIT_REMOTE_URL`, con `ERMES_AUDIT_REMOTE_TOKEN` per l'header Bearer.
- **Log centralizzati (Loki, Elastic):** i log del container sono già JSON, un collettore (Alloy, Promtail, Filebeat) può leggerli da Docker senza modifiche all'applicazione.

## Cosa non c'è

Non sono inclusi: uno stack di log (Loki, Elasticsearch/Kibana), OpenTelemetry per le trace distribuite, Sentry. Con un'applicazione sola e un worker le metriche e i log JSON bastano; se il sistema si dividerà in più servizi, le trace diventeranno utili.

## Verifica

`tests/test_monitoring_assets.py` fallisce se una regola di alert o un pannello della dashboard cita una metrica che non esiste più in `core/metrics.py`, se le porte non sono sul loopback o se un segreto ha un valore di default.
