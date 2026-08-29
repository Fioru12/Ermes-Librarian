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

## Numero reale, modalita' keyword (misurato 20 agosto 2026, ricorretto e rimisurato 29 agosto 2026)

```json
{
  "queries": 27,
  "passed": 23,
  "recall_at_3": 0.852,
  "recall_at_3_direct": 1.0,
  "recall_at_3_paraphrase": 0.5,
  "abstention_accuracy": 1.0,
  "citation_coverage": 0.958
}
```

Letto onestamente, non solo il numero migliore:

- **`recall_at_3_direct = 1.0`**: sulle query dirette, la ricerca a parole chiave trova sempre il passaggio giusto nei primi tre risultati. E' la baseline attesa — un corpus di 16 chunk con query che condividono lessico col testo non e' una prova severa.
- **`recall_at_3_paraphrase = 0.5`**: su metà delle query parafrasate, il solo keyword matching non basta.
- **`abstention_accuracy = 1.0`** (era 0.667, 2 su 3): la query di astensione che falliva ("un collega lavora sempre da casa...") ora passa. Causa del bug, trovata e corretta il 29 agosto 2026: lo stemmer naive in `core/library_store.py::_search_token` troncava *qualsiasi* vocale finale delle parole >4 caratteri, quindi "lavora" (verbo) e "lavoro" (sostantivo) collassavano entrambi sulla radice "lavor" pur finendo in vocali diverse. Corretto restringendo il troncamento alle sole coppie singolare/plurale femminili reali (finale in `a`/`e`, es. richiesta/richieste) — verificato con un test che riproduce il bug (fallisce sul codice vecchio, passa su quello nuovo) e uno che conferma che richiesta/richieste continuano a corrispondere.
- **`citation_coverage = 0.958`** (era 1.0): una query parafrasata che falliva gia' prima del fix (citava per errore un passaggio sbagliato, per la stessa causa del bug sopra) ora non cita piu' nulla invece di citare qualcosa di sbagliato — il numero grezzo scende leggermente, ma e' un fallimento piu' onesto (astenersi) al posto di uno silenzioso (citare la fonte sbagliata). Nessun'altra query e' passata da superata a fallita: verificato confrontando l'esito di tutte e 27 le query prima/dopo il fix, una sola e' cambiata (quella del bug, da fallita a superata).

## Numero reale, modalita' `--semantic` (misurato 29 agosto 2026, con Ollama locale attivo — `nomic-embed-text`)

```json
{
  "queries": 27,
  "passed": 22,
  "recall_at_3": 0.815,
  "recall_at_3_direct": 1.0,
  "recall_at_3_paraphrase": 0.75,
  "abstention_accuracy": 0.0,
  "citation_coverage": 1.0
}
```

Prima misurazione reale di questa modalita' — e il risultato non e' univocamente positivo, riportato per intero:

- **`recall_at_3_paraphrase` sale da 0.5 a 0.75**: la ricerca semantica recupera 2 delle 4 query parafrasate che il solo keyword matching perdeva — l'effetto per cui e' stata aggiunta.
- **`abstention_accuracy` crolla da 1.0 (keyword, dopo il fix dello stemmer sopra) a 0.0**: tutte e tre le query che dovrebbero astenersi ora trovano un passaggio "abbastanza simile" da superare la soglia di coseno-similarita' (0.35 in `core/library_embeddings.py::min_semantic_score`), anche quando l'argomento non e' davvero nel corpus. La ricerca semantica, cosi' com'e' configurata, e' piu' brava a trovare cose vagamente correlate e piu' incline a farlo anche quando non dovrebbe — un compromesso reale, non un dettaglio da correggere in un futuro imprecisato. Non e' lo stesso bug dello stemmer: qui la causa e' la soglia di similarita', un meccanismo indipendente.
- **Bug trovato misurando questo numero, non nell'algoritmo di retrieval ma nello script di valutazione**: `build_demo_store` in `evaluation/run_library_eval.py` costruiva il database demo senza mai generare embedding per i chunk (solo `core/ingestion_service.py`, il percorso di caricamento reale, lo faceva) — il flag `--semantic` non aveva mai avuto un vettore da confrontare, quindi restava silenziosamente in modalita' keyword indipendentemente da Ollama. Corretto imitando esattamente il percorso di ingestion reale (embed dei chunk + `store_chunk_embeddings`, stesso ordine e stesso modello configurato).
- **Secondo bug trovato nello stesso punto**: il flag `LIBRARY_SEMANTIC_SEARCH_ENABLED` veniva impostato a `True` solo se `--semantic` era passato, mai esplicitamente a `False` altrimenti — un `.env` locale con `ERMES_LIBRARY_SEMANTIC_SEARCH=1` (lasciato attivo da altri test manuali di sessione) faceva quindi "trapelare" la modalita' semantica anche nella corsa di default, silenziosamente. La valutazione "sempre sicura per la CI, senza Ollama" dipendeva in realta' da una variabile d'ambiente ambientale, non dal flag passato. Corretto impostando il flag esplicitamente in entrambe le direzioni.

**Implicazione pratica**: prima di attivare `ERMES_LIBRARY_SEMANTIC_SEARCH=1` per un utente reale, la soglia di coseno-similarita' andrebbe alzata sopra 0.35, o l'astensione andrebbe ricontrollata con un secondo segnale — attivarla cosi' com'e' oggi scambia "trova piu' parafrasi" con "inventa citazioni quando non dovrebbe rispondere", che per un prodotto evidence-first e' il compromesso sbagliato di default.

## Gate CI

`tests/test_library_evaluation.py` verifica `recall_at_3_direct >= 0.9` e `citation_coverage >= 0.9` come soglie dure (sempre raggiungibili senza Ollama), piu' due soglie morbide (`recall_at_3_paraphrase > 0`, `abstention_accuracy > 0`) per accorgersi se la qualita' sulle query difficili crolla a zero, senza pretendere che il keyword-only le risolva tutte. Il gate CI resta sulla modalita' keyword-only: la modalita' `--semantic` non e' ancora adatta a un default di prodotto (vedi sopra) e comunque richiederebbe Ollama in CI, non disponibile.

## Cosa NON misura ancora

- La qualita' di generazione LLM quando `assistant_mode` e' `local_ollama`/`approved_openrouter` — questa valutazione misura solo il retrieval, il requisito che viene prima.
- Il comportamento su versioni ripristinate o casi di accesso negato tra librerie.
- Una soglia di coseno-similarita' che non sacrifichi l'astensione per guadagnare sulle parafrasi — vedi l'implicazione pratica sopra.

Prima di una release pubblica, il golden set dovrebbe crescere ulteriormente con query derivate dal corpus demo fittizio della Fase D del roadmap (`docs/ROADMAP_V2.md`), non solo dal corpus sintetico qui sopra.
