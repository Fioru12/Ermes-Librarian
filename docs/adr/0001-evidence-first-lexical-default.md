# ADR 0001 — Evidenza prima della risposta, recupero lessicale come default

**Stato:** accettata · **Data:** agosto–settembre 2026, formalizzata il 25 settembre 2026

## Contesto

Un assistente documentale aziendale sbaglia in due modi con costi diversi.
Non trovare una risposta che c'è costa una ricerca in più. Rispondere con
sicurezza citando una fonte che non dice quello, o inventare quando la fonte
non c'è, costa una decisione presa su un dato falso — e distrugge la fiducia
nello strumento. Il secondo errore è quello da evitare per primo.

## Decisione

1. **Ogni risposta è costruita dai passaggi recuperati e li cita.** La
   modalità predefinita (`evidence_only`, `core/evidence_assistant.py`) non usa
   alcun modello generativo: restituisce i passaggi. Le modalità con modello
   (`local_ollama`, provider approvati) devono citare con marcatori `[n]`
   che puntano a passaggi reali; una risposta senza marcatori validi, o con
   marcatori fuori intervallo, viene scartata e trasformata in astensione.
2. **Senza evidenza, il sistema si astiene** (`status: "abstained"`) invece di
   rispondere.
3. **Il recupero predefinito è lessicale**, non ibrido con embedding.

## Perché lessicale e non ibrido

Misurato sul gold set (`docs/RETRIEVAL_EVALUATION.md`):

| | Lessicale | Ibrida | Ibrida + verifica |
|---|---|---|---|
| Parafrasi (recall@3) | 0.500 | **0.875** | 0.625 |
| Astensione corretta | **1.000** | 0.000 | **1.000** |

La ricerca ibrida trova più parafrasi, ma la similarità coseno restituisce
*sempre* qualcosa di vicino: sulle domande senza risposta nel corpus cita un
passaggio in ogni caso. Nessuna soglia di coseno separa le parafrasi corrette
dai falsi positivi (gli intervalli si sovrappongono, tabella nello stesso
documento). Per il criterio sopra, un'astensione a 0 è inaccettabile come
default, qualunque sia il guadagno sulle parafrasi.

## Conseguenze

- Le parafrasi sono il punto debole della configurazione rilasciata, ed è
  dichiarato nel README.
- Su corpus grandi e misti anche il lessicale perde astensione (1.000 → 0.333
  con 100 passaggi estranei). L'unico meccanismo misurato che la recupera è la
  verifica dell'evidenza con un modello locale, che resta opzionale perché
  richiede hardware che non tutte le installazioni hanno.
- `tests/test_library_evaluation.py` blocca la CI se diretta, parafrasi o
  astensione scendono sotto i valori misurati: cambiare il default richiede
  prima una misura migliore, non un'opinione.

## Alternative scartate

- **Soglia minima di copertura dei termini**: misurata da 0.2 a 0.5, nessun
  valore migliora l'astensione senza far crollare le domande dirette.
- **Pesatura IDF**: migliora il ranking a 100 passaggi, non l'astensione — i
  falsi positivi vengono da polisemie ("codice" etico/sorgente), che la
  frequenza non distingue.
