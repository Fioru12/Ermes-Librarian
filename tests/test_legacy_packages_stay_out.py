"""Le dipendenze del motore storico WinSarp non devono rientrare nel prodotto.

Il motore e' stato rimosso dal repository il 18 settembre 2026 (era congelato
in `legacy_winsarp/` da agosto, e il suo interruttore importava router che
non esistevano piu'). Restano i suoi pacchetti come tentazione: LlamaIndex,
ChromaDB e il client Ollama, che da soli trascinavano 94 pacchetti
(kubernetes, onnxruntime, grpcio, pandas, nltk, tokenizers...) dentro ogni
deployment e dentro il container. Superficie del prodotto: 56 pacchetti; con
loro: 150.

Non e' una questione di megabyte. Ogni pacchetto installato e' una CVE
possibile e una riga di SBOM che qualcuno, in una valutazione aziendale, deve
giustificare.
"""

import ast
import pathlib
import re
import subprocess

RADICE = pathlib.Path(__file__).resolve().parents[1]

# Pacchetti che esistevano solo per il motore storico.
SOLO_LEGACY = ("llama-index", "llama_index", "chromadb", "ollama")

# tests/test_integration.py e' opt-in con ERMES_TEST_INTEGRATION=1 e prova
# chromadb solo se installato a mano.
DEROGHE = {"tests/test_integration.py"}


def _file_di_prodotto() -> list[str]:
    """Solo i file tracciati: `rglob` prenderebbe anche backup e artefatti non
    versionati."""
    tracciati = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=RADICE,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [p for p in tracciati if p not in DEROGHE and not p.startswith("tests/")]


def test_the_product_requirements_do_not_carry_the_legacy_engine():
    righe = [
        r.strip().lower()
        for r in (RADICE / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if r.strip() and not r.strip().startswith("#")
    ]
    colpevoli = [r for r in righe if any(r.startswith(p.lower()) for p in SOLO_LEGACY)]
    assert colpevoli == [], "requirements.txt contiene le dipendenze del motore storico: " + ", ".join(colpevoli)


def test_no_product_module_imports_the_legacy_stack():
    colpevoli = []
    for percorso in _file_di_prodotto():
        try:
            albero = ast.parse((RADICE / percorso).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for nodo in ast.walk(albero):
            nomi: list[str] = []
            if isinstance(nodo, ast.Import):
                nomi = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level:
                # `from .ollama import OllamaProvider` (relativo) e' il provider
                # interno core/ai/providers/ollama.py, non il pacchetto PyPI.
                nomi = [nodo.module]
            for nome in nomi:
                if nome.split(".")[0] in {"llama_index", "chromadb", "ollama", "legacy_winsarp"}:
                    colpevoli.append(f"{percorso}: import {nome}")
    assert colpevoli == [], "il prodotto importa il motore storico:\n" + "\n".join(colpevoli)


def test_nothing_mentions_the_legacy_stack_any_more():
    """Con il motore rimosso non esistono piu' deroghe: una menzione in un
    modulo di prodotto e' un rientro dalla finestra. I commenti storici che
    spiegano PERCHE' qualcosa e' fatto in un certo modo restano ammessi."""
    citazioni = set()
    for percorso in _file_di_prodotto():
        testo = (RADICE / percorso).read_text(encoding="utf-8", errors="ignore")
        codice = "\n".join(riga for riga in testo.splitlines() if not riga.lstrip().startswith("#"))
        if re.search(r"\b(llama_index|chromadb|legacy_winsarp)\b", codice):
            citazioni.add(percorso)
    assert citazioni == set(), "il motore storico e' nominato in: " + ", ".join(sorted(citazioni))
