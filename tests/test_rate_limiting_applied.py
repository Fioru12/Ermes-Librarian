"""Il limitatore protegge davvero delle rotte (api/auth.py::rate_limited).

`core/rate_limiter.py` esisteva completo, con dieci test che passavano, e non
era applicato a nessuna rotta: quei test verificano la classe, quindi restavano
verdi mentre il server non era protetto da niente. Questo file verifica il
server.

`tests/test_rate_limiter.py` continua a coprire la logica di conteggio; qui si
controlla solo che sia collegata, e a cosa.
"""

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.libraries
import config
from api import app
from core.rate_limiter import get_rate_limiter

PASSWORD = "StrongPassword!123"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir), DATABASE_URL="", ADMIN_USERNAME="capo", ADMIN_PASSWORD=PASSWORD, API_KEY=""
    )
    monkeypatch.setattr(config, "cfg", test_cfg)
    monkeypatch.setattr(api.auth, "cfg", test_cfg)
    monkeypatch.setattr(api.libraries, "cfg", test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()
    get_rate_limiter().reset()
    return test_cfg


def _accedi(username="capo", password=PASSWORD):
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return client


def _biblioteca(client):
    risposta = client.post("/api/libraries", json={"name": "Archivio", "visibility": "private"})
    assert risposta.status_code == 201, risposta.text
    return risposta.json()["id"]


def _abbassa_il_limite(monkeypatch, massimo):
    limiter = get_rate_limiter()
    monkeypatch.setattr(limiter.config, "max_requests_per_minute", massimo)
    limiter.reset()


# ============================================================
# Le rotte costose sono protette
# ============================================================


def test_asking_repeatedly_eventually_gets_refused(istanza, monkeypatch):
    """La rotta piu' costosa del prodotto: recupero piu' generazione."""
    client = _accedi()
    library_id = _biblioteca(client)
    _abbassa_il_limite(monkeypatch, 3)

    esiti = [
        client.post(f"/api/libraries/{library_id}/ask", json={"question": "quali sono le ferie?"}).status_code
        for _ in range(5)
    ]

    assert 429 in esiti
    assert esiti.count(429) == 2


def test_searching_repeatedly_eventually_gets_refused(istanza, monkeypatch):
    client = _accedi()
    library_id = _biblioteca(client)
    _abbassa_il_limite(monkeypatch, 2)

    esiti = [client.get(f"/api/libraries/{library_id}/search?q=ferie").status_code for _ in range(4)]

    assert esiti[-1] == 429


# ============================================================
# Le rotte a costo nullo non lo sono
# ============================================================


def test_health_is_never_rate_limited(istanza, monkeypatch):
    """Una sonda di readiness interroga /health di continuo: limitarla
    significherebbe far dichiarare morta un'istanza sana."""
    client = TestClient(app)
    _abbassa_il_limite(monkeypatch, 1)

    esiti = [client.get("/health").status_code for _ in range(10)]

    assert set(esiti) == {200}


# ============================================================
# Su cosa si conta
# ============================================================


def test_two_users_do_not_share_a_quota(istanza, monkeypatch):
    """Il punto della scelta: contare per solo IP significherebbe che dietro
    il NAT di un'azienda il primo che carica blocca tutti i colleghi."""
    from core.governance import create_or_update_user

    capo = _accedi()
    library_id = _biblioteca(capo)
    capo.put(f"/api/libraries/{library_id}/members", json={"username": "collega", "role": "editor"})
    create_or_update_user(istanza.USERS_FILE, "collega", "editor", "AltraPassword!123")
    collega = _accedi("collega", "AltraPassword!123")

    _abbassa_il_limite(monkeypatch, 2)
    for _ in range(3):
        capo.post(f"/api/libraries/{library_id}/ask", json={"question": "ferie"})

    # Il capo ha esaurito la sua quota; il collega arriva dallo stesso indirizzo.
    esito_collega = collega.post(f"/api/libraries/{library_id}/ask", json={"question": "ferie"})

    assert esito_collega.status_code != 429


def test_the_refusal_explains_itself(istanza, monkeypatch):
    client = _accedi()
    library_id = _biblioteca(client)
    _abbassa_il_limite(monkeypatch, 1)

    client.post(f"/api/libraries/{library_id}/ask", json={"question": "ferie"})
    rifiutata = client.post(f"/api/libraries/{library_id}/ask", json={"question": "ferie"})

    assert rifiutata.status_code == 429
    assert "rate limit" in rifiutata.json()["detail"].lower()


def test_uploading_repeatedly_eventually_gets_refused(istanza, monkeypatch):
    """Il caricamento fa parsing e indicizzazione: costa piu' di una ricerca."""
    client = _accedi()
    library_id = _biblioteca(client)
    _abbassa_il_limite(monkeypatch, 2)

    esiti = []
    for i in range(4):
        esiti.append(
            client.post(
                f"/api/libraries/{library_id}/documents",
                files={
                    "file": (f"nota{i}.txt", b"Le ferie si richiedono con quindici giorni di anticipo.", "text/plain")
                },
            ).status_code
        )

    assert esiti[-1] == 429
