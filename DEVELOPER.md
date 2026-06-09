# Guida per Sviluppatori — Ermes RAG

## Struttura del Progetto

```
app.py                  # Entry point Streamlit (585 righe)
api.py                  # API REST FastAPI
config.py               # Config centralizzata (dataclass + .env)
pyproject.toml          # Ruff + pytest config

core/
├── error_handler.py    # Gerarchia errori, log, retry_on_error, safe_call
├── governance.py       # Autenticazione, audit log, utenti
├── input_validator.py  # Validazione/sanitizzazione input
├── rag_engine.py       # RAG puro: LlamaIndex, ChromaDB, embedding, LLM
├── rate_limiter.py     # Rate limiting DoS
├── streamlit_rag.py    # Wrapper cached (check_ollama, get_index) per Streamlit
└── utils.py            # Utility: hash, log, pulizia

modules/
├── winsarp.py          # Modulo WinSarp (formule HR)
└── generic.py          # Modulo generico

ui/
├── admin_ui.py         # Pannello admin (utenti, audit)
├── chat_handler.py     # Flusso streaming chat (estratto da app.py)
├── chat_ui.py          # Render storico messaggi, badge confidenza, formula
├── monitor_dashboard.py# Dashboard metriche
├── sidebar_ui.py       # Sidebar: logo, tema, modelli, moduli, stato
├── theme.py            # Tema dark/light + copy button JS
├── theme_base.css      # Variabili CSS, scrollbar, reset, streamlit override
├── theme_layout.css    # Header, sidebar, footer, layout
├── theme_components.css# Bottoni, badge, card, chat, formula, modali
└── welcome_ui.py       # Welcome screen, feedback, help, workspace overview

scripts/
├── AVVIA.bat           # Launcher principale
├── AVVIA.vbs           # Wrapper VBS invisibile
└── crea_shortcut.ps1   # Crea shortcut desktop

tests/                  # 115+ test (pytest)
├── test_api.py
├── test_error_handler.py
├── test_governance.py
├── test_integration.py
├── test_monitor.py
├── test_rag_engine.py
├── test_rate_limiter.py
├── test_utils.py
└── test_winsarp.py
```

## Convenzioni

- **Lint**: `ruff check .` — 0 errori richiesto prima di commit
- **Test**: `pytest tests/ -v` — tutti verdi
- **Python**: 3.11+, type hints ovunque
- **CSS**: `string.Template` con variabili `$color`, split in 3 file
- **Errori**: usare gerarchia `AppError` da `core/error_handler.py`

## Come Aggiungere un Modulo

1. Crea `modules/tuo_modulo.py` con classe che implementa `get_prompt()`
2. Aggiungi a `app.py` nell'init di `st.session_state.modules`
3. Crea `documenti/tuo_modulo/` e metti i PDF/DOCX/TXT

## Come Eseguire

```bash
.venv\Scripts\streamlit run app.py    # UI
.venv\Scripts\uvicorn api:app         # API REST
.venv\Scripts\pytest tests/ -v       # Test
.venv\Scripts\ruff check .           # Lint
```
