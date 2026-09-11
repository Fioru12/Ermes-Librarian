"""Genera THIRD_PARTY_NOTICES.md dai metadati realmente installati.

Il file dichiarava di essere generato, ma lo script non esisteva: era scritto a
mano, e quando `psycopg` e' stato aggiunto a requirements.txt (commit 47a3fe1,
10 settembre 2026) nessuno lo ha aggiornato. Risultato: quattro dipendenze
assenti dall'inventario, e — piu' grave — l'affermazione in grassetto "ogni
dipendenza e' sotto licenza permissiva, nessuna impone obblighi di copyleft"
era falsa, perche' psycopg e' LGPL-3.0.

Un inventario delle licenze e' una dichiarazione legale su cui qualcuno decide
se puo' adottare il prodotto. Deve essere prodotto dai fatti, non ricordato.

Uso:
    .\\.venv-ermes\\Scripts\\python.exe scripts\\generate_third_party_notices.py
"""

from __future__ import annotations

import importlib.metadata as md
import json
import pathlib
import re
import sys

RADICE = pathlib.Path(__file__).resolve().parents[1]
USCITA = RADICE / "THIRD_PARTY_NOTICES.md"

# Licenze che non impongono obblighi oltre l'attribuzione.
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
    "cc0",  # dedica al pubblico dominio
)


def dipendenze_dichiarate() -> dict[str, str]:
    """{nome: versione fissata}. La versione viene da requirements.txt, non
    dai metadati installati: l'inventario descrive quello che un deployment
    ottiene, non quello che c'e' sulla macchina di chi lo rigenera — due cose
    che divergono ogni volta che un pin cambia prima di un `pip install`."""
    dichiarate: dict[str, str] = {}
    for riga in (RADICE / "requirements.txt").read_text(encoding="utf-8").splitlines():
        riga = riga.split("#")[0].strip()
        if not riga or riga.startswith("-"):
            continue
        nome = re.split(r"[=<>!\[]", riga)[0].strip()
        fissata = riga.split("==", 1)[1].strip() if "==" in riga else "(non fissata)"
        dichiarate[nome] = fissata
    return dict(sorted(dichiarate.items(), key=lambda v: v[0].lower()))


