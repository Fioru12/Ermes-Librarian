"""Cosa e' cambiato fra due versioni di un documento, sezione per sezione.

Lo storico delle versioni conserva gli originali; il testo indicizzato esiste
solo per la versione corrente. Il confronto rilegge quindi i due originali con
lo stesso parser dell'ingestione e confronta le unita' per riferimento
(``Sezione: ...``, ``Pagina N``): cosi' ogni differenza e' citabile come una
risposta, con la sezione in cui si trova.

Una sezione rinominata appare come tolta e aggiunta: e' quello che vede chi
confronta le due versioni a mano, e indovinare l'abbinamento rischierebbe di
presentare come "modificato" un testo che non c'entra.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from core.document_parser import SourceUnit

# Una frase cambiata in un paragrafo lungo deve leggersi senza scorrere tutto
# il paragrafo: si mostrano le frasi, non il blocco intero.
_MAX_FRASI = 40


@dataclass(frozen=True)
class SectionChange:
    locator: str
    kind: str  # "added" | "removed" | "changed"
    before: list[str]
    after: list[str]

    def as_dict(self) -> dict:
        return {"locator": self.locator, "kind": self.kind, "before": self.before, "after": self.after}


def _frasi(testo: str) -> list[str]:
    import re

    return [f.strip() for f in re.split(r"(?<=[.!?;:])\s+|\n+", testo) if f.strip()]


def _per_riferimento(units: list[SourceUnit]) -> dict[str, str]:
    sezioni: dict[str, str] = {}
    for unit in units:
        # Lo stesso riferimento piu' volte (raro): si concatena, non si perde.
        sezioni[unit.locator] = (sezioni.get(unit.locator, "") + "\n" + unit.text).strip()
    return sezioni


def compare_units(before: list[SourceUnit], after: list[SourceUnit]) -> list[SectionChange]:
    """Differenze nell'ordine in cui le sezioni compaiono nella versione nuova."""
    vecchie, nuove = _per_riferimento(before), _per_riferimento(after)
    changes: list[SectionChange] = []
    for locator, testo in nuove.items():
        if locator not in vecchie:
            changes.append(SectionChange(locator, "added", [], _frasi(testo)[:_MAX_FRASI]))
            continue
        if " ".join(vecchie[locator].split()) == " ".join(testo.split()):
            continue
        prima, dopo = _frasi(vecchie[locator]), _frasi(testo)
        tolte: list[str] = []
        aggiunte: list[str] = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=prima, b=dopo, autojunk=False).get_opcodes():
            if tag in {"replace", "delete"}:
                tolte += prima[i1:i2]
            if tag in {"replace", "insert"}:
                aggiunte += dopo[j1:j2]
        changes.append(SectionChange(locator, "changed", tolte[:_MAX_FRASI], aggiunte[:_MAX_FRASI]))
    for locator, testo in vecchie.items():
        if locator not in nuove:
            changes.append(SectionChange(locator, "removed", _frasi(testo)[:_MAX_FRASI], []))
    return changes
