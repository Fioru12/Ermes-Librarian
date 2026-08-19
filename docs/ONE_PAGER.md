# Ermes Knowledge — one-pager

> Versione testuale. La versione visiva, pensata per essere condivisa con un recruiter o un CTO, è pubblicata come artifact: **[Ermes Knowledge — one-pager](https://claude.ai/code/artifact/b04f7270-660a-4501-802e-7d5ab2a691ad)**.

## Il problema

La conoscenza aziendale vive sparsa tra cartelle e versioni. Un chatbot generico risponde con sicurezza — a volte in modo sbagliato, senza modo di verificarlo. Ermes Knowledge scommette sul contrario: una risposta vale quanto la citazione che la sostiene, e senza citazione non c'è risposta.

## Cinque regole, applicate nel codice

1. **Local first** — una chiave API cloud da sola non attiva mai l'elaborazione cloud.
2. **Evidenza prima della generazione** — ogni risposta sostanziale cita un documento accessibile, o l'assistente dichiara di non sapere.
3. **Isolamento tra biblioteche** — la ricerca è vincolata alla biblioteca scelta prima che il contenuto raggiunga l'assistente. Verificato dal vivo, non solo assunto.
4. **I documenti sono input non fidato** — il testo recuperato non può mai autorizzare un'azione.
5. **Gli originali restano raggiungibili** — ogni citazione rimanda alla versione esatta del documento, scaricabile con un click dalla chat.

## Verificato, non dichiarato

- **Isolamento tra biblioteche provato dal vivo**: una domanda la cui risposta esiste solo nella biblioteca A, posta con la biblioteca B selezionata, restituisce correttamente "nessuna evidenza" — verificato con uno script automatico contro un server reale a ogni esecuzione, non solo in un documento di design.
- **Qualità del retrieval misurata e pubblicata**: golden set di 27 query (dirette, parafrasate, di astensione), risultati riportati onestamente, incluso dove il solo keyword matching non basta.
- **Controllo accessi testato a livello API**: un non-membro di una biblioteca privata riceve 404 (non 403, per non confermare l'esistenza della biblioteca) tentando di scaricare un documento — verificato contro la tabella di route reale, con una guardia di regressione che blocca la CI se un futuro endpoint viene spedito senza autenticazione.
- **Cronologia git scansionata per intero**: un documento riservato di terzi trovato e rimosso completamente dalla history, non solo cancellato in un nuovo commit.

## Retrieval, onestamente

Baseline solo-keyword (nessuna dipendenza esterna richiesta), misurata su un golden set costruito apposta per includere i casi che il solo keyword matching non può risolvere:

| Tipo di query | Cosa verifica | Risultato |
|---|---:|---:|
| Dirette (16) | Le parole della domanda sono vicine al testo sorgente | 100% |
| Parafrasate (8) | Stessa domanda, zero parole condivise con la fonte | 50% |
| Astensione (3) | Domanda plausibile, nessuna risposta nel corpus | 67% |

Il divario sulle query parafrasate è esattamente ciò che la ricerca ibrida locale (keyword + embedding on-device, già collegata end-to-end) dovrebbe colmare — quel numero richiede un'esecuzione locale con Ollama per essere verificato, e non è stato dichiarato senza averlo misurato.

## Costruito con

FastAPI · React + TypeScript · SQLite · Tailwind · Ollama (embedding locali) · Docker · GitHub Actions CI · pytest + vitest

## Link

- Repository: [github.com/Fioru12/Ermes-Librarian](https://github.com/Fioru12/Ermes-Librarian)
- Registro di sviluppo fase per fase: [docs/ROADMAP_V2.md](ROADMAP_V2.md)
- Audit completo (architettura, sicurezza, design): [docs/AUDIT_2026-08-19.md](AUDIT_2026-08-19.md)

Licenza MIT.
