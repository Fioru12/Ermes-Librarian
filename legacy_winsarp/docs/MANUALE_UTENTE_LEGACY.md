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
AVVIA_PRO.bat
```
Questo è il punto di avvio consigliato. In alternativa puoi usare `launch.py` oppure lanciare direttamente `uvicorn api:app --host 127.0.0.1 --port 8504`.

### Manuale
```bash
# Avvia Ollama (se non già in esecuzione)
ollama serve

# Attiva virtual environment
.venv\Scripts\activate

# Avvia backend (serve anche frontend precompilato)
uvicorn api:app --host 127.0.0.1 --port 8504
```

Apri `http://127.0.0.1:8504` nel browser.

### Docker
```bash
docker compose up -d
```
Servizi: Backend FastAPI (8504), Ollama (11434).

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
- **Catalogo WinSarp strutturato** con metadati, codice, campi e chiamate
- **Grafo delle dipendenze** con relazioni `calls_r`, `calls_p` e collegamenti di flusso
- Ricerca per: ID, nome, tipo, campo, operatore
- Navigazione: chiama/chiamata da, catene di chiamate

## API REST

```bash
# Query RAG
curl -X POST http://127.0.0.1:8504/query \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query": "domanda", "module": "WinSarp"}'

# Health check
curl http://127.0.0.1:8504/health

# Knowledge Graph
curl http://127.0.0.1:8504/modules/WinSarp/graph/stats
curl http://127.0.0.1:8504/modules/WinSarp/graph/search?q=principale
curl http://127.0.0.1:8504/modules/WinSarp/graph/formula/120
```

## Configurazione (.env)

```env
# Modelli
ERMES_MODEL=qwen3.5:4b
ERMES_EMBED_MODEL=bge-m3

# Server
OLLAMA_HOST=127.0.0.1:11434
ERMES_PORT=8504

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
├── api.py                 # Entry point FastAPI (uvicorn), retrocompat wrapper
├── api/                   # API moduli (auth, query, formule, documents, etc.)
├── frontend/              # UI React (Vite)
├── config.py              # Configurazione centralizzata
├── core/
│   ├── rag_engine.py      # LlamaIndex, ChromaDB, hybrid retriever
│   ├── knowledge_graph.py # Knowledge Graph formule
│   ├── formula_builder.py # Generazione formule WinSarp
│   ├── formula_booster.py # Post-processor formule
│   ├── intent_builder.py  # Classifica intenti + IR generation
│   ├── monitoring.py      # Monitoraggio e metriche
│   ├── backup_manager.py  # Backup/ripristino
│   ├── pii_filter.py      # Filtro PII (GDPR)
│   └── governance.py      # Auth, audit, security
├── core/ai/
│   ├── llm_bridge.py      # Bridge LLM (Ollama + OpenRouter)
│   ├── chain_of_thought.py # Pipeline 4-step
│   ├── providers/         # Registry provider LLM
│   ├── response_cache.py  # Cache risposte
│   └── semantic_cache.py  # Cache semantica
├── core/winsarp/
│   ├── catalog.py         # Parsing catalogo WinSarp
│   ├── knowledge_graph.py # Grafo formule
│   ├── patterns.py        # Pattern library (44 codici)
│   ├── parser_rules.py    # Regole regex centralizzate
│   ├── linter.py          # Linter statico
│   ├── validator.py       # Validatore Lark
│   └── workbook_retriever.py # Recupero workbook
├── modules/
│   ├── winsarp/           # Modulo WinSarp (package)
│   ├── generic.py         # Modulo generico
│   └── base.py            # Classe astratta moduli
├── evaluation/
│   ├── gold_set.json      # 50 query di evaluation
│   └── run_eval.py        # Script evaluation automatico
├── tests/                 # 871 test
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
| Porta 8502 occupata | Cambia porta: `$env:ERMES_PORT="8504"; uvicorn api:app --port 8504` |

## Limiti noti

- **Latenza CPU**: ~10s (4B) o ~1min (9b) per query su CPU senza GPU
- **Query complesse**: le relazioni multi-hop funzionano meglio con qwen3.5:9b
