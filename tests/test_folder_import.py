"""Importazione documenti da cartelle registrate (core/folder_importer.py).

Regole verificate:
- la scansione importa i file supportati e crea i job di indicizzazione;
- i duplicati (stesso contenuto, anche con nome diverso) vengono saltati;
- le estensioni non supportate e le cartelle irraggiungibili non fanno crashare;
- solo il PROPRIETARIO della biblioteca (o un admin globale) puo' registrare o
  rimuovere una sorgente — non un editor collaboratore qualsiasi;
- nessuna sorgente puo' puntare dentro la directory dell'applicazione, per
  nessun attore, nemmeno il proprietario: e' il confine che chiude il bypass
  descritto sotto.

Trovato in revisione, non prima: senza il gate sul proprietario, qualunque
editor aggiunto a una biblioteca condivisa poteva registrare come "sorgente
cartella" della propria biblioteca lo storage di UN'ALTRA biblioteca a cui
non aveva accesso (storage/libraries/<altro-id>/) e farsela importare per
intero — bypass completo della garanzia "il recupero non attraversa mai il
confine fra biblioteche", verificata altrove (test_library_store.py,
scripts/run_demo_validation.py, l'E2E su browser) ma mai su questo percorso.
Riprodotto empiricamente prima di correggere: vedi
test_editor_member_cannot_use_another_librarys_storage_as_a_source qui sotto.
"""

from fastapi.testclient import TestClient

from api import app
from api.auth import _SESSIONS
from config import cfg


def api_client_factory(tmp_path, monkeypatch):
    # La directory dell'app finta e il materiale "esterno" dei test devono
    # essere fratelli, mai l'uno dentro l'altro: altrimenti il confine che
    # questo file verifica non verrebbe mai davvero esercitato.
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = cfg.replace(
        BASE_DIR=str(app_dir), ADMIN_USERNAME="owner", ADMIN_PASSWORD="StrongPassword!123", API_KEY=""
    )
    monkeypatch.setattr("config.cfg", test_cfg)
    monkeypatch.setattr("api.auth.cfg", test_cfg)
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    _SESSIONS.clear()
    return TestClient(app), test_cfg


def _setup_library(tmp_path, monkeypatch, *, visibility="private"):
    client, test_cfg = api_client_factory(tmp_path, monkeypatch)
    import api.libraries

    monkeypatch.setattr(api.libraries, "_store", None)
    store = api.libraries.get_library_store()
    library = store.create_library("Archivio", "", visibility, owner_id="owner")
    assert (
        client.post("/api/auth/login", json={"username": "owner", "password": "StrongPassword!123"}).status_code == 200
    )
    return client, store, library, test_cfg


def _login_as(test_cfg, username, role, password):
    from core.governance import create_or_update_user

    create_or_update_user(test_cfg.USERS_FILE, username, role, password)
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return client


def test_scan_imports_supported_files_and_deduplicates_by_content(tmp_path, monkeypatch):
    client, store, library, _ = _setup_library(tmp_path, monkeypatch)
    folder = tmp_path / "esterna"
    folder.mkdir()
    (folder / "contratto.txt").write_text("Il contratto scade a dicembre.", encoding="utf-8")
    (folder / "stesso_contenuto.txt").write_text("Il contratto scade a dicembre.", encoding="utf-8")  # duplicato
    (folder / "archivio.zip").write_bytes(b"PK\x03\x04 not a document")  # estensione non supportata

    # Un vero xlsx (stesso skeleton deterministico del parser) deve essere
    # importato e arrivare a "ready" come i .txt: la whitelist del connettore
    # cartella è allineata a quella degli upload.
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    xlsx_buffer = BytesIO()
    with ZipFile(xlsx_buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Scadenza</t></si></sst>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Scadenze" sheetId="1" /></sheets></workbook>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>',
        )
    (folder / "foglio.xlsx").write_bytes(xlsx_buffer.getvalue())

    added = client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(folder)})
    assert added.status_code == 201
    source_id = added.json()["id"]

    scan = client.post(f"/api/libraries/{library['id']}/sources/{source_id}/scan")
    assert scan.status_code == 200
    body = scan.json()
    assert sorted(item["filename"] for item in body["imported"]) == ["contratto.txt", "foglio.xlsx"]
    assert body["skipped_duplicates"] == ["stesso_contenuto.txt"]
    assert body["skipped_unsupported"] == ["archivio.zip"]

    # Il documento importato è realmente nella biblioteca, e la sua
    # ingestione e' arrivata a "ready", non solo la riga creata in stato
    # "queued". Trovato in revisione (non da questo test, che non lo
    # controllava): add_document registra solo metadati, non scrive mai il
    # contenuto su disco — scan_import_source riceveva storage_dir ma non lo
    # usava, quindi ogni file importato falliva l'ingestione subito dopo con
    # "Originale non disponibile", pur risultando "imported" nella risposta
    # della scansione qui sopra.
    documents = store.list_documents(library["id"])
    assert sorted(d["filename"] for d in documents) == ["contratto.txt", "foglio.xlsx"]
    assert all(d["status"] == "ready" for d in documents), [d.get("status") for d in documents]
    from core.library_store import resolve_storage_path

    for document in documents:
        stored_path = resolve_storage_path(document["storage_path"], tmp_path / "app" / "storage" / "libraries")
        assert stored_path.is_file()

    # Seconda scansione: nessun nuovo import; tutti i file sono già noti.
    rescan = client.post(f"/api/libraries/{library['id']}/sources/{source_id}/scan").json()
    assert rescan["imported"] == []
    assert sorted(rescan["skipped_duplicates"]) == ["contratto.txt", "foglio.xlsx", "stesso_contenuto.txt"]


