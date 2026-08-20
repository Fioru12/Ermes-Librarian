# Guida per Sviluppatori — Ermes Knowledge

Questa guida descrive il codice **effettivamente eseguito dal prodotto**. Il motore
formule WinSarp è materiale storico, isolato sotto `legacy_winsarp/` e non
raggiungibile dal percorso di prodotto se non dietro il flag `ENABLE_LEGACY_WINSARP`
(vedi `legacy_winsarp/README.md`).

## Struttura del progetto

```
config.py               # Config centralizzata (dataclass congelata + .env)
pyproject.toml          # Ruff + pytest config

api/                    # FastAPI — l'app e' `api:app`
├── __init__.py         # Composizione app, router, startup, SPA catch-all
├── auth.py             # Login locale, API key, RBAC (_require_role)
├── libraries.py        # Biblioteche, documenti, versioni, download, ricerca
├── health.py           # /health (stato ollama, storage, disco, database)
├── users.py            # Gestione account e API key (solo admin)
├── audit.py            # Lettura audit log firmato
├── backup.py           # Backup e ripristino
├── models.py           # Elenco modelli disponibili
├── providers.py        # Provider LLM approvati
└── shutdown.py         # Arresto controllato

core/
├── library_store.py    # Metadati, versioni, ACL, ricerca ibrida keyword+embedding
├── ingestion_service.py# Pipeline di ingestione (parse -> chunk -> embedding)
├── document_parser.py  # Estrazione testo PDF/DOCX/TXT/MD
├── library_embeddings.py# Generazione e persistenza embedding dei chunk
├── evidence_assistant.py# Risposta evidence-first con citazioni, o astensione
├── governance.py       # Utenti, audit log firmato
├── input_validator.py  # Validazione/sanitizzazione input e nomi file upload
├── rate_limiter.py     # Rate limiting
├── pii_filter.py       # Filtro PII (GDPR)
├── backup_manager.py   # Backup/ripristino atomico
└── monitoring.py       # Metriche

core/ai/
├── llm_bridge.py       # Bridge LLM
├── utils.py            # Utility AI
└── providers/          # Registry provider (ollama, openai_compat, anthropic, google)

frontend/               # UI React + TypeScript + Vite + Tailwind
├── src/                # Componenti, hook, tema
└── dist/               # Build di produzione (servita dal backend, non versionata)

evaluation/             # Golden set e harness di valutazione del retrieval
examples/               # Corpus demo (Northstar Works, Meridian Precision Works)
scripts/                # Launcher e utility operative
tests/                  # 148 test (pytest)
legacy_winsarp/         # Motore formule storico, congelato
```

## Convenzioni

- **Lint**: `ruff check .` — 0 errori richiesto prima del commit
- **Test**: `pytest tests/` — tutti verdi
- **Python**: 3.11+, type hints
- **Ambiente**: `.venv-ermes` (non `.venv`, che può provenire da un altro profilo Windows)
- **Autenticazione**: ogni endpoint deve dipendere da `_verify_api_key` o
  `_require_role`. `tests/test_api_auth_coverage.py` percorre le route dell'app e
  fa fallire la CI se un endpoint viene aggiunto senza protezione: l'allowlist
  dei percorsi pubblici va aggiornata esplicitamente.
- **Errori**: non usare `except Exception: pass`. Un errore ingoiato produce un
  controllo che riporta successo senza aver verificato nulla — logga sempre,
  o lascia propagare.

## Come eseguire

```powershell
.\scripts\avvia_ermes.ps1                                   # Tutto (Ollama + backend + frontend)
.\.venv-ermes\Scripts\python.exe -m uvicorn api:app --reload --port 8502   # Solo backend
npm.cmd --prefix frontend run dev                           # Solo frontend (porta 3000)
.\.venv-ermes\Scripts\python.exe -m pytest tests/           # Test
```

Backend su `8502`, frontend di sviluppo su `3000` (il proxy Vite punta a 8502).
La build di produzione in `frontend/dist/` è servita direttamente dal backend ed è
un artefatto separato: modificare `frontend/index.html` non la aggiorna finché non
si riesegue `npm run build`.

## Come aggiungere un endpoint

1. Aggiungi la route nel router appropriato sotto `api/`.
2. Dichiara la dipendenza di autenticazione (`_require_role("admin")` o `_verify_api_key`).
3. Se la route tocca una biblioteca, l'ACL va applicata **server-side** prima di
   servire qualunque contenuto — mai delegarla al frontend.
4. Esegui la suite: `test_api_auth_coverage.py` rifiuta gli endpoint non protetti.
