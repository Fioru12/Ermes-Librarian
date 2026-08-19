"""Load and validate the fictional Northstar Works demo against a running Ermes instance.

The script reads local credentials from the untracked environment only. It never
prints credentials, sends documents outside localhost, or enables cloud AI.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "examples" / "demo-corpus"
QUALITY_CORPUS = ROOT / "examples" / "demo-corpus-quality"
BASE_URL = os.environ.get("ERMES_DEMO_URL", "http://127.0.0.1:8502").rstrip("/")
LIBRARY_NAME = "Northstar Works Demo"
QUALITY_LIBRARY_NAME = "Meridian Precision Works Demo"
EXPECTED_ANSWERS = [
    ("How much notice is required for annual leave?", "employee-handbook.md"),
    ("When is an expense report due?", "expense-policy.md"),
    ("Who approves access before IT provisions it?", "it-access-policy.md"),
]
ABSTENTION_QUESTION = "What is the warranty period for customer hardware?"
QUALITY_EXPECTED_ANSWER = ("Who approves the disposition of a nonconforming batch?", "nonconformity-procedure.md")
# Asked against the quality library on purpose: the correct source lives in
# the Northstar library, so retrieval must not cross the boundary. Chosen to
# share no keyword with the Meridian corpus (unlike the annual-leave
# question, which collides on "required" with the nonconformity procedure
# and would falsely look like a cross-library leak instead of a keyword
# false positive within Meridian's own content).
ISOLATION_QUESTION = "What is the annual learning budget per employee?"


def configure_environment() -> None:
    """Load .env if python-dotenv is available, without echoing its values."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def require_ok(response: httpx.Response, message: str) -> dict:
    if response.is_success:
        return response.json()
    raise RuntimeError(f"{message}: HTTP {response.status_code}")


def authenticate(client: httpx.Client) -> None:
    password = os.environ.get("ERMES_ADMIN_PASSWORD", "")
    username = os.environ.get("ERMES_ADMIN_USERNAME", "admin")
    if password:
        require_ok(
            client.post("/api/auth/login", json={"username": username, "password": password}),
            "Login locale non riuscito",
        )
        return

    api_key = os.environ.get("ERMES_API_KEY", "")
    if api_key:
        client.headers["Authorization"] = f"Bearer {api_key}"
        return
    raise RuntimeError("Configura ERMES_ADMIN_PASSWORD oppure ERMES_API_KEY nel file .env locale")


def find_or_create_library(client: httpx.Client, name: str, description: str) -> dict:
    libraries = require_ok(client.get("/api/libraries"), "Impossibile leggere le biblioteche")["items"]
    for library in libraries:
        if library["name"] == name:
            return library
    return require_ok(
        client.post(
            "/api/libraries",
            json={"name": name, "description": description, "visibility": "private"},
        ),
        f"Impossibile creare la biblioteca demo {name}",
    )


def wait_for_ingestion(client: httpx.Client, library_id: str, filenames: set[str]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        jobs = require_ok(client.get(f"/api/libraries/{library_id}/ingestion-jobs"), "Impossibile leggere i job")["items"]
        latest = {job["filename"]: job for job in jobs if job["filename"] in filenames}
        if filenames <= latest.keys() and all(job["status"] == "ready" for job in latest.values()):
            return
        failed = [job for job in latest.values() if job["status"] == "failed"]
        if failed:
            raise RuntimeError(f"Indicizzazione demo fallita: {failed[0].get('error_message', 'errore sconosciuto')}")
        time.sleep(0.5)
    raise RuntimeError("Timeout durante l'indicizzazione del corpus demo")


def ensure_library_with_documents(client: httpx.Client, name: str, description: str, files: list[Path]) -> str:
    if any(not item.is_file() for item in files):
        raise RuntimeError(f"Corpus demo incompleto per {name}")
    library = find_or_create_library(client, name, description)
    library_id = library["id"]
    require_ok(
        client.put(f"/api/libraries/{library_id}/assistant-policy", json={"mode": "evidence_only"}),
        "Impossibile impostare la policy evidence_only",
    )
    existing = require_ok(client.get(f"/api/libraries/{library_id}/documents"), "Impossibile leggere i documenti")["items"]
    existing_names = {document["filename"] for document in existing if document["status"] == "ready"}
    for item in files:
        if item.name in existing_names:
            continue
        with item.open("rb") as stream:
            require_ok(
                client.post(
                    f"/api/libraries/{library_id}/documents",
                    files={"file": (item.name, stream, "text/markdown")},
                ),
                f"Upload fallito per {item.name}",
            )
    wait_for_ingestion(client, library_id, {item.name for item in files})
    return library_id


def ask(client: httpx.Client, library_id: str, question: str) -> dict:
    return require_ok(client.post(f"/api/libraries/{library_id}/ask", json={"question": question}), "Domanda demo fallita")


def main() -> int:
    configure_environment()
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        health = require_ok(client.get("/health"), "Ermes non e raggiungibile")
        if health.get("status") != "healthy":
            raise RuntimeError("Ermes non e pronto: health check non healthy")
        authenticate(client)

        northstar_id = ensure_library_with_documents(
            client, LIBRARY_NAME, "Corpus fittizio per dimostrare citazioni e astensione di Ermes Knowledge.",
            [CORPUS / "employee-handbook.md", CORPUS / "expense-policy.md", CORPUS / "it-access-policy.md"],
        )
        quality_id = ensure_library_with_documents(
            client, QUALITY_LIBRARY_NAME, "Corpus fittizio per dimostrare l'isolamento tra biblioteche.",
            [QUALITY_CORPUS / "nonconformity-procedure.md", QUALITY_CORPUS / "document-review-policy.md"],
        )

        for question, expected_file in EXPECTED_ANSWERS:
            response = ask(client, northstar_id, question)
            cited_files = {citation["filename"] for citation in response.get("citations", [])}
            if response.get("status") != "answered" or expected_file not in cited_files:
                raise RuntimeError(f"Risposta demo non verificabile per: {question}")

        abstention = ask(client, northstar_id, ABSTENTION_QUESTION)
        if abstention.get("status") != "abstained" or abstention.get("citations"):
            raise RuntimeError("L'assistente non si e astenuto dalla domanda fuori corpus")

        quality_question, quality_expected_file = QUALITY_EXPECTED_ANSWER
        quality_response = ask(client, quality_id, quality_question)
        quality_cited = {citation["filename"] for citation in quality_response.get("citations", [])}
        if quality_response.get("status") != "answered" or quality_expected_file not in quality_cited:
            raise RuntimeError("Risposta demo non verificabile per la biblioteca Meridian")

        # The correct source for this question lives in the Northstar
        # library. Asked against Meridian, retrieval must not cross the
        # boundary — this is what proves library isolation, not just states it.
        isolation = ask(client, quality_id, ISOLATION_QUESTION)
        if isolation.get("status") != "abstained" or isolation.get("citations"):
            raise RuntimeError("Isolamento tra biblioteche non verificato: la biblioteca Meridian ha risposto a una domanda Northstar")

    print("DEMO_VALIDATION_OK")
    print(f"library={LIBRARY_NAME}; library={QUALITY_LIBRARY_NAME}")
    print("documents=5; cited_answers=4; abstention=verified; isolation=verified; assistant_mode=evidence_only")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (httpx.HTTPError, RuntimeError) as error:
        print(f"DEMO_VALIDATION_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1) from error
