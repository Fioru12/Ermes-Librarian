# Manuale Utente - Ermes Enterprise Knowledge Hub

## Prerequisiti

- **Python 3.14+** con `.venv` creato
- **Ollama** in esecuzione con modelli:
  - `qwen3.5:4b` (~3.4GB, default, ~10s risposta)
  - `qwen3.5:9b` (~6.6GB, qualita, ~1min risposta)
  - `bge-m3` (~1.2GB, embeddings 1024d)
- **Documenti** da indicizzare in `documenti/<modulo>/`

## Avvio rapido

### Windows (doppio click)
```bat
AVVIA_DIRETTO.bat
```

### Manuale
```bash
# Avvia Ollama (se non già in esecuzione)
ollama serve

# Attiva virtual environment
.venv\Scripts\activate

# Avvia Streamlit (frontend)
streamlit run app.py

# Avvia FastAPI (API REST, opzionale)
uvicorn api:app --host 127.0.0.1 --port 8503
```

Apri `http://127.0.0.1:8502` nel browser.

### Docker
```bash
docker compose up -d
```
Servizi: Streamlit (8502), FastAPI (8503), Ollama (11434).

## Interfaccia

### Sidebar (sinistra)

| Controllo | Descrizione |
|-----------|-------------|
| Tema | Alterna tema scuro/chiaro (Deep Enterprise) |
| Modello LLM | `Qwen3.5 4B` (veloce) o `Qwen3.5 9B` (qualita) |
| Area di lavoro | Modulo documentale (es. WinSarp) |
| Stato sistema | Health check: Ollama, ChromaDB, documenti |
| Documenti | File indicizzati per il modulo attivo |
| Dashboard KPI | Sessioni, query, tempo medio, eval scores |
| Manutenzione | Re-indicizza, cancella indice, nuova conversazione |

### Area principale

- **Header**: modulo attivo, modello, modalita operativa
- **Modalita operativa**: `Recupero`, `Generazione`, `Analisi`
- **Chat**: scrivi una domanda e premi Invio

## Modalita operative

### Recupero (RAG classico)
Interroga i documenti indicizzati. Il sistema usa un **hybrid retriever** che combina:
1. **Lookup KG**: cerca per ID o nome formula nel Knowledge Graph
2. **Ricerca vettoriale**: semanticamente nei documenti indicizzati

### Generazione formule WinSarp
In modalita Generazione, produce codice WinSarp seguendo la grammatica del catalogo.
Il sistema include:
- Few-Shot contestuale (14 esempi + formule simili dal KG)
- Auto-correzione (max 2 retry con grammatica iniettata)

### Analisi formule WinSarp
Analisi approfondita delle formule con navigazione del Knowledge Graph.

## Knowledge Graph

Il grafo delle formule WinSarp contiene:
- **27 formule** con metadati completi (ID, nome, tipo, codice, campi, chiamate)
- **27 archi** di relazione (calls_r, calls_p)
- Ricerca per: ID, nome, tipo, campo, operatore
- Navigazione: chiama/chiamata da, catene di chiamate

## API REST

```bash
# Query RAG
curl -X POST http://127.0.0.1:8503/query \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query": "domanda", "module": "WinSarp"}'

# Health check
curl http://127.0.0.1:8503/health

# Knowledge Graph
curl http://127.0.0.1:8503/modules/WinSarp/graph/stats
curl http://127.0.0.1:8503/modules/WinSarp/graph/search?q=principale
curl http://127.0.0.1:8503/modules/WinSarp/graph/formula/120
```

## Configurazione (.env)

```env
# Modelli
ERMES_MODEL=qwen3.5:4b
ERMES_EMBED_MODEL=bge-m3

# Server
OLLAMA_HOST=127.0.0.1:11434
STREAMLIT_PORT=8502
API_PORT=8503

# Sicurezza
ADMIN_USER=admin
ADMIN_PASS=admin
API_KEY=chiave-api-secura
```

## Evaluation

