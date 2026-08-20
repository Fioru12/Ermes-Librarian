# Go-Live Checklist (LAN + Locale)

## 1) Prerequisiti host

- [ ] PC server con Python e Ollama installati
- [ ] Modelli Ollama presenti:
  - [ ] `qwen2.5:7b`
  - [ ] `nomic-embed-text`
- [ ] Cartelle runtime disponibili:
  - [ ] `documenti/`
  - [ ] `chroma_db/`
  - [ ] `logs/`

## 2) Configurazione sicurezza minima

- [ ] `OLLAMA_HOST` resta `http://127.0.0.1:11434`
- [ ] Streamlit esposto in LAN solo se necessario (`0.0.0.0`)
- [ ] Firewall aperto solo su rete privata per la porta applicativa (es. 8502)
- [ ] Impostata password admin:
  - [ ] `WINSARP_ADMIN_USERNAME`
  - [ ] `WINSARP_ADMIN_PASSWORD`

## 3) Verifica funzionale

- [ ] Upload documento da pannello admin
- [ ] Reindicizzazione modulo
- [ ] Query con risposta ancorata a fonti
- [ ] Caso “non trovato” con fallback corretto
- [ ] Download log conversazione
- [ ] Audit admin scritto in `logs/audit_admin.jsonl`

## 4) Verifica da client LAN

- [ ] Accesso da altro PC a `http://<IP_SERVER>:8502`
- [ ] Query end-to-end completata con risposta
- [ ] Nessun accesso diretto a Ollama dai client LAN

## 5) Operazioni e manutenzione

- [ ] Backup periodico di:
  - [ ] `documenti/`
  - [ ] `security/users.json`
  - [ ] `chroma_db/` (opzionale, ricostruibile)
  - [ ] `logs/` e `logs/audit_admin.jsonl`
- [ ] Verifica retention log (`WINSARP_LOG_RETENTION_DAYS`)
- [ ] Test rapidi (`pytest -q tests`) prima di ogni rilascio
