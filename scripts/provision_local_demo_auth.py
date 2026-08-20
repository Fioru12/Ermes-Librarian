"""Create local-only credentials for a first Ermes Knowledge demo.

This script is deliberately opt-in. It writes an administrator password to the
untracked .env and a local reminder file that is also excluded from Git.
"""
from __future__ import annotations

import argparse
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
LOGIN_FILE = ROOT / "LOCAL_LOGIN.txt"


def has_setting(content: str, name: str) -> bool:
    return any(line.startswith(f"{name}=") and line.split("=", 1)[1].strip() for line in content.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision local Ermes demo credentials.")
    parser.add_argument("--write", action="store_true", help="Create credentials only when they are missing.")
    args = parser.parse_args()
    if not args.write:
        parser.error("Use --write to create local credentials.")

    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    if has_setting(content, "ERMES_ADMIN_PASSWORD") or has_setting(content, "ERMES_API_KEY"):
        print("LOCAL_AUTH_ALREADY_CONFIGURED")
        return 0

    password = secrets.token_urlsafe(24)
    username = "admin"
    additions = f"\n# Credenziali locali generate per la demo Ermes Knowledge\nERMES_ADMIN_USERNAME={username}\nERMES_ADMIN_PASSWORD={password}\n"
    ENV_FILE.write_text(content.rstrip() + additions, encoding="utf-8")
    LOGIN_FILE.write_text(
        "Ermes Knowledge — credenziali locali demo\n"
        f"Username: {username}\n"
        f"Password: {password}\n\n"
        "Questo file e .env non devono essere caricati su GitHub. Elimina questo promemoria dopo il primo accesso.\n",
        encoding="utf-8",
    )
    print("LOCAL_AUTH_PROVISIONED")
    print("login_file=LOCAL_LOGIN.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
