"""Il motore storico WinSarp non deve rientrare nel prodotto dalla finestra.

`legacy_winsarp/` e' codice congelato: il README lo dichiara fuori dal percorso
di prodotto, e' spento salvo `ERMES_ENABLE_LEGACY_WINSARP`, e la CI non lo
esegue (`testpaths = ["tests"]`).

Fino all'11 settembre 2026 le sue dipendenze stavano pero' in
requirements.txt: LlamaIndex, ChromaDB e il client Ollama, che da soli
trascinavano 94 pacchetti (kubernetes, onnxruntime, grpcio, pandas, nltk,
tokenizers...) dentro ogni deployment del prodotto e dentro il container.
Superficie del prodotto: 56 pacchetti. Con il legacy: 150.

Non e' una questione di megabyte. Ogni pacchetto installato e' una CVE
possibile e una riga di SBOM che qualcuno, in una valutazione aziendale, deve
giustificare — e giustificarla con "serve a un motore che teniamo spento" e'
una risposta che costa credibilita'.
"""

import ast
import pathlib
import re
import subprocess

RADICE = pathlib.Path(__file__).resolve().parents[1]

# Pacchetti che esistono solo per legacy_winsarp/.
SOLO_LEGACY = ("llama-index", "llama_index", "chromadb", "ollama")

# I due punti del prodotto autorizzati a nominare ChromaDB, entrambi dietro un
# interruttore e nessuno dei due a livello di modulo:
#   - api/health.py lo sonda solo se ENABLE_LEGACY_WINSARP e' attivo, in
#     try/except, per riportare se l'archivio storico e' leggibile;
#   - tests/test_integration.py e' opt-in con ERMES_TEST_INTEGRATION=1.
DEROGHE = {"api/health.py", "tests/test_integration.py"}


def _file_di_prodotto() -> list[str]:
    """Solo i file tracciati: `rglob` prenderebbe anche backup e artefatti non
    versionati, ed e' gia' successo due volte che un test passasse in locale e
    fallisse in CI per questo."""
    tracciati = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=RADICE,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [p for p in tracciati if not p.startswith("legacy_winsarp/")]


def test_the_product_requirements_do_not_carry_the_legacy_engine():
    requisiti = (RADICE / "requirements.txt").read_text(encoding="utf-8")

    intrusi = []
    for riga in requisiti.splitlines():
        riga = riga.split("#")[0].strip()
        if not riga:
            continue
        nome = re.split(r"[=<>!\[]", riga)[0].strip().lower()
        if any(nome.startswith(p) for p in SOLO_LEGACY):
            intrusi.append(nome)

    assert intrusi == [], (
        "requirements.txt torna a installare le dipendenze del motore storico: "
        + ", ".join(intrusi)
        + ". Vanno in requirements-legacy.txt."
    )


def test_the_legacy_requirements_file_builds_on_the_product_one():
    """Chi installa il legacy deve ottenere anche il prodotto, altrimenti la
    divisione trasforma un `pip install` in due passaggi da ricordare."""
    legacy = (RADICE / "requirements-legacy.txt").read_text(encoding="utf-8")

    assert "-r requirements.txt" in legacy
    for pacchetto in ("llama-index-core", "chromadb", "ollama"):
        assert pacchetto in legacy, f"{pacchetto} non e' in requirements-legacy.txt"


def test_no_product_module_imports_the_legacy_stack_at_import_time():
    """Un import a livello di modulo renderebbe la dipendenza obbligatoria di
    fatto, qualunque cosa dica requirements.txt: l'applicazione non partirebbe
    senza il pacchetto."""
    colpevoli = []

    for rel in _file_di_prodotto():
        percorso = RADICE / rel
        try:
            albero = ast.parse(percorso.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        # Solo il corpo del modulo: un import dentro una funzione e' differito
        # e paga il prezzo soltanto se quella funzione viene chiamata.
        for nodo in albero.body:
            moduli = []
            if isinstance(nodo, ast.Import):
                moduli = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
                # `level == 0` esclude gli import relativi: il prodotto ha un
                # proprio `core/ai/providers/ollama.py`, e `from .ollama import
                # OllamaProvider` non ha nulla a che vedere col pacchetto PyPI
                # omonimo.
                moduli = [nodo.module]
            for modulo in moduli:
                radice = modulo.split(".")[0].lower()
                if radice in ("llama_index", "chromadb", "ollama"):
                    colpevoli.append(f"{rel}: import {modulo}")

    assert colpevoli == [], "il prodotto importa il motore storico all'avvio:\n" + "\n".join(colpevoli)


def test_only_the_two_gated_places_mention_the_legacy_stack():
    """Se compare un terzo punto, va deciso di proposito: o e' dietro il flag,
    o e' una dipendenza del prodotto e allora torna in requirements.txt."""
    citazioni = set()

    for rel in _file_di_prodotto():
        testo = (RADICE / rel).read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\b(import\s+chromadb|from\s+chromadb|import\s+llama_index|from\s+llama_index)", testo):
            citazioni.add(rel.replace("\\", "/"))

    assert citazioni <= DEROGHE, (
        "nuovi punti del prodotto che usano il motore storico: "
        + ", ".join(sorted(citazioni - DEROGHE))
        + ". Vanno dietro ERMES_ENABLE_LEGACY_WINSARP, o la dipendenza torna obbligatoria."
    )
