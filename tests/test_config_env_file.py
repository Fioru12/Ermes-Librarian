"""ERMES_ENV_FILE sceglie quale .env caricare; vuota = nessuno.

I test la usano per non dipendere dal .env di chi sviluppa. Si prova in un processo separato perche'
la configurazione legge il file una sola volta, all'importazione.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _valore_letto(tmp_path: Path, env_file: str) -> str:
    codice = "import config, os; print(os.environ.get('ERMES_PROVA_ENV_FILE', '<assente>'))"
    ambiente = {k: v for k, v in os.environ.items() if k != "ERMES_PROVA_ENV_FILE"}
    ambiente["ERMES_ENV_FILE"] = env_file
    uscita = subprocess.run(
        [sys.executable, "-c", codice], cwd=ROOT, env=ambiente, capture_output=True, text=True, check=True
    )
    return uscita.stdout.strip().splitlines()[-1]


def test_the_named_env_file_is_loaded(tmp_path):
    file_env = tmp_path / "prova.env"
    file_env.write_text("ERMES_PROVA_ENV_FILE=letto\n", encoding="utf-8")
    assert _valore_letto(tmp_path, str(file_env)) == "letto"


def test_an_empty_value_loads_no_env_file(tmp_path):
    assert _valore_letto(tmp_path, "") == "<assente>"
