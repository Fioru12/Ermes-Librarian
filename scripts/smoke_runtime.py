"""Smoke test a runtime: esercita l'app completa con lifespan reale.

A differenza dei test di suite (TestClient senza context manager, lifespan
mai attivato), qui partono davvero: caricamento sessioni persistite, recovery
job, sweeper ingestion in thread. Poi l'intero flusso utente.
"""
import io
import os
import sys
import tempfile
import time
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="ermes_smoke_")
os.environ["ERMES_BASE_DIR"] = TMP
os.environ["ERMES_ADMIN_USERNAME"] = "owner"
os.environ["ERMES_ADMIN_PASSWORD"] = "StrongSmoke!123"
os.environ["ERMES_API_KEY"] = ""
os.environ["ERMES_BACKUP_ENABLED"] = "0"
os.environ["ERMES_INGESTION_POLL_SECONDS"] = "2"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def step(name: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(name)
    print(("  OK " if condition else "FAIL ") + name + ((" — " + detail) if detail else ""))


def main() -> int:
    from api import app

    # 'with' attiva il lifespan vero: sessioni, recovery, sweeper, shutdown.
    with TestClient(app) as client:
        r = client.get("/health")
        body = r.json()
        step("health risponde", r.status_code == 200)
        step("health espone coerenza indice", "library_index_ok" in body and body.get("library_index_ok") is True)
        step("consistency negato ad anonimo", client.get("/health/index-consistency").status_code == 401)

        r = client.post("/api/auth/login", json={"username": "owner", "password": "StrongSmoke!123"})
        step("login owner", r.status_code == 200 and r.json()["role"] == "admin")

        from api.auth import _SESSIONS
        step("sessione persistita su SQLite",
             len(_SESSIONS) >= 1 and (Path(TMP) / "security" / "sessions.sqlite3").exists())

        codes = [client.post("/api/auth/login", json={"username": "victim", "password": "sbagliata"}).status_code for _ in range(5)]
        locked = client.post("/api/auth/login", json={"username": "victim", "password": "qualsiasi"}).status_code
        step("lockout dopo 5 tentativi", codes.count(401) == 5 and locked == 429)

        lib = client.post("/api/libraries", json={"name": "Fumo", "description": "", "visibility": "private"}).json()
        library_id = lib["id"]
        content = b"# Manuale\nLe note spese vanno inviate entro dieci giorni dal viaggio."
        files = {"file": ("manuale.md", io.BytesIO(content), "text/markdown")}
        up = client.post(f"/api/libraries/{library_id}/documents", files=files)
        doc_id = up.json()["id"]
        job_id = up.json()["ingestion_job_id"]
        step("upload accodato", up.status_code == 201 and up.json()["status"] == "queued")

        deadline = time.time() + 30
        status = ""
        while time.time() < deadline:
            listed = client.get(f"/api/libraries/{library_id}/documents").json()["items"]
            status = next((d["status"] for d in listed if d["id"] == doc_id), "")
            if status in {"ready", "failed"}:
                break
            time.sleep(0.3)
        step("documento indicizzato (ready)", status == "ready", f"stato finale: {status}")
        jobs = client.get(f"/api/libraries/{library_id}/ingestion-jobs").json()["items"]
        step("job chiuso correttamente", any(j["id"] == job_id and j["status"] == "ready" for j in jobs))

        hits = client.get(f"/api/libraries/{library_id}/search", params={"q": "note spese"}).json()
        step("ricerca trova passaggi", len(hits["items"]) >= 1)
        answer = client.post(f"/api/libraries/{library_id}/ask", json={"question": "Entro quando si inviano le note spese?"}).json()
        step("ask produce evidenze citate",
             answer["status"] in {"answered", "abstained"},
             f"coverage={answer['evidence']['coverage']}, citazioni={len(answer['citations'])}")
        step("citazione ha documento/versione/locator",
             bool(answer["citations"]) and all(k in answer["citations"][0] for k in ("document_id", "version", "locator")))

        dl = client.get(f"/api/libraries/{library_id}/documents/{doc_id}/download")
        step("download originale", dl.status_code == 200 and dl.content == content)

        rep = client.get("/health/index-consistency").json()
        step("report coerenza admin ok", rep["ok"] is True and rep["checked_documents"] >= 1,
             f"problemi: {rep['issue_count']}")

        client.post("/api/auth/logout")
        step("logout invalida la sessione", client.get("/api/libraries").status_code == 401)

    return restart_check()


def restart_check() -> int:
    """Riavvio simulato: memoria vuota ma disco intatto -> sessione sopravvive."""
    from api import app as app2
    from api.auth import _SESSIONS, load_persisted_sessions

    token = None
    with TestClient(app2) as client2:
        r = client2.post("/api/auth/login", json={"username": "owner", "password": "StrongSmoke!123"})
        if r.status_code == 200:
            token = r.cookies.get("ermes_session")
    step("secondo avvio: login ok", token is not None)

    with TestClient(app2):
        dict.clear(_SESSIONS)  # simula il processo nuovo: solo la memoria e' vuota
        load_persisted_sessions()  # l'avvio reale ricarica dal disco...
        client3 = TestClient(app2)
        client3.cookies.set("ermes_session", token or "")
        ok = client3.get("/api/auth/me").status_code == 200
        step("sessione sopravvive al riavvio (persistenza)", ok)

    print(f"\nRISULTATO: {len(PASS)} passati, {len(FAIL)} falliti")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