def test_source_registration_requires_ownership_not_just_a_role(tmp_path, monkeypatch):
    client, store, library, test_cfg = _setup_library(tmp_path, monkeypatch, visibility="shared")
    folder = tmp_path / "esterna"
    folder.mkdir()

    # Viewer MEMBRO: rifiutato per ruolo insufficiente, non per assenza di
    # relazione con la biblioteca (quel caso è 404, testato altrove).
    viewer_client = _login_as(test_cfg, "carol", "viewer", "StrongViewer!123")
    client.put(f"/api/libraries/{library['id']}/members", json={"username": "carol", "role": "viewer"})
    denied = viewer_client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(folder)})
    assert denied.status_code == 403

    # Editor MEMBRO ma non proprietario: e' esattamente il caso che mancava.
    # Un editor puo' caricare documenti nella biblioteca condivisa, ma
    # registrare una sorgente concede al server accesso in lettura a un
    # percorso del filesystem scelto dall'attore — un privilegio piu' ampio,
    # riservato al proprietario.
    editor_client = _login_as(test_cfg, "bob", "editor", "StrongEditor!123")
    client.put(f"/api/libraries/{library['id']}/members", json={"username": "bob", "role": "editor"})
    denied_editor = editor_client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(folder)})
    assert denied_editor.status_code == 403

    # Rimozione di una sorgente: stessa soglia, stesso motivo.
    added = client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(folder)})
    source_id = added.json()["id"]
    denied_remove = editor_client.delete(f"/api/libraries/{library['id']}/sources/{source_id}")
    assert denied_remove.status_code == 403

    # Percorso inesistente: la registrazione dal proprietario è consentita,
    # ma la scansione lo segnala senza crashare.
    missing = client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(tmp_path / "inesistente")})
    assert missing.status_code == 201
    scan = client.post(f"/api/libraries/{library['id']}/sources/{missing.json()['id']}/scan")
    assert scan.status_code == 200
    assert "non raggiungibile" in scan.json()["failed"][0]["error"]

    # Duplicato della stessa sorgente -> 409.
    again = client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(tmp_path / "inesistente")})
    assert again.status_code == 409


def test_listing_sources_is_denied_to_a_non_member_of_a_private_library(tmp_path, monkeypatch):
    """Trovato debuggando il progetto: list_import_sources chiamava
    self.get_library(library_id) senza l'attore, quindi _can_access
    restituiva sempre True (il "system bypass" per actor=None) -- un
    utente autenticato ma senza alcuna relazione con la biblioteca privata
    poteva leggere i veri percorsi filesystem registrati come sorgenti,
    esattamente il tipo di dato che questa registrazione dovrebbe
    proteggere. /documents applicava gia' correttamente il 404; /sources
    no. Riprodotto con un percorso plausibile prima di correggere."""
    client, store, library, test_cfg = _setup_library(tmp_path, monkeypatch, visibility="private")
    client.post(f"/api/libraries/{library['id']}/sources", json={"path": str(tmp_path / "server" / "hr")})

    stranger_client = _login_as(test_cfg, "mallory", "viewer", "StrongViewer!123")
    denied = stranger_client.get(f"/api/libraries/{library['id']}/sources")
    assert denied.status_code == 404

    assert client.get(f"/api/libraries/{library['id']}/sources").status_code == 200


def test_editor_member_cannot_use_another_librarys_storage_as_a_source(tmp_path, monkeypatch):
    """Riproduce e chiude il bypass descritto nel docstring del modulo."""
    client, store, private_library, test_cfg = _setup_library(tmp_path, monkeypatch, visibility="private")
    confidential = client.post(
        f"/api/libraries/{private_library['id']}/documents",
        files={"file": ("stipendi.txt", b"Stipendio CEO: 950000 EUR - CONFIDENZIALE", "text/plain")},
    )
    assert confidential.status_code == 201

    mallory_client = _login_as(test_cfg, "mallory", "editor", "StrongEditor!123")
    own_lib = mallory_client.post("/api/libraries", json={"name": "Di Mallory", "visibility": "private"})
    mallory_lib_id = own_lib.json()["id"]

    # Mallory non e' membro della biblioteca privata: l'API normale la nega.
    assert mallory_client.get(f"/api/libraries/{private_library['id']}/documents").status_code == 404

    # Tentativo: registrare lo storage dell'altra biblioteca come sorgente
    # della propria. Deve fallire per il confine di percorso, prima ancora
    # di arrivare al controllo sul ruolo — vale per chiunque, non solo per
    # chi non e' proprietario.
    target = str(tmp_path / "app" / "storage" / "libraries" / private_library["id"])
    r = mallory_client.post(f"/api/libraries/{mallory_lib_id}/sources", json={"path": target})
    assert r.status_code == 422

    # E anche una sorgente che punta genericamente dentro l'app viene rifiutata.
    r = mallory_client.post(f"/api/libraries/{mallory_lib_id}/sources", json={"path": str(tmp_path / "app")})
    assert r.status_code == 422

    # Nessun documento e' trapelato nella biblioteca di Mallory.
    assert store.list_documents(mallory_lib_id) == []
