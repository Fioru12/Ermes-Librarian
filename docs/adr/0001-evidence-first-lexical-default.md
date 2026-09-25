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

Misurato sul gold set di 52 domande (`docs/RETRIEVAL_EVALUATION.md`),
corpus demo / corpus con 388 passaggi estranei:

| | Lessicale | Ibrida | Lessicale + verifica | Ibrida + verifica |
|---|---|---|---|---|
| Dirette (recall@3) | 1.000 / 0.938 | 1.000 / 1.000 | 1.000 / 0.938 | 1.000 / 0.625 |
| Parafrasi (recall@3) | 0.450 / 0.250 | **0.900 / 0.500** | 0.350 / 0.200 | 0.350 / 0.050 |
| Astensione corretta | 0.375 / 0.062 | 0.000 / 0.000 | **1.000 / 1.000** | 1.000 / 1.000 |

Fino al 25 settembre 2026 questa tabella riportava 1.000 per l'astensione
lessicale: il valore veniva da tre domande. Su sedici e' 0.375. La decisione
non cambia — l'ibrida a 0 resta inaccettabile — ma cambia la conseguenza: il
default senza modello non e' "affidabile sul corpus piccolo", e' debole
ovunque; la verifica non e' un'opzione per archivi grandi, e' il requisito
per mantenere la promessa di questo ADR.

La ricerca ibrida trova più parafrasi, ma la similarità coseno restituisce
*sempre* qualcosa di vicino: sulle domande senza risposta nel corpus cita un
passaggio in ogni caso. Nessuna soglia di coseno separa le parafrasi corrette
dai falsi positivi (gli intervalli si sovrappongono, tabella nello stesso
documento). Per il criterio sopra, un'astensione a 0 è inaccettabile come
default, qualunque sia il guadagno sulle parafrasi.

## Conseguenze

- Le parafrasi sono il punto debole della configurazione rilasciata, ed è
  dichiarato nel README.
- Senza modello il lessicale si astiene correttamente 6 volte su 16, e 1 su
  16 con un archivio attorno. L'unico meccanismo misurato che la porta a 16/16
  e' la verifica dell'evidenza con un modello locale, che resta opzionale
  perche' richiede hardware che non tutte le installazioni hanno: il profilo
  "verified" la rende un requisito dichiarato.
- `tests/test_library_evaluation.py` blocca la CI se diretta, parafrasi o
  astensione scendono sotto i valori misurati: cambiare il default richiede
  prima una misura migliore, non un'opinione.

## Alternative scartate

- **Soglia minima di copertura dei termini**: misurata da 0.2 a 0.5, nessun
  valore migliora l'astensione senza far crollare le domande dirette.
- **Pesatura IDF**: migliora il ranking a 100 passaggi, non l'astensione — i
  falsi positivi vengono da polisemie ("codice" etico/sorgente), che la
  frequenza non distingue.
