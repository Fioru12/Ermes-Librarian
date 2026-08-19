# Piano di pubblicazione GitHub

> **Stato (20 agosto 2026)**: la scansione dei segreti sulla history completa richiesta in fondo a questo documento è stata eseguita — nessuna credenziale reale trovata, un documento riservato di terzi trovato e rimosso interamente dalla history (non solo cancellato). La ristrutturazione monorepo proposta qui sotto (`apps/api`, `apps/web`, ecc.) resta un obiettivo aspirazionale per una release pubblica finale, non ancora eseguita — lo scope pragmatico attualmente in corso è quello di `docs/ROADMAP_V2.md` Fase F.

## Obiettivo

Pubblicare una reference platform local-first, installabile e verificabile. Non pubblicare un prototipo interno come se fosse un prodotto enterprise finito.

## Struttura proposta del nuovo repository

```text
apps/api/                 API e servizi applicativi
apps/web/                 interfaccia React
packages/contracts/       tipi e OpenAPI condivisi
packages/connectors/      SDK e connettori
docs/adr/                 decision record
docs/architecture.md      architettura e data flow
docs/threat-model.md      minacce e mitigazioni
examples/demo-corpus/     contenuti fittizi con licenza
infra/compose/            ambiente locale
scripts/                  dev, test, release
tests/unit/               test rapidi
tests/integration/        servizi e persistence
tests/e2e/                flussi UI/API
tests/eval/               golden queries e metriche RAG
```

## Esperienza demo richiesta

In meno di quindici minuti, un valutatore deve poter:

1. eseguire `docker compose up`;
2. entrare in una demo con credenziali esplicite e non riutilizzabili;
3. caricare o indicizzare un corpus fittizio;
4. cercare e ricevere una risposta con pagina/estratto citato;
5. vedere che un utente senza permesso non accede a un documento;
6. passare da modello locale a provider compatibile OpenAI e capire quali dati escono dal perimetro.

Il corpus demo consigliato è una società immaginaria con handbook HR, policy ferie, procedure IT e manuale prodotto; include dieci/trenta domande gold e casi di accesso negato/documento obsoleto.

## Materiale obbligatorio prima di una release pubblica

- README in inglese, UTF-8, con scope e limiti chiari, screenshot/GIF e quickstart;
- `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES`, `SECURITY.md`, `CONTRIBUTING.md` e changelog;
- architettura, deployment guide, connector guide, evaluation guide e threat model;
- `.env.example` senza segreti; runtime data fuori dal repository;
- release semver, immagini container pinning/digest e SBOM.

Apache-2.0 è una buona ipotesi per il core se l'obiettivo è l'adozione enterprise; la scelta finale richiede verifica delle dipendenze e della strategia commerciale.

## Quality gates

Nessun badge o claim senza gate realmente bloccante:

- formatter, lint, typecheck progressivo e test;
- test di autorizzazione e ACL prima/dopo retrieval;
- test upload (MIME, limiti, zip bomb, path traversal) e restore;
- secret scan, SAST, dependency/container scan e SBOM;
- build Compose ed E2E browser;
- golden set: recall@k, citation precision/coverage, astensione, latenza e costo.

Non usare `|| true` per far sembrare verde una CI. Non mettere `.env` in backup o artefatti.

## Cosa non migrare senza revisione dal repository corrente

Il progetto è personale e può essere evoluto. Prima della pubblicazione, però, vanno rimossi o sostituiti tutti i dati runtime, segreti, log, backup, artefatti, documentazione duplicata e qualsiasi materiale riservato di terzi. WinSarp può restare come esempio o plugin, ma non deve dominare il core né usare corpus non pubblicabile. La history Git va sottoposta a secret scan prima della release.
