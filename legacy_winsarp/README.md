# WinSarp — verticale legacy, congelato

Questo albero contiene l'intero motore di formule "WinSarp" (parser, knowledge graph, business assistant, UI Streamlit, script di manutenzione ed eval) così come esisteva prima che il prodotto diventasse "Ermes Knowledge", il bibliotecario documentale.

**Non riceve più sviluppo attivo.** Resta qui come materiale storico/di riferimento, isolato dal path del prodotto (`api/`, `core/library_store.py`, `core/evidence_assistant.py`, `core/ingestion_service.py`, `frontend/`). Nessun file è stato cancellato nello spostamento — solo spostato fuori dal perimetro del prodotto, come deciso in `docs/ROADMAP_V2.md` (Fase A).

## Come farlo girare, se mai servisse

Il flag `ERMES_ENABLE_LEGACY_WINSARP=1` (vedi `config.py`, `ENABLE_LEGACY_WINSARP`) riattiva i router legacy in `api/__init__.py`. Va usato solo in sviluppo/debug — non è pensato per produzione e non ha lo stesso modello di permessi del percorso a librerie (vedi `docs/AUDIT_2026-08-19.md`, sezione sicurezza, per i dettagli).

Test legacy (non raccolti dalla suite di default del prodotto):

```powershell
.\.venv-ermes\Scripts\python.exe -m pytest legacy_winsarp/tests -q
```

## Struttura

Rispecchia l'albero originale: `core/`, `api/`, `ui/`, `modules/`, `data/`, `evaluation/`, `scripts/`, `tests/`, `frontend/`, più `app.py` (il vecchio entry point Streamlit). Gli import interni sono stati aggiornati per puntare a `legacy_winsarp.*` invece che a `core.*`/`modules.*`.
