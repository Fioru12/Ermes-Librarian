"""Il gateway di automazione applica le guardie del caricamento normale.

`POST /api/integrations/automation/ingest` e' la terza via d'immissione
documenti, dopo il caricamento dal browser e il connettore, ed era l'unica che
non applicava nessuna delle guardie delle altre due.

Dimostrato prima della correzione: un utente con ruolo `viewer`, rifiutato con
403 dal caricamento normale, immetteva documenti da qui ricevendo 200. Conta
piu' di una semplice escalation di permessi: i documenti immessi diventano
l'evidenza che il bibliotecario cita agli altri utenti come autorevole, quindi
chi ha la sola lettura poteva mettere in bocca al sistema qualunque contenuto.

Un nome file con estensione non ammessa produceva inoltre un 500 — un errore
del server invece di un rifiuto — perche' l'eccezione del parser sfuggiva.
"""

import base64

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.libraries
import api.webhook_gateway
import config
from api import app
from core.governance import create_or_update_user

PASSWORD_CAPO = "StrongPassword!123"
PASSWORD_OSPITE = "PasswordOspite!123"
PASSWORD_COLLEGA = "PasswordCollega!123"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir), DATABASE_URL="", ADMIN_USERNAME="capo", ADMIN_PASSWORD=PASSWORD_CAPO, API_KEY=""
    )
    for modulo in (config, api.auth, api.libraries, api.webhook_gateway):
        # Solo dove l'attributo esiste: cosi' il file resta eseguibile anche
        # contro una versione del gateway che non importa cfg, e il confronto
        # prima/dopo produce fallimenti leggibili invece di errori di
        # raccolta.
        if hasattr(modulo, "cfg"):
            monkeypatch.setattr(modulo, "cfg", test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()
    return test_cfg


def _accedi(username: str, password: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return client


@pytest.fixture
def biblioteca(istanza):
    capo = _accedi("capo", PASSWORD_CAPO)
    library_id = capo.post("/api/libraries", json={"name": "Condivisa", "visibility": "shared"}).json()["id"]
    return capo, library_id


def _immetti(client: TestClient, library_id: str, filename: str, contenuto: bytes, base64_encoded: bool = True):
    return client.post(
        "/api/integrations/automation/ingest",
        json={
            "library_id": library_id,
            "filename": filename,
            "content": base64.b64encode(contenuto).decode() if base64_encoded else contenuto.decode(),
            "is_base64": base64_encoded,
        },
    )


# ============================================================
# Il buco che questi test chiudono
# ============================================================


def test_a_viewer_is_refused_here_exactly_as_on_the_normal_upload(istanza, biblioteca):
    capo, library_id = biblioteca
    create_or_update_user(istanza.USERS_FILE, "ospite", "viewer", PASSWORD_OSPITE)
    capo.put(f"/api/libraries/{library_id}/members", json={"username": "ospite", "role": "viewer"})
    ospite = _accedi("ospite", PASSWORD_OSPITE)

    dal_browser = ospite.post(
        f"/api/libraries/{library_id}/documents", files={"file": ("nota.txt", b"contenuto", "text/plain")}
    )
    dal_webhook = _immetti(ospite, library_id, "iniettato.txt", b"Inserito da un utente in sola lettura.")

    assert dal_browser.status_code == 403
    assert dal_webhook.status_code == 403, "un utente in sola lettura immette documenti dal gateway"


def test_an_unsupported_extension_is_refused_not_a_server_error(istanza, biblioteca):
    """Prima restituiva 500: l'eccezione del parser sfuggiva come errore del
    server invece di essere un rifiuto della richiesta."""
    capo, library_id = biblioteca

    esito = _immetti(capo, library_id, "evasione.exe", b"MZ eseguibile")

    assert esito.status_code == 400, f"atteso un rifiuto, ricevuto {esito.status_code}"


def test_a_traversal_filename_is_refused(istanza, biblioteca):
    capo, library_id = biblioteca

    esito = _immetti(capo, library_id, "../../../../security/users.json", b"{}")

    assert esito.status_code == 400


def test_content_that_does_not_match_the_declared_type_is_refused(istanza, biblioteca):
    """Stessa guardia del caricamento dal browser: i byte iniziali devono
    corrispondere all'estensione dichiarata."""
    capo, library_id = biblioteca

    esito = _immetti(capo, library_id, "finto.pdf", b"questo non e' un PDF")

    assert esito.status_code == 400


def test_an_oversized_payload_is_refused(istanza, biblioteca, monkeypatch):
    capo, library_id = biblioteca
    monkeypatch.setattr(api.webhook_gateway, "cfg", istanza.replace(ADMIN_MAX_UPLOAD_MB=1), raising=False)

    esito = _immetti(capo, library_id, "grande.txt", b"x" * (2 * 1024 * 1024))

    assert esito.status_code == 413


# ============================================================
# La funzionalita' legittima deve continuare a funzionare
# ============================================================


def test_an_editor_can_still_ingest_through_the_gateway(istanza, biblioteca):
    """E' il motivo per cui il gateway esiste: n8n, Zapier e simili."""
    capo, library_id = biblioteca

    esito = _immetti(capo, library_id, "procedura.txt", b"Le ferie si richiedono con quindici giorni di anticipo.")

    assert esito.status_code == 200, esito.text
    corpo = esito.json()
    assert corpo["ok"] is True
    assert corpo["filename"] == "procedura.txt"


def test_the_ingested_document_is_findable_afterwards(istanza, biblioteca):
    capo, library_id = biblioteca
    _immetti(capo, library_id, "ferie.txt", b"Le ferie si richiedono con quindici giorni di anticipo.")

    ricerca = capo.get(f"/api/libraries/{library_id}/search", params={"q": "ferie anticipo"})

    assert ricerca.status_code == 200
    assert "ferie" in ricerca.text.lower()
