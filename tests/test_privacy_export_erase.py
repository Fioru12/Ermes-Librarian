"""Diritti dell'interessato: accesso (art. 15) e cancellazione (art. 17).

Dichiarati mancanti nel threat model e nella tesina fino all'11 settembre
2026. I test fissano la regola su cosa si cancella, cosa passa
all'amministratore che esegue, e cosa si conserva dichiarandolo.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.libraries
import api.privacy
import config
from api import app
from core.governance import create_or_update_user

PASSWORD_CAPO = "StrongPassword!123"
PASSWORD_MARIO = "PasswordMario!123"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir),
        DATABASE_URL="",
        ADMIN_USERNAME="capo",
        ADMIN_PASSWORD=PASSWORD_CAPO,
        API_KEY="",
        EVIDENCE_VERIFIER_ENABLED=False,
        CONVERSATION_MEMORY_ENABLED=False,
        LIBRARY_SEMANTIC_SEARCH_ENABLED=False,
        HYDE_ENABLED=False,
    )
    for percorso in ("config.cfg", "api.auth.cfg", "api.libraries.cfg", "api.privacy.cfg", "core.analytics.cfg"):
        monkeypatch.setattr(percorso, test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()
    return test_cfg


def _accedi(username: str, password: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return client


@pytest.fixture
def mario(istanza):
    """Un collega con un'impronta completa: account, biblioteca propria,
    appartenenza a una biblioteca altrui, una domanda registrata."""
    capo = _accedi("capo", PASSWORD_CAPO)
    create_or_update_user(istanza.USERS_FILE, "mario", "editor", PASSWORD_MARIO)
    condivisa = capo.post("/api/libraries", json={"name": "Condivisa", "visibility": "shared"}).json()["id"]
    capo.put(f"/api/libraries/{condivisa}/members", json={"username": "mario", "role": "viewer"})
    mario = _accedi("mario", PASSWORD_MARIO)
    propria = mario.post("/api/libraries", json={"name": "Di Mario", "visibility": "private"}).json()["id"]
    mario.post(
        f"/api/libraries/{propria}/documents",
        files={"file": ("nota.txt", b"La pausa pranzo dura 60 minuti.", "text/plain")},
    )
    mario.post(f"/api/libraries/{propria}/ask", json={"question": "Quanto dura la pausa pranzo di Mario Rossi?"})
    return {"capo": capo, "mario": mario, "condivisa": condivisa, "propria": propria}


# ============================================================
# Accesso
# ============================================================


def test_a_user_can_export_their_own_data(istanza, mario):
    esito = mario["mario"].get("/api/privacy/users/mario/export")

    assert esito.status_code == 200, esito.text
    corpo = esito.json()
    assert corpo["account"]["username"] == "mario"
    assert [lib["id"] for lib in corpo["libraries"]["owned_libraries"]] == [mario["propria"]]
    assert [m["library_id"] for m in corpo["libraries"]["memberships"]] == [mario["condivisa"]]
    assert any("pausa pranzo" in e.get("query", "") for e in corpo["analytics_events"])
    assert any(v["action"] == "library_answer" for v in corpo["audit_entries"])


def test_a_user_cannot_export_someone_elses_data(istanza, mario):
    esito = mario["mario"].get("/api/privacy/users/capo/export")

    assert esito.status_code == 404, "deve rispondere come se l'account non esistesse"


def test_an_admin_can_export_anyone(istanza, mario):
    assert mario["capo"].get("/api/privacy/users/mario/export").status_code == 200


# ============================================================
# Cancellazione
# ============================================================


def test_erasure_removes_the_person_and_keeps_the_organisation_s_documents(istanza, mario):
    capo = mario["capo"]

    esito = capo.delete("/api/privacy/users/mario")

    assert esito.status_code == 200, esito.text
    rapporto = esito.json()
    assert rapporto["erased"]["account"] is True
    assert rapporto["erased"]["memberships_removed"] == 1
    assert rapporto["erased"]["libraries_reassigned"] == 1
    assert rapporto["erased"]["analytics_events"] >= 1
    assert rapporto["reassigned_to"] == "capo"

    # La persona non entra piu'.
    anonimo = TestClient(app)
    assert anonimo.post("/api/auth/login", json={"username": "mario", "password": PASSWORD_MARIO}).status_code == 401
    # La sua biblioteca esiste ancora, e ora e' del capo: i documenti sono
    # dell'organizzazione, non della persona.
    biblioteca = capo.get(f"/api/libraries/{mario['propria']}").json()
    assert biblioteca["owner_id"] == "capo"
    assert biblioteca["document_count"] == 1
    # Le sue domande non sono piu' nell'archivio analitico.
    eventi = [json.loads(r) for r in Path(istanza.ANALYTICS_FILE).read_text(encoding="utf-8").splitlines() if r.strip()]
    assert all(e.get("actor") != "mario" for e in eventi)


def test_erasure_ends_the_active_sessions(istanza, mario):
    mario["capo"].delete("/api/privacy/users/mario")

    assert mario["mario"].get("/api/libraries").status_code == 401


def test_audit_entries_are_retained_and_the_report_says_so(istanza, mario):
    from core.governance import audit_entries_for

    prima = len(audit_entries_for(istanza.AUDIT_FILE, "mario"))
    assert prima >= 1

    rapporto = mario["capo"].delete("/api/privacy/users/mario").json()

    assert rapporto["retained"]["audit_entries"] == prima
    assert "17(3)(b)" in rapporto["retained"]["reason"]
    assert len(audit_entries_for(istanza.AUDIT_FILE, "mario")) == prima
    # E la cancellazione stessa e' nel log, a nome di chi l'ha eseguita.
    assert any(v["action"] == "privacy_erase" for v in audit_entries_for(istanza.AUDIT_FILE, "capo"))


def test_an_admin_cannot_erase_themselves_or_the_configured_admin(istanza, mario):
    capo = mario["capo"]

    assert capo.delete("/api/privacy/users/capo").status_code == 409


def test_erasing_a_nonexistent_account_is_a_404(istanza, mario):
    assert mario["capo"].delete("/api/privacy/users/nessuno").status_code == 404


def test_erasure_is_admin_only(istanza, mario):
    assert mario["mario"].delete("/api/privacy/users/capo").status_code == 403
