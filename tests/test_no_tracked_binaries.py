"""Un eseguibile compilato non si puo' verificare contro i sorgenti: nel repository non ci sta."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = (".exe", ".dll", ".msi", ".bin", ".so", ".dylib")


def test_no_compiled_executables_are_tracked_by_git():
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if out.returncode != 0:  # non e' un checkout git (archivio sorgenti): niente da controllare
        return
    tracked = [f for f in out.stdout.splitlines() if f.lower().endswith(FORBIDDEN)]
    assert not tracked, f"binari tracciati in git (compilali da sorgente): {tracked}"
