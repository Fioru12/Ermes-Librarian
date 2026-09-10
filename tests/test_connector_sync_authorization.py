"""Chi puo' far leggere al server una cartella, e quali cartelle.

`POST /api/connectors/sync` immette documenti in una biblioteca leggendoli dal
filesystem del server — esattamente come le sorgenti cartella registrate in
`api/libraries.py`. Quel percorso gemello ha due guardie, scritte con cura e
commentate: proprietario o amministratore, e rifiuto dei percorsi interni
all'applicazione. Questa rotta le ignorava entrambe.

Dimostrato prima della correzione: un utente con ruolo globale `editor`, NON
proprietario della biblioteca, ha puntato il connettore a una cartella
arbitraria del server, importato un file di buste paga e ne ha letto il
contenuto tramite la ricerca — retribuzione, codice fiscale e IBAN compresi.

La guardia sui percorsi interni non e' un dettaglio: il suo commento
originale spiega che serve a impedire di puntare una sorgente dentro
`storage/libraries/<altra-biblioteca>`, cioe' l'aggiramento completo della
garanzia centrale del prodotto, raggiungibile senza passare dal percorso di
lettura che i test di isolamento coprono.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.connectors
import api.libraries
import config
from api import app
from core.governance import create_or_update_user

PASSWORD_PROPRIETARIO = "StrongPassword!123"
PASSWORD_COLLEGA = "AltraPassword!123"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir),
        DATABASE_URL="",
        ADMIN_USERNAME="capo",
        ADMIN_PASSWORD=PASSWORD_PROPRIETARIO,
        API_KEY="",
    )
    for modulo in (config, api.auth, api.libraries, api.connectors):
        monkeypatch.setattr(modulo, "cfg", test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()
    return test_cfg


def _accedi(username: str, password: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return client


def _cartella_riservata(tmp_path: Path) -> Path:
    cartella = tmp_path / "CartellaRiservata"
    cartella.mkdir()
    (cartella / "buste_paga.txt").write_text(
        "RISERVATO. Retribuzione annua lorda: 41.500 euro. Codice fiscale RSSMRA85M01H501Z.",
        encoding="utf-8",
    )
    return cartella


def _sincronizza(client: TestClient, library_id: str, cartella: Path):
    return client.post(
        "/api/connectors/sync",
        json={
            "type": "local_folder",
            "target_library_id": library_id,
            "config": {"folder_path": str(cartella), "recursive": True},
        },
    )


# ============================================================
# Il buco che questi test chiudono
# ============================================================


def test_an_editor_who_does_not_own_the_library_cannot_make_the_server_read_a_folder(istanza, tmp_path):
    proprietario = _accedi("capo", PASSWORD_PROPRIETARIO)
    library_id = proprietario.post("/api/libraries", json={"name": "Condivisa", "visibility": "shared"}).json()["id"]
    create_or_update_user(istanza.USERS_FILE, "dipendente", "editor", PASSWORD_COLLEGA)
    collega = _accedi("dipendente", PASSWORD_COLLEGA)
    riservata = _cartella_riservata(tmp_path)

    esito = _sincronizza(collega, library_id, riservata)

    assert esito.status_code in (403, 404), f"importazione consentita a un non proprietario: {esito.status_code}"
    ricerca = proprietario.get(f"/api/libraries/{library_id}/search", params={"q": "retribuzione"})
    assert "41.500" not in ricerca.text, "il contenuto riservato e' finito nella biblioteca"


def test_a_path_inside_the_application_is_refused_even_to_the_owner(istanza):
    """Vale anche per il proprietario: nessuna sorgente legittima punta dentro
    i dati che l'applicazione gestisce."""
    proprietario = _accedi("capo", PASSWORD_PROPRIETARIO)
    library_id = proprietario.post("/api/libraries", json={"name": "Archivio", "visibility": "private"}).json()["id"]

    esito = _sincronizza(proprietario, library_id, Path(istanza.BASE_DIR) / "storage")

    assert esito.status_code == 422
    assert "applicazione" in esito.json()["detail"].lower()


def test_another_librarys_storage_cannot_be_imported(istanza):
    """L'aggiramento dell'isolamento descritto nel commento della guardia:
    importare la cartella di un'altra biblioteca ne renderebbe i documenti
    leggibili attraverso le citazioni della propria."""
    proprietario = _accedi("capo", PASSWORD_PROPRIETARIO)
    altra = proprietario.post("/api/libraries", json={"name": "Riservata", "visibility": "private"}).json()["id"]
    mia = proprietario.post("/api/libraries", json={"name": "Mia", "visibility": "private"}).json()["id"]

    esito = _sincronizza(proprietario, mia, Path(istanza.LIBRARY_STORAGE_DIR) / "libraries" / altra)

    assert esito.status_code == 422


# ============================================================
# La funzionalita' legittima deve continuare a funzionare
# ============================================================


def test_the_owner_can_still_import_an_external_folder(istanza, tmp_path):
    """Chiudere il buco non deve togliere la funzionalita': importare una
    cartella di rete esterna e' esattamente cio' per cui esiste."""
    proprietario = _accedi("capo", PASSWORD_PROPRIETARIO)
    library_id = proprietario.post("/api/libraries", json={"name": "Archivio", "visibility": "private"}).json()["id"]
    esterna = tmp_path / "CartellaDiRete"
    esterna.mkdir()
    (esterna / "procedura.txt").write_text(
        "Le ferie si richiedono con quindici giorni di anticipo al responsabile.", encoding="utf-8"
    )

    esito = _sincronizza(proprietario, library_id, esterna)

    assert esito.status_code == 200, esito.text
    assert esito.json()["imported_count"] == 1
