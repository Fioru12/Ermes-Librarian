# Valutazione del retrieval locale

`evaluation/library_gold_set.json` e' il dataset fittizio per verificare il bibliotecario Ermes senza documenti aziendali reali. Copre quattro biblioteche indipendenti: HR, IT, Qualita e Amministrazione, con 27 query in tre categorie (`type`):

- **`direct`** (16 query): la domanda usa parole vicine al testo sorgente — il caso base che qualunque ricerca a parole chiave deve gestire.
- **`paraphrase`** (8 query): stessa domanda, parole diverse dal testo sorgente, zero o quasi zero sovrapposizione lessicale — pensate apposta per essere difficili per il solo keyword matching, il caso in cui la ricerca semantica dovrebbe fare la differenza.
- **`abstention`** (3 query): argomenti plausibili ma assenti dal corpus demo — il comportamento corretto e' restituire zero citazioni, non indovinare.

## Come eseguirlo

```powershell
python evaluation/run_library_eval.py
```

crea un database temporaneo, carica il corpus demo e misura se il passaggio atteso appare nelle prime tre citazioni, in modalita' keyword (nessuna dipendenza esterna, sicuro per la CI).

```powershell
python evaluation/run_library_eval.py --semantic
```

attiva anche la componente semantica locale (`core/library_embeddings.py`, embedding via Ollama). Se Ollama non e' raggiungibile, lo script degrada automaticamente a keyword-only e lo segnala esplicitamente a schermo (`semantic_search_active: false` nel report) — non fallisce in silenzio e non finge un numero che non ha misurato.

## Numero reale, misurato in questa sessione (20 agosto 2026, solo modalita' keyword — Ollama non disponibile in questo ambiente)

```json
{
  "queries": 27,
  "passed": 22,
  "recall_at_3": 0.815,
  "recall_at_3_direct": 1.0,
  "recall_at_3_paraphrase": 0.5,
  "abstention_accuracy": 0.667,
  "citation_coverage": 1.0
}
```

Letto onestamente, non solo il numero migliore:

- **`recall_at_3_direct = 1.0`**: sulle query dirette, la ricerca a parole chiave trova sempre il passaggio giusto nei primi tre risultati. E' la baseline attesa — un corpus di 16 chunk con query che condividono lessico col testo non e' una prova severa.
- **`recall_at_3_paraphrase = 0.5`**: su metà delle query parafrasate, il solo keyword matching non basta — esattamente il gap che la ricerca semantica (`ERMES_LIBRARY_SEMANTIC_SEARCH=1`) dovrebbe colmare. **Il numero in modalita' `--semantic` non e' stato misurato in questa sessione** (Ollama non raggiungibile qui) — va rieseguito in locale per essere verificato, non dichiarato.
- **`abstention_accuracy = 0.667`** (2 su 3): una query di astensione ("un collega lavora sempre da casa...") ha trovato per errore un passaggio su assenze per malattia. Causa individuata: lo stemmer naive in `core/library_store.py::_search_token` (righe 199-208) tronca l'ultima vocale delle parole >4 caratteri — "lavora" e "lavoro" collassano sulla stessa radice "lavor", causando un match spurio. E' una lacuna reale dell'euristica attuale, non nascosta qui.
- **`citation_coverage = 1.0`**: su tutte le query dove ci si aspetta evidenza (dirette + parafrasate), il sistema ha sempre trovato *qualcosa* da citare — anche quando quel qualcosa non era il passaggio corretto (vedi `recall_at_3_paraphrase`). Coverage alta non implica correttezza: sono due assi diversi, letti insieme.

## Gate CI

`tests/test_library_evaluation.py` verifica `recall_at_3_direct >= 0.9` e `citation_coverage >= 0.9` come soglie dure (sempre raggiungibili senza Ollama), piu' due soglie morbide (`recall_at_3_paraphrase > 0`, `abstention_accuracy > 0`) per accorgersi se la qualita' sulle query difficili crolla a zero, senza pretendere che il keyword-only le risolva tutte.

## Cosa NON misura ancora

- La qualita' di generazione LLM quando `assistant_mode` e' `local_ollama`/`approved_openrouter` — questa valutazione misura solo il retrieval, il requisito che viene prima.
- Il comportamento su versioni ripristinate o casi di accesso negato tra librerie.
- Il numero reale della modalita' `--semantic` (richiede Ollama locale attivo — rieseguire `python evaluation/run_library_eval.py --semantic` per ottenerlo).

Prima di una release pubblica, il golden set dovrebbe crescere ulteriormente con query derivate dal corpus demo fittizio della Fase D del roadmap (`docs/ROADMAP_V2.md`), non solo dal corpus sintetico qui sopra.