Il sistema include un framework di evaluation con 50 query gold set:

```bash
# Esegui evaluation (subset)
.venv\Scripts\python evaluation/run_eval.py --limit 10

# Esegui evaluation completa
.venv\Scripts\python evaluation/run_eval.py

# Valida gold set
.venv\Scripts\python -m tests.test_gold_set
```

### Risultati (qwen3.5:4b + hybrid retriever + num_ctx=16K)

| Categoria | Pass Rate |
|-----------|-----------|
| field_lookup | 100% |
| retrieval_by_type | 100% |
| retrieval_by_id | 100% |
| retrieval_by_name | 100% |
| relationship_calls | 100% |
| relationship_callers | 100% |
| **Totale** | **100%** |

### Risultati (qwen3.5:9b + hybrid retriever)

| Metrica | Valore |
|---------|--------|
| Pass rate | 100% |
| Avg keyword score | 1.00 |

## Amministrazione

### Login admin
Le credenziali admin sono in `.env` (`ADMIN_USER`, `ADMIN_PASS`).
Dopo il login, la sidebar mostra sezioni admin:
- Gestione utenti (ruoli: admin, viewer)
- Audit log (HMAC, SHA-256)
- Manutenzione documenti

### Audit log
Ogni operazione admin viene registrata con:
- Timestamp, azione, attore, dettagli
- HMAC-SHA256 per integrita
- File locking per concorrenza

## Sicurezza

- **Autenticazione**: HMAC-based con PBKDF2-SHA256
- **Path traversal protection**: validazione percorsi file
- **File upload**: validazione dimensione, tipo, contenuto
- **Input validation**: sanitizzazione query utente
- **Audit logging**: tracciamento completo operazioni admin

## Struttura progetto

```
ProgettoRAG_DEV/
├── app.py                 # Entry point Streamlit
├── api.py                 # API REST FastAPI
├── config.py              # Configurazione centralizzata
├── core/
│   ├── rag_engine.py      # LlamaIndex, ChromaDB, hybrid retriever
│   ├── knowledge_graph.py # Knowledge Graph 27 formule
│   ├── formula_builder.py # Generazione formule WinSarp
│   ├── business_assistant.py # Intent recognition LLM-based
│   ├── agent_runner.py    # Agente multi-step
│   └── governance.py      # Auth, audit, security
├── ui/
│   ├── chat_handler.py    # Streaming, auto-correzione
│   ├── sidebar_ui.py      # Sidebar, health check
│   ├── monitor_dashboard.py # Dashboard KPI
│   └── theme.py           # Tema Deep Enterprise
├── modules/
│   ├── base.py            # Classe astratta moduli
│   └── winsarp.py         # Modulo WinSarp (prompt, validazione)
├── evaluation/
│   ├── gold_set.json      # 50 query di evaluation
│   └── run_eval.py        # Script evaluation automatico
├── tests/                 # 173 test
├── data/
│   └── winsarp_graph.json # Grafo persistito
├── Dockerfile             # Python 3.14, multi-stage
└── docker-compose.yml     # Config completa
```

## Troubleshooting

| Problema | Soluzione |
|----------|-----------|
| "Ollama non raggiungibile" | Avvia Ollama: `ollama serve` |
| "Modelli mancanti" | `ollama pull qwen3.5:4b && ollama pull bge-m3` |
| "Empty Response" | Verifica che `num_ctx` sia >= 16384 nel config |
| Nessun documento trovato | Metti file in `documenti/<modulo>/` e re-indicizza |
| Indice ChromaDB obsoleto | Click "Aggiorna" nella sidebar o cancella `chroma_db/` |
| Errori di import | `pip install -r requirements.txt` |
| Porta 8502 occupata | Cambia porta: `streamlit run app.py --server.port 8503` |

## Limiti noti

- **Latenza CPU**: ~10s (4B) o ~1min (9b) per query su CPU senza GPU
- **Query complesse**: le relazioni multi-hop funzionano meglio con qwen3.5:9b
