"""Create local-only credentials for a first Ermes Knowledge demo.

This script is deliberately opt-in. It writes an administrator password to the
untracked .env and a local reminder file that is also excluded from Git.

Corretto il 10 settembre 2026: `has_setting` guardava solo se la variabile era
presente, quindi trovando `ERMES_ADMIN_PASSWORD=CHANGE_ME` — copiata da
`.env.example` al primo passo del README — stampava
LOCAL_AUTH_ALREADY_CONFIGURED e non generava niente. Un'installazione appena
clonata restava con una password nota a chiunque conosca il progetto.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
LOGIN_FILE = ROOT / "LOCAL_LOGIN.txt"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _is_placeholder(valore: str) -> bool:
    """Stessa lista di config/validation.py, che rifiuta l'avvio con uno di
    questi valori: le due difese devono concordare, altrimenti questo script
    genererebbe una credenziale che il controllo poi rifiuta, o viceversa."""
    from config.validation import _is_placeholder as _controllo_condiviso

    return _controllo_condiviso(valore)


def has_setting(content: str, name: str) -> bool:
    """Se `name` e' impostata a un valore utilizzabile: un segnaposto no."""
    for line in content.splitlines():
        if not line.startswith(f"{name}="):
            continue
        valore = line.split("=", 1)[1].strip()
        if valore and not _is_placeholder(valore):
            return True
    return False


def provision(env_file: Path, login_file: Path) -> int:
    """Genera le credenziali se mancano.

    Separata da `main()` per essere verificabile su file temporanei: i percorsi
    del repository sono un default della riga di comando, non un vincolo della
    logica. Prima non lo erano, e un test non poteva esercitarla senza
    scrivere nel `.env` reale dello sviluppatore.
    """
    content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    if has_setting(content, "ERMES_ADMIN_PASSWORD") or has_setting(content, "ERMES_API_KEY"):
        print("LOCAL_AUTH_ALREADY_CONFIGURED")
        return 0

    password = secrets.token_urlsafe(24)
    username = "admin"
    # Le righe segnaposto vanno rimosse, non solo scavalcate: aggiungere la
    # credenziale nuova in fondo funziona (per dotenv vince l'ultima) ma
    # lascerebbe nel file una riga che sembra una password attiva.
    righe = [
        riga
        for riga in content.splitlines()
        if not (riga.startswith("ERMES_ADMIN_PASSWORD=") and _is_placeholder(riga.split("=", 1)[1].strip()))
    ]
    additions = (
        "\n# Credenziali locali generate per la demo Ermes Knowledge\n"
        f"ERMES_ADMIN_USERNAME={username}\n"
        f"ERMES_ADMIN_PASSWORD={password}\n"
    )
    env_file.write_text("\n".join(righe).rstrip() + additions, encoding="utf-8")
    login_file.write_text(
        "Ermes Knowledge — credenziali locali demo\n"
        f"Username: {username}\n"
        f"Password: {password}\n\n"
        "Questo file e .env non devono essere caricati su GitHub. Elimina questo promemoria dopo il primo accesso.\n",
        encoding="utf-8",
    )
    print("LOCAL_AUTH_PROVISIONED")
    print(f"login_file={login_file.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision local Ermes demo credentials.")
    parser.add_argument("--write", action="store_true", help="Create credentials only when they are missing.")
    args = parser.parse_args()
    if not args.write:
        parser.error("Use --write to create local credentials.")
    return provision(ENV_FILE, LOGIN_FILE)


if __name__ == "__main__":
    raise SystemExit(main())
