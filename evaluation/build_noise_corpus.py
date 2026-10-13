"""Genera evaluation/noise_corpus.json, il rumore usato da scale_check.py.

Perche' un file congelato
-------------------------
Fino al 25 settembre 2026 scale_check.py leggeva il rumore dai .md del
repository a ogni esecuzione. Due difetti, trovati confrontando due misure
dello stesso codice che davano numeri diversi (0.704 e 0.667):

1. **Non riproducibile.** Ogni modifica alla documentazione cambiava il
   corpus di prova: il numero di un commit non era confrontabile con quello
   del commit dopo, e un peggioramento del recupero si confondeva con una
   frase aggiunta al README.
2. **Contaminato.** I documenti che analizzano la valutazione citano le sue
   domande: quattro paragrafi parlavano di "lavoro da casa" e tre di "codice
   etico", proprio gli argomenti di due delle tre domande di astensione.
   Citarli non era un errore del sistema — parlano davvero di quello — ma la
   misura lo contava come tale.

Cosa si esclude, e perche' cosi'
--------------------------------
Interi i file che descrivono la valutazione, e negli altri i paragrafi che
ne usano il lessico. Non si esclude per argomento aziendale ("ferie",
"backup"): renderebbe il rumore artificialmente facile, mentre il suo scopo
e' proprio competere con le risposte giuste.

Rigenerarlo cambia i numeri di scale_check.py: va fatto di proposito, e i
numeri pubblicati vanno rimisurati nello stesso commit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
USCITA = Path(__file__).resolve().parent / "noise_corpus.json"

_DOC_GLOBS = ("docs/**/*.md", "*.md")
_MIN_PARAGRAFO = 200
_FILE_ESCLUSI = {"README.md", "CHANGELOG.md", "docs/RETRIEVAL_EVALUATION.md"}
_CARTELLE_ESCLUSE = ("docs/adr/",)
_LESSICO_VALUTAZIONE = re.compile(
    r"astensi|abstention|gold ?set|golden|recall|parafras|paraphras|benchmark|da casa|codice etico",
    re.IGNORECASE,
)


def genera() -> list[dict]:
    visti: set[str] = set()
    fuori: list[dict] = []
    percorsi = sorted({p for glob in _DOC_GLOBS for p in RADICE.glob(glob) if p.is_file()})
    for percorso in percorsi:
        relativo = percorso.relative_to(RADICE).as_posix()
        if relativo in _FILE_ESCLUSI or relativo.startswith(_CARTELLE_ESCLUSE):
            continue
        for paragrafo in percorso.read_text(encoding="utf-8", errors="ignore").split("\n\n"):
            pulito = " ".join(paragrafo.split())
            if len(pulito) < _MIN_PARAGRAFO or pulito in visti:
                continue
            if _LESSICO_VALUTAZIONE.search(re.sub(r"[*_`]", "", pulito)):
                continue
            visti.add(pulito)
            fuori.append({"source": relativo, "text": pulito})
    return fuori


def main() -> int:
    paragrafi = genera()
    USCITA.write_text(json.dumps(paragrafi, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(paragrafi)} paragrafi -> {USCITA.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
