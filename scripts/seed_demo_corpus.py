#!/usr/bin/env python3
"""scripts/seed_demo_corpus.py
Popola un'istanza Ermes Knowledge in esecuzione con i documenti demo fittizi
(Northstar Works e Meridian Precision Works) per preparare la demo in 1 secondo.

Uso:
    python scripts/seed_demo_corpus.py
    python scripts/seed_demo_corpus.py --url http://127.0.0.1:8502 --username admin --password admin
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NORTHSTAR_DIR = ROOT / "examples" / "demo-corpus"
MERIDIAN_DIR = ROOT / "examples" / "demo-corpus-quality"


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def require_ok(response: httpx.Response, message: str) -> dict[str, Any]:
    if response.is_success:
        data: Any = response.json()
        if isinstance(data, dict):
            return dict(data)
        return {"data": data}
    raise RuntimeError(f"{message}: HTTP {response.status_code} - {response.text}")


def authenticate(client: httpx.Client, username: str, password: str, api_key: str) -> None:
    if password:
        require_ok(
            client.post("/api/auth/login", json={"username": username, "password": password}),
            "Login locale non riuscito",
        )
        return
    if api_key:
        client.headers["Authorization"] = f"Bearer {api_key}"
        return
    raise RuntimeError("Specificare password o api_key per l'autenticazione")


def find_or_create_library(client: httpx.Client, name: str, description: str) -> dict[str, Any]:
    libraries: list[Any] = require_ok(client.get("/api/libraries"), "Impossibile leggere le biblioteche")["items"]
    for library in libraries:
        if isinstance(library, dict) and library.get("name") == name:
            return dict(library)
    res = require_ok(
        client.post(
            "/api/libraries",
            json={"name": name, "description": description, "visibility": "private"},
        ),
        f"Impossibile creare la biblioteca demo '{name}'",
    )
    return dict(res)


def wait_for_ingestion(client: httpx.Client, library_id: str, filenames: set[str], timeout_sec: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        jobs = require_ok(client.get(f"/api/libraries/{library_id}/ingestion-jobs"), "Impossibile leggere i job")[
            "items"
        ]
        latest = {job["filename"]: job for job in jobs if job["filename"] in filenames}
        if filenames <= latest.keys() and all(job["status"] == "ready" for job in latest.values()):
            return
        failed = [job for job in latest.values() if job["status"] == "failed"]
        if failed:
            raise RuntimeError(f"Indicizzazione fallita: {failed[0].get('error_message', 'errore sconosciuto')}")
        time.sleep(0.5)
    raise RuntimeError("Timeout durante l'indicizzazione dei documenti demo")


def seed_library(client: httpx.Client, name: str, description: str, folder: Path) -> tuple[str, int]:
    if not folder.is_dir():
        raise RuntimeError(f"Cartella demo non trovata: {folder}")
    files = [f for f in folder.glob("*.md") if f.name not in {"README.md", "questions.md"}]
    if not files:
        raise RuntimeError(f"Nessun file markdown trovato in: {folder}")

    library = find_or_create_library(client, name, description)
    library_id = str(library["id"])

    existing = require_ok(client.get(f"/api/libraries/{library_id}/documents"), "Impossibile leggere documenti")[
        "items"
    ]
    existing_ready = {doc["filename"] for doc in existing if doc.get("status") == "ready"}

    to_upload = [f for f in files if f.name not in existing_ready]
    for item in to_upload:
        with item.open("rb") as stream:
            require_ok(
                client.post(
                    f"/api/libraries/{library_id}/documents",
                    files={"file": (item.name, stream, "text/markdown")},
                ),
                f"Upload fallito per {item.name}",
            )

    if to_upload:
        wait_for_ingestion(client, library_id, {item.name for item in to_upload})

    return library_id, len(files)


def main() -> int:
    load_env()
    default_url = os.environ.get("ERMES_DEMO_URL", "http://127.0.0.1:8502").rstrip("/")
    default_user = os.environ.get("ERMES_ADMIN_USERNAME", "admin")
    default_pass = os.environ.get("ERMES_ADMIN_PASSWORD", "admin")
    default_key = os.environ.get("ERMES_API_KEY", "")

    parser = argparse.ArgumentParser(description="Popola Ermes Knowledge con i documenti demo aziendali.")
    parser.add_argument("--url", default=default_url, help=f"URL del backend Ermes (default: {default_url})")
    parser.add_argument("--username", default=default_user, help=f"Username admin (default: {default_user})")
    parser.add_argument("--password", default=default_pass, help="Password admin")
    parser.add_argument("--api-key", default=default_key, help="API Key (opzionale)")
    args = parser.parse_args()

    print("\n========================================================")
    print("  🚀 ERMES KNOWLEDGE — SEEDING DEMO CORPUS")
    print("========================================================")
    print(f"Target URL: {args.url}")

    with httpx.Client(base_url=args.url, timeout=30.0) as client:
        try:
            # 1. Verifica raggiungibilità
            health_res = client.get("/health")
            if not health_res.is_success:
                print(f"[!] Errore connessione /health (HTTP {health_res.status_code})")
                return 1
            print("[OK] Backend Ermes attivo e raggiungibile.")

            # 2. Autenticazione
            authenticate(client, args.username, args.password, args.api_key)
            print(f"[OK] Autenticato come '{args.username}'.")

            # 3. Seeding Northstar Works
            ns_id, ns_count = seed_library(
                client,
                name="Northstar Works Demo",
                description="Manuale dipendenti, policy note spese e accessi IT",
                folder=NORTHSTAR_DIR,
            )
            print(f"[OK] Biblioteca 'Northstar Works Demo' pronta ({ns_count} documenti, ID: {ns_id[:8]}...).")

            # 4. Seeding Meridian Precision Works
            mer_id, mer_count = seed_library(
                client,
                name="Meridian Precision Works Demo",
                description="Procedure di controllo qualità e non conformità",
                folder=MERIDIAN_DIR,
            )
            print(f"[OK] Biblioteca 'Meridian Precision Works Demo' pronta ({mer_count} documenti, ID: {mer_id[:8]}...).")

            print("\n========================================================")
            print("  ✨ SEEDING COMPLETATO CON SUCCESSO!")
            print("========================================================")
            print("\nDomande pronte da provare in Chat:")
            print("  • \"Quanti giorni di preavviso servono per le ferie annuali?\" (Northstar)")
            print("  • \"Entro quando va inviata la nota spese?\" (Northstar)")
            print("  • \"Chi approva la disposizione di un lotto non conforme?\" (Meridian)")
            print("  • \"Qual è la procedura di garanzia per l'hardware fornito?\" (Test di astensione/rifiuto)")
            print("\nApri il browser su: http://127.0.0.1:3000\n")
            return 0

        except Exception as err:
            print(f"\n[ERRORE] Seeding fallito: {err}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
