"""L'inventario delle licenze deve descrivere le dipendenze che ci sono.

Trovato l'11 settembre 2026 controllando le licenze: THIRD_PARTY_NOTICES.md
dichiarava di essere generato, ma lo script non esisteva e il file era scritto
a mano. Quando `psycopg` e' stato aggiunto a requirements.txt nessuno lo ha
aggiornato, e il file affermava in grassetto:

    "Every declared dependency is under a permissive license (MIT,
    BSD-3-Clause, Apache-2.0 or ISC). None imposes a copyleft obligation."

Falso: psycopg e' LGPL-3.0. Quattro dipendenze mancavano del tutto
(PyJWT, prometheus-client, psycopg, pytest-benchmark).

Un inventario delle licenze e' una dichiarazione legale su cui un'azienda
decide se puo' adottare il prodotto: una sua affermazione sbagliata e' peggio
di un test rosso, perche' nessuno la verifica finche' non e' tardi.
"""

import importlib.metadata as md
import json
import pathlib
import re

import pytest

RADICE = pathlib.Path(__file__).resolve().parents[1]
NOTICES = RADICE / "THIRD_PARTY_NOTICES.md"

# Le stesse del generatore. Duplicate di proposito: se qualcuno allargasse la
# lista nel generatore per far sparire un'eccezione, questo test non lo
# seguirebbe in silenzio.
PERMISSIVE = (
    "mit",
    "bsd",
    "apache",
    "isc",
    "0bsd",
    "unlicense",
    "zlib",
    "python software foundation",
    "psf",
    "python-2.0",
    "blueoak",
    "cc0",
)


def _dichiarate() -> list[str]:
    nomi = []
    for riga in (RADICE / "requirements.txt").read_text(encoding="utf-8").splitlines():
        riga = riga.split("#")[0].strip()
        if not riga or riga.startswith("-"):
            continue
        nomi.append(re.split(r"[=<>!\[]", riga)[0].strip())
    return sorted(set(nomi), key=str.lower)


def _licenza(nome: str) -> str:
    try:
        dist = md.distribution(nome)
    except md.PackageNotFoundError:
        pytest.skip(f"{nome} non installata in questo ambiente")
    meta = dist.metadata
    for chiave in ("License-Expression", "License"):
        valore = (meta.get(chiave) or "").strip()
        if valore and len(valore) < 80:
            return valore
    classifier = [c.split("::")[-1].strip() for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")]
    return " / ".join(classifier) if classifier else ""


def test_every_declared_dependency_appears_in_the_inventory():
    testo = NOTICES.read_text(encoding="utf-8")

    mancanti = [nome for nome in _dichiarate() if f"`{nome}`" not in testo]

    assert mancanti == [], (
        "Dipendenze in requirements.txt assenti da THIRD_PARTY_NOTICES.md: "
        + ", ".join(mancanti)
        + ". Rigenera con scripts/generate_third_party_notices.py."
    )


def test_the_inventory_does_not_claim_every_dependency_is_permissive_unless_true():
    """La riga che era falsa. Se torna, questo test la becca."""
    testo = NOTICES.read_text(encoding="utf-8")
    non_permissive = [n for n in _dichiarate() if (lic := _licenza(n)) and not any(p in lic.lower() for p in PERMISSIVE)]

    if non_permissive:
        assert "Every declared dependency is under a permissive license" not in testo, (
            "L'inventario afferma che tutte le dipendenze sono permissive, ma non lo sono: "
            + ", ".join(non_permissive)
        )
        assert "None imposes a copyleft obligation" not in testo


def test_non_permissive_dependencies_are_named_in_the_inventory():
    """Non basta togliere l'affermazione falsa: chi valuta deve poter vedere
    quali sono le eccezioni e dove si applicano."""
    testo = NOTICES.read_text(encoding="utf-8")

    for nome in _dichiarate():
        licenza = _licenza(nome)
        if licenza and not any(p in licenza.lower() for p in PERMISSIVE):
            assert f"`{nome}`" in testo, f"{nome} ({licenza}) non compare nell'inventario"
            assert "Licence summary" in testo, "manca la sezione che elenca le eccezioni"


def test_the_sbom_covers_the_declared_dependencies():
    """L'SBOM era fermo al 20 agosto 2026 con 21 componenti, quattro in meno di
    requirements.txt. Un SBOM incompleto e' peggio di uno assente: chi lo
    scansiona per le CVE crede di aver coperto tutto."""
    sbom = json.loads((RADICE / "sbom.json").read_text(encoding="utf-8"))
    presenti = {str(c.get("name", "")).lower() for c in sbom.get("components", [])}

    mancanti = [n for n in _dichiarate() if n.lower() not in presenti]

    assert mancanti == [], (
        "Dipendenze assenti da sbom.json: "
        + ", ".join(mancanti)
        + ". Rigenera: python -m cyclonedx_py requirements requirements.txt "
        "-o sbom.json --output-format JSON"
    )


def test_the_project_license_and_the_copyright_holder_agree():
    """LICENSE e NOTICE devono nominare la stessa persona: un titolare del
    copyright diverso fra i due file e' un'ambiguita' su chi detiene i
    diritti."""
    licenza = (RADICE / "LICENSE").read_text(encoding="utf-8")
    notice = (RADICE / "NOTICE").read_text(encoding="utf-8")

    assert "MIT License" in licenza
    titolare_licenza = re.search(r"Copyright \(c\) \d{4} (.+)", licenza)
    titolare_notice = re.search(r"Copyright \(c\) \d{4} (.+)", notice)
    assert titolare_licenza and titolare_notice, "manca la riga di copyright in LICENSE o NOTICE"
    assert titolare_licenza.group(1).strip() == titolare_notice.group(1).strip(), (
        f"LICENSE dice {titolare_licenza.group(1)!r}, NOTICE dice {titolare_notice.group(1)!r}"
    )
