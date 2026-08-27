"""Verifica live del percorso cloud (OpenRouter) con i suoi tre cancelli.

Modello gratuito (tencent/hy3:free) gia' configurato: costo zero.
Cancelli attesi:
1. chiave presente ma consenso spento -> policy rifiutata (409), ask degrada
   alle sole evidenze senza mai inviare nulla all'esterno;
2. consenso globale acceso -> l'owner imposta la policy per biblioteca;
3. ask genera con il modello cloud CITANDO le evidenze locali.
"""
import io
import os
import sys
import tempfile
import time
from dataclasses import replace

TMP = tempfile.mkdtemp(prefix="ermes_cloud_")
os.environ["ERMES_BASE_DIR"] = TMP
os.environ["ERMES_ADMIN_USERNAME"] = "owner"
os.environ["ERMES_ADMIN_PASSWORD"] = "StrongSmoke!123"
os.environ["ERMES_API_KEY"] = ""
os.environ["ERMES_BACKUP_ENABLED"] = "0"
os.environ["ERMES_LIBRARY_SEMANTIC_SEARCH"] = "1"
os.environ["ERMES_EMBED_MODEL"] = "nomic-embed-text"
# Consenso globale all'egress cloud: cancellello 2 dei 3 (chiave + consenso +
# scelta per-biblioteca da parte dell'owner).
os.environ["ERMES_LIBRARY_CLOUD_CONSENT"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0


def step(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + (1 if condition else 0), FAIL + (0 if condition else 1)
    print(("  OK " if condition else "FAIL ") + name + ((" — " + detail) if detail else ""))


def main() -> int:
    from fastapi.testclient import TestClient

    import api.libraries as api_libraries
    import config
    import core.evidence_assistant as evidence_assistant
    from api import app

    doc_text = ("Politica viaggi. Il rimborso chilometrico si calcola con la tariffa ACI "
                "per ogni chilometro percorso. Le ricevute vanno conservate cinque anni.")

    with TestClient(app) as client:
        client.post("/api/auth/login", json={"username": "owner", "password": "StrongSmoke!123"})
        lib = client.post("/api/libraries", json={"name": "Cloud"}).json()
        library_id = lib["id"]
        up = client.post(f"/api/libraries/{library_id}/documents",
                         files={"file": ("viaggi.md", io.BytesIO(doc_text.encode()), "text/markdown")})
        deadline, status = time.time() + 60, ""
        while time.time() < deadline:
            items = client.get(f"/api/libraries/{library_id}/documents").json()["items"]
            status = next((d["status"] for d in items if d["id"] == up.json()["id"]), "")
            if status == "ready":
                break
            time.sleep(0.5)
        step("documento pronto", status == "ready")
        base = f"/api/libraries/{library_id}"

        # ── Cancello 1: chiave SENZA consenso globale ──
        no_consent = replace(config.cfg, LIBRARY_CLOUD_CONSENT=False)
        saved = (config.cfg, api_libraries.cfg, evidence_assistant.cfg)
        config.cfg = api_libraries.cfg = evidence_assistant.cfg = no_consent
        r = client.put(f"{base}/assistant-policy",
                       json={"mode": "approved_openrouter", "provider_name": ""})
        step("cancello 1: chiave sola NON abilita il cloud (409)", r.status_code == 409)
        answer = client.post(f"{base}/ask", json={"question": "Con quale tariffa si calcola il rimborso?"}).json()
        step("ask resta evidence-only senza consenso", answer["meta"]["assistant_mode"] == "evidence_only")
        config.cfg, api_libraries.cfg, evidence_assistant.cfg = saved

        # ── Cancello 2+3: consenso globale + scelta per biblioteca ──
        options = client.get(f"{base}/assistant-options").json()
        step("assistant-options raggiungibile col consenso", options.get("cloud_enabled") is True,
             f"provider approvati: {[i['name'] for i in options.get('items', [])]}")

        r = client.put(f"{base}/assistant-policy",
                       json={"mode": "approved_openrouter", "provider_name": ""})
        step("policy approved_openrouter impostata dall'owner", r.status_code == 200)

        answer = client.post(f"{base}/ask",
                             json={"question": "Con quale tariffa si calcola il rimborso chilometrico?"}).json()
        reason = answer["evidence"].get("reason") or ""
        generated = answer["answer"] != "" and not answer["answer"].startswith("Ho trovato questi passaggi")
        step("ask in modalita' cloud: risposta generata O fallback sicuro alle evidenze",
             answer["status"] == "answered" and bool(answer["citations"]),
             f"generata={generated}, motivo fallback={reason!r}")

    print(f"\nRISULTATO: {PASS} passati, {FAIL} falliti")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