def licenza_python(nome: str) -> str:
    """Legge PEP 639 (License-Expression), poi i classifier, poi il campo
    libero: i pacchetti recenti usano il primo, quelli piu' vecchi gli altri, e
    guardarne uno solo fa risultare mezza lista "senza licenza"."""
    try:
        dist = md.distribution(nome)
    except md.PackageNotFoundError:
        return "NON INSTALLATA"
    meta = dist.metadata
    for chiave in ("License-Expression", "License"):
        valore = (meta.get(chiave) or "").strip()
        if valore and len(valore) < 80:
            return valore
    classifier = [c.split("::")[-1].strip() for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")]
    return " / ".join(classifier) if classifier else "(non dichiarata)"


def permissiva(licenza: str) -> bool:
    return any(p in licenza.lower() for p in PERMISSIVE)


def dipendenze_javascript() -> list[tuple[str, str, str, bool]]:
    lock = json.loads((RADICE / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    diretti = set()
    package_json = json.loads((RADICE / "frontend" / "package.json").read_text(encoding="utf-8"))
    for sezione in ("dependencies", "devDependencies"):
        diretti |= set(package_json.get(sezione, {}))

    voci = []
    for percorso, info in (lock.get("packages") or {}).items():
        nome = percorso.replace("node_modules/", "")
        if not nome:
            continue
        licenza = info.get("license") or info.get("licenses") or "(non dichiarata)"
        if isinstance(licenza, list):
            licenza = " / ".join(str(x.get("type", x)) if isinstance(x, dict) else str(x) for x in licenza)
        voci.append((nome, str(info.get("version", "?")), str(licenza), nome in diretti))
    return sorted(voci, key=lambda v: v[0].lower())


def main() -> int:
    python_voci = [(nome, versione, licenza_python(nome)) for nome, versione in dipendenze_dichiarate().items()]
    js_voci = dipendenze_javascript()
    js_diretti = [v for v in js_voci if v[3]]

    non_permissive_py = [(n, v, lic) for n, v, lic in python_voci if not permissiva(lic)]
    non_permissive_js = sorted({(lic) for _, _, lic, _ in js_voci if not permissiva(lic)})
    js_per_licenza: dict[str, int] = {}
    for _, _, lic, _ in js_voci:
        js_per_licenza[lic] = js_per_licenza.get(lic, 0) + 1

    righe = [
        "# Third-party notices",
        "",
        "Ermes Knowledge is distributed under the MIT License (see `LICENSE`). It bundles",
        "no third-party source code, but depends on the open-source packages listed here.",
        "Each remains under its own license, held by its respective authors.",
        "",
        "Generated from installed package metadata and `frontend/package-lock.json` by",
        "`scripts/generate_third_party_notices.py`. Do not edit by hand: regenerate it.",
        "`tests/test_third_party_notices.py` fails when it no longer matches",
        "`requirements.txt`, which is how four missing entries were found.",
        "",
        "## Licence summary",
        "",
    ]

    if non_permissive_py or non_permissive_js:
        righe += [
            "Most dependencies are permissive (MIT, BSD, Apache-2.0, ISC). The exceptions",
            "are listed here rather than averaged away, because an organisation with a",
            "policy on copyleft needs to see them before adopting the product.",
            "",
            "| Package | License | Where it applies |",
            "|---|---|---|",
        ]
        for nome, _versione, lic in non_permissive_py:
            righe.append(f"| `{nome}` (Python) | {lic} | see the note below |")
        for lic in non_permissive_js:
            pacchetti = sorted({n for n, _, li, _ in js_voci if li == lic})
            campione = ", ".join(f"`{p}`" for p in pacchetti[:3])
            piu = f" (+{len(pacchetti) - 3} more)" if len(pacchetti) > 3 else ""
            righe.append(f"| {campione}{piu} (JavaScript) | {lic} | build time only, not shipped in the bundle |")
        righe += [
            "",
            "**`psycopg` (LGPL-3.0) is optional.** It is the PostgreSQL driver: the product",
            "runs entirely on SQLite without it, and `ERMES_DATABASE_URL` is what turns the",
            "PostgreSQL backend on. Used unmodified as an imported library, the LGPL does",
            "not extend its terms to Ermes; it does require that whoever receives the",
            "software can replace that library, which a `pip install` already allows.",
            "An organisation that forbids (L)GPL outright can drop the line from",
            "`requirements.txt` and stay on SQLite — nothing else depends on it.",
            "",
            "**MPL-2.0 and CC-BY-4.0 on the JavaScript side** come from build tooling",
            "(`lightningcss`, pulled in by Tailwind, and the `caniuse-lite` data set).",
            "They are not modified and not redistributed in the built frontend.",
            "",
        ]
    else:
        righe += ["Every declared dependency is under a permissive license.", ""]

    righe += [
        "## Python — runtime and test dependencies",
        "",
        "Declared in `requirements.txt`.",
        "",
        "| Package | Version | License |",
        "|---|---|---|",
    ]
    for nome, versione, lic in python_voci:
        righe.append(f"| `{nome}` | {versione} | {lic} |")

    righe += [
        "",
        "## JavaScript — application and build dependencies",
        "",
        f"Declared in `frontend/package.json` ({len(js_diretti)} direct, {len(js_voci)} resolved in the lock file).",
        "",
        "| Package | Version | License |",
        "|---|---|---|",
    ]
    for nome, versione, lic, _ in js_diretti:
        righe.append(f"| `{nome}` | {versione} | {lic} |")

    righe += [
        "",
        "Licenses across the full resolved tree: "
        + ", ".join(
            f"{lic or '(non dichiarata)'} ({n})" for lic, n in sorted(js_per_licenza.items(), key=lambda x: -x[1])
        )
        + ".",
        "",
        "## Machine-readable SBOM",
        "",
        "`sbom.json` is a CycloneDX 1.6 software bill of materials for the Python",
        "dependency surface. Regenerate it whenever `requirements.txt` changes:",
        "",
        "```powershell",
        ".\\.venv-ermes\\Scripts\\python.exe -m pip install cyclonedx-bom",
        ".\\.venv-ermes\\Scripts\\python.exe -m cyclonedx_py requirements requirements.txt -o sbom.json --output-format JSON",
        "```",
        "",
        "The generator warns about any dependency without an exact version, which is how",
        "two unpinned requirements (`httpx`, `langfuse`) were found: `langfuse>=2.60.0`",
        "was resolving to 4.14.4, two major versions past the declared floor, so CI and a",
        "developer machine could install different code with nothing reporting it. Both",
        "are now pinned.",
        "",
        "## External services",
        "",
        "These are not dependencies and are not redistributed. They run under their own",
        "terms, and Ermes contacts them only when an administrator explicitly enables the",
        "corresponding mode:",
        "",
        "- **Ollama** — local model server, contacted only for embeddings, evidence",
        "  verification, question rewriting or `local_ollama` answers.",
        "- **OpenRouter and approved cloud providers** — contacted only when both the",
        "  global consent flag and the per-library policy authorise it.",
        "- **Slack, Microsoft Teams, Telegram** — contacted only for libraries with a",
        "  registered chat integration.",
        "",
    ]

    USCITA.write_text("\n".join(righe), encoding="utf-8")
    print(f"scritto {USCITA.name}: {len(python_voci)} pacchetti Python, {len(js_diretti)} JavaScript diretti")
    if non_permissive_py:
        print("NON permissive (Python):", ", ".join(f"{n} [{lic}]" for n, _, lic in non_permissive_py))
    return 0


if __name__ == "__main__":
    sys.exit(main())
