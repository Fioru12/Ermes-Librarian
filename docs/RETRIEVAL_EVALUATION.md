# Valutazione del retrieval locale

`evaluation/library_gold_set.json` e' il dataset iniziale, completamente fittizio, per verificare il bibliotecario Ermes senza documenti aziendali reali. Copre quattro biblioteche indipendenti: HR, IT, Qualita e Amministrazione.

Il comando seguente crea un database temporaneo, carica il corpus demo e misura se il passaggio atteso appare nelle prime tre citazioni:

```powershell
python evaluation/run_library_eval.py
```

Il risultato riporta `recall_at_3`, dettaglio per query e integrita' minima della citazione. La soglia CI iniziale e' 0.90. Il test equivalente e' `tests/test_library_evaluation.py`.

Questa valutazione non misura ancora la qualita' di generazione LLM. Misura il requisito che viene prima: la domanda deve recuperare il documento e il locator corretti, nella sola biblioteca autorizzata. Prima di una release pubblica il set deve crescere a 20-30 domande, includere query ambigue, astensioni, versioni ripristinate e casi di accesso negato.

La ricerca semantica resta opzionale nel MVP: impostando `ERMES_LIBRARY_SEMANTIC_SEARCH=1`, gli embedding vengono ottenuti solamente da Ollama configurato in locale. Se il modello locale non e' disponibile, Ermes degrada alla ricerca testuale senza inviare documenti al cloud.
