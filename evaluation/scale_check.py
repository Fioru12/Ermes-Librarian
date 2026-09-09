"""Il numero di recall regge quando il corpus cresce?

Perche' serve
-------------
Tutti i numeri pubblicati dal progetto vengono da 16 passaggi. Trovare il
passaggio giusto fra tre risultati su sedici candidati e' un compito molto
piu' facile che farlo su qualche migliaio, che e' la dimensione di un archivio
aziendale vero. Finche' non e' misurato, `recall@3 = 0.852` non dice niente
sulla scala — ed e' la prima obiezione che farebbe chiunque valuti il
progetto sul serio.

Come e' misurato
----------------
La variabile isolata e' una sola: la dimensione del corpus. Stesse 27
domande, stesse risposte attese, stesso codice di recupero. Cambia solo
quanto rumore c'e' intorno alla risposta corretta.

Il rumore non e' inventato: sono paragrafi reali presi dalla documentazione
di questo repository. Testo vero, con la struttura irregolare del testo vero,
e per giunta a tema tecnico-aziendale — quindi non rumore facile da scartare.

Quello che questo strumento NON dimostra: che il sistema funzioni sui
documenti di una specifica azienda. Le domande restano scritte da noi. Misura
la robustezza alla scala, non l'aderenza a un dominio.

Uso
---
    python evaluation/scale_check.py
    python evaluation/scale_check.py --sizes 0,200,400 --semantic
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import cfg  # noqa: E402
from core.evidence_verifier import verify_citations  # noqa: E402
from core.library_embeddings import embed_texts  # noqa: E402
from evaluation.run_library_eval import (  # noqa: E402
    GOLD_SET_PATH,
    _recall,
    build_demo_store,
)

# Sorgenti del rumore: la documentazione del progetto. Esclusa evaluation/
# stessa, per non inserire nel corpus il testo che descrive le risposte attese.
_DOC_GLOBS = ("docs/**/*.md", "*.md")
_MIN_PARAGRAFO = 200


def paragrafi_reali(radice: Path) -> list[str]:
    """Paragrafi di prosa vera, deduplicati e in ordine deterministico."""
    visti: set[str] = set()
    fuori: list[str] = []
    percorsi = sorted({p for glob in _DOC_GLOBS for p in radice.glob(glob) if p.is_file()})
    for percorso in percorsi:
        testo = percorso.read_text(encoding="utf-8", errors="ignore")
        for paragrafo in testo.split("\n\n"):
            pulito = " ".join(paragrafo.split())
            if len(pulito) >= _MIN_PARAGRAFO and pulito not in visti:
                visti.add(pulito)
                fuori.append(pulito)
    return fuori


def aggiungi_rumore(store, library_id: str, paragrafi: list[str], semantic: bool) -> int:
    """Inserisce i paragrafi come documenti aggiuntivi nella biblioteca."""
    if not paragrafi:
        return 0
    # A blocchi di dieci, come un documento vero con piu' sezioni: un unico
    # documento gigante non somiglierebbe a un archivio reale.
    inseriti = 0
    for indice in range(0, len(paragrafi), 10):
        blocco = paragrafi[indice : indice + 10]
        chunks = [(testo, f"Sezione {n + 1}") for n, testo in enumerate(blocco)]
        contenuto = "\n".join(blocco).encode("utf-8")
        nome = f"documento-archivio-{indice // 10:03d}.md"
        documento = store.add_document(library_id, nome, "text/markdown", contenuto, f"/archivio/{nome}", chunks=chunks)
        if semantic:
            vettori = embed_texts([testo for testo, _ in chunks])
            if vettori:
                store.store_chunk_embeddings(library_id, documento["id"], vettori, cfg.EMBED_MODEL_ID)
        inseriti += len(blocco)
    return inseriti


def misura(
    gold: list[dict], rumore_per_biblioteca: int, paragrafi: list[str], semantic: bool, verify: bool = False
) -> dict:
    object.__setattr__(cfg, "LIBRARY_SEMANTIC_SEARCH_ENABLED", semantic)
    object.__setattr__(cfg, "EVIDENCE_VERIFIER_ENABLED", verify)

    with tempfile.TemporaryDirectory(prefix="ermes-scale-") as temporanea:
        store, libraries = build_demo_store(Path(temporanea) / "library.sqlite3")

        casuale = random.Random(20260909)  # deterministico: due corse devono coincidere
        aggiunti = 0
        for library_id in libraries.values():
            campione = casuale.sample(paragrafi, min(rumore_per_biblioteca, len(paragrafi)))
            aggiunti += aggiungi_rumore(store, library_id, campione, semantic)

        dettagli = []
        for item in gold:
            tipo = item.get("type", "direct")
            risultati, _ = store.search_with_profile(libraries[item["library"]], item["query"], limit=3)
            risultati, _verificato = verify_citations(item["query"], risultati)
            if tipo == "abstention":
                superato = len(risultati) == 0
            else:
                superato = any(
                    r["filename"] == item["expected_filename"] and r["citation"]["locator"] == item["expected_locator"]
                    for r in risultati
                )
            dettagli.append({"type": tipo, "passed": superato})

    superati = sum(d["passed"] for d in dettagli)
    return {
        "rumore_per_biblioteca": rumore_per_biblioteca,
        "passaggi_aggiunti": aggiunti,
        "recall_at_3": round(superati / len(dettagli), 3),
        "dirette": _recall(dettagli, "direct"),
        "parafrasi": _recall(dettagli, "paraphrase"),
        "astensione": _recall(dettagli, "abstention"),
    }


def tabella(righe: list[dict]) -> str:
    testa = [
        "| Rumore per biblioteca | Passaggi aggiunti | recall@3 | dirette | parafrasi | astensione |",
        "|---|---|---|---|---|---|",
    ]
    for r in righe:
        testa.append(
            f"| {r['rumore_per_biblioteca']} | {r['passaggi_aggiunti']} | {r['recall_at_3']:.3f} | "
            f"{r['dirette']:.3f} | {r['parafrasi']:.3f} | {r['astensione']:.3f} |"
        )
    return "\n".join(testa)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", default="0,25,50,100", help="Passaggi di rumore per biblioteca, separati da virgola")
    parser.add_argument("--semantic", action="store_true", help="Misura in modalita' ibrida (richiede Ollama)")
    parser.add_argument("--verify", action="store_true", help="Applica la verifica dell'evidenza (richiede Ollama)")
    parser.add_argument("--output", type=Path)
    argomenti = parser.parse_args()

    radice = Path(__file__).resolve().parents[1]
    paragrafi = paragrafi_reali(radice)
    if len(paragrafi) < 20:
        print(f"Solo {len(paragrafi)} paragrafi disponibili: rumore insufficiente.", file=sys.stderr)
        return 1
    print(f"Paragrafi reali disponibili come rumore: {len(paragrafi)}", file=sys.stderr)

    gold = json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))
    righe = []
    for taglia in [int(x) for x in argomenti.sizes.split(",")]:
        print(f"-> {taglia} passaggi di rumore per biblioteca ...", file=sys.stderr, flush=True)
        righe.append(misura(gold, taglia, paragrafi, argomenti.semantic, argomenti.verify))

    print()
    print(tabella(righe))
    if argomenti.output:
        argomenti.output.write_text(json.dumps(righe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
