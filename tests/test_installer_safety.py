"""L'installer non deve mai portare con se' segreti, dati o ambienti virtuali dello sviluppatore.

Una revisione ha trovato che lo script impacchettava il `.env` vero (chiavi e password), la cartella
`data/` (database e utenti) e `.venv-ermes`. Chi installava l'app riceveva i segreti di chi l'aveva
compilata. Questo test legge lo script e impedisce che torni.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISS = ROOT / "scripts" / "installer" / "ermes_setup.iss"
# Si producono compilando (build_exe.ps1, vite build): in un checkout pulito non esistono.
PRODOTTI_DI_BUILD = {"Ermes.exe"}


def _sources() -> list[str]:
    righe = [r for r in ISS.read_text(encoding="utf-8").splitlines() if r.strip().startswith("Source:")]
    return [re.search(r'Source:\s*"([^"]+)"', r).group(1).replace("\\", "/") for r in righe]  # type: ignore[union-attr]


def test_the_installer_never_ships_secrets_data_or_a_virtualenv():
    vietati = ("/.env", "/data", ".venv", "/security", "/storage", "/backups", "/logs", ".sqlite")
    for src in _sources():
        if src.endswith("/.env.example") or src.endswith(".env.example"):
            continue  # il modello senza segreti va bene
        assert not any(v in src for v in vietati), f"l'installer include un percorso sensibile: {src}"


def test_every_folder_the_installer_copies_exists_and_the_app_code_is_complete():
    for src in _sources():
        base = src.replace("../../", "").split("/*")[0]
        assert (ROOT / base).exists() or base in PRODOTTI_DI_BUILD or base.startswith("frontend/dist"), f"percorso inesistente: {src}"
    cartelle = {s.replace("../../", "").split("/*")[0] for s in _sources()}
    # `core` e `config` sono importati dall'API: senza, l'app installata non parte
    assert {"api", "core", "config"} <= cartelle
