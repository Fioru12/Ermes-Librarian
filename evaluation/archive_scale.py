"""Quanto regge la ricerca su un archivio di dimensioni aziendali?

Perche' serve
-------------
Il caso d'uso vero del prodotto e' un ufficio che cerca dentro una mole di
documenti gia' esistente. Il test di prestazioni piu' grande del progetto usa
**60 passaggi**; la valutazione di qualita' arriva a 388. Un archivio
aziendale ne ha decine di migliaia.

Finche' non e' misurato, "la ricerca e' veloce" e' un'impressione presa su un
corpus giocattolo. Qui si misura la cosa che decide se il tool viene usato o
abbandonato dopo due settimane: **quanto ci mette a rispondere, e come cresce
quel tempo con l'archivio**.

Cosa misura
-----------
- il tempo di indicizzazione, cioe' quanto si aspetta al primo caricamento;
- il tempo di una ricerca, al crescere del numero di passaggi;
- la dimensione del database sul disco.

Modalita' lessicale: e' quella predefinita e non richiede modelli. Con gli
embedding attivi l'indicizzazione e' dominata dalle chiamate al modello, che
sono un costo diverso e vanno misurate a parte.

Uso
---
    python evaluation/archive_scale.py
    python evaluation/archive_scale.py --sizes 1000,10000,50000
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import cfg  # noqa: E402
from core.library_store import LibraryStore  # noqa: E402

# Vocabolario da ufficio: le query devono trovare qualcosa, altrimenti si
# misurerebbe il caso piu' veloce (nessun candidato) invece di quello reale.
_ARGOMENTI = [
    "ferie", "permessi", "malattia", "trasferta", "rimborso", "fattura",
    "contratto", "fornitore", "cliente", "scadenza", "collaudo", "verbale",
    "sicurezza", "formazione", "manutenzione", "non conformita", "audit",
    "protocollo", "delibera", "preventivo",
]

_QUERY = [
    "come richiedo le ferie",
    "procedura di rimborso trasferta",
    "scadenza contratto fornitore",
    "verbale di collaudo impianto",
    "formazione sicurezza obbligatoria",
]


def _passaggio(casuale: random.Random, indice: int) -> str:
    argomento = casuale.choice(_ARGOMENTI)
    secondario = casuale.choice(_ARGOMENTI)
    return (
        f"Sezione {indice}. La procedura relativa a {argomento} prevede che la richiesta "
        f"sia inoltrata al responsabile con almeno quindici giorni di anticipo, allegando "
        f"la documentazione di {secondario}. Il protocollo numero {indice * 7 % 9973} "
        f"registra l'esito e la data di approvazione."
    )


def costruisci(store: LibraryStore, library_id: str, passaggi: int, per_documento: int = 10) -> float:
    """Indicizza `passaggi` passaggi e restituisce i secondi impiegati."""
    casuale = random.Random(20260910)
    inizio = time.perf_counter()
    for primo in range(0, passaggi, per_documento):
        blocco = [_passaggio(casuale, primo + n) for n in range(min(per_documento, passaggi - primo))]
        chunks = [(testo, f"Sezione {n + 1}") for n, testo in enumerate(blocco)]
        nome = f"archivio-{primo // per_documento:05d}.md"
        store.add_document(
            library_id, nome, "text/markdown", "\n".join(blocco).encode("utf-8"), f"/archivio/{nome}", chunks=chunks
        )
    return time.perf_counter() - inizio


def misura(passaggi: int) -> dict:
    object.__setattr__(cfg, "LIBRARY_SEMANTIC_SEARCH_ENABLED", False)
    object.__setattr__(cfg, "EVIDENCE_VERIFIER_ENABLED", False)

    with tempfile.TemporaryDirectory(prefix="ermes-archivio-") as temporanea:
        percorso = Path(temporanea) / "archivio.sqlite3"
        store = LibraryStore(percorso)
        library = store.create_library("Archivio", "", "private", owner_id="misura")

        secondi_indice = costruisci(store, library["id"], passaggi)

        # Una passata a vuoto per non misurare l'apertura del database.
        store.search_with_profile(library["id"], "protocollo", limit=3)

        tempi = []
        for _ in range(3):
            for query in _QUERY:
                avvio = time.perf_counter()
                store.search_with_profile(library["id"], query, limit=3)
                tempi.append(time.perf_counter() - avvio)

        return {
            "passaggi": passaggi,
            "indicizzazione_s": round(secondi_indice, 1),
            "per_1000_passaggi_s": round(secondi_indice / max(passaggi, 1) * 1000, 2),
            "ricerca_mediana_ms": round(statistics.median(tempi) * 1000, 1),
            "ricerca_peggiore_ms": round(max(tempi) * 1000, 1),
            "database_mb": round(percorso.stat().st_size / (1024 * 1024), 1),
        }


def tabella(righe: list[dict]) -> str:
    testa = [
        "| Passaggi | Indicizzazione | per 1000 | Ricerca (mediana) | Ricerca (peggiore) | Database |",
        "|---|---|---|---|---|---|",
    ]
    for r in righe:
        testa.append(
            f"| {r['passaggi']:,} | {r['indicizzazione_s']} s | {r['per_1000_passaggi_s']} s | "
            f"{r['ricerca_mediana_ms']} ms | {r['ricerca_peggiore_ms']} ms | {r['database_mb']} MB |"
        )
    return "\n".join(testa).replace(",", ".")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", default="1000,5000,20000", help="Numero di passaggi, separati da virgola")
    argomenti = parser.parse_args()

    righe = []
    for taglia in [int(x) for x in argomenti.sizes.split(",")]:
        print(f"-> {taglia} passaggi ...", file=sys.stderr, flush=True)
        righe.append(misura(taglia))
        print(f"   {righe[-1]}", file=sys.stderr, flush=True)

    print()
    print(tabella(righe))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
