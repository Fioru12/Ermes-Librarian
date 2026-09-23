"""Unit and integration tests for Cross-Library Federated Search & Document Retention Engine."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api import app
from core.library_store import LibraryStore
from core.retention_engine import RetentionEngine


@pytest.fixture
def temp_env(monkeypatch, tmp_path):
    db_file = tmp_path / "test_libraries.db"
    retention_db = tmp_path / "test_retention.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("config.cfg.LIBRARY_DB_PATH", str(db_file))
    monkeypatch.setattr("config.cfg.LIBRARY_STORAGE_DIR", str(storage_dir))
    monkeypatch.setattr("config.cfg.BASE_DIR", str(tmp_path))
    monkeypatch.setattr("config.cfg.API_KEY", "test-secret-key")
    monkeypatch.setattr("config.cfg.AUDIT_FILE", str(tmp_path / "audit.jsonl"))

    store = LibraryStore(str(db_file))
    retention_engine = RetentionEngine(str(retention_db))

    monkeypatch.setattr("api.libraries.get_library_store", lambda: store)
    monkeypatch.setattr("api.retention.get_retention_engine", lambda: retention_engine)

    return {
        "store": store,
        "retention": retention_engine,
        "tmp_path": tmp_path,
        "admin_auth": {"username": "admin", "role": "admin"},
        "viewer_auth": {"username": "viewer", "role": "viewer"},
        "headers": {"Authorization": "Bearer test-secret-key"},
    }


def test_retention_policy_and_legal_hold(temp_env):
    retention = temp_env["retention"]
    lib_id = "lib_compliance_001"

    # Set library retention policy
    policy = retention.set_library_policy(
        library_id=lib_id,
        retention_days=90,
        action="purge",
        actor="admin",
    )
    assert policy.library_id == lib_id
    assert policy.retention_days == 90
    assert policy.action == "purge"

    fetched = retention.get_library_policy(lib_id)
    assert fetched is not None
    assert fetched.retention_days == 90
    assert fetched.action == "purge"

    # Set legal hold on a document
    hold = retention.set_document_legal_hold(
        library_id=lib_id,
        document_id="doc_audit_123",
        legal_hold=True,
        reason="Indagine fiscale 2026",
        actor="compliance_officer",
    )
    assert hold["legal_hold"] is True
    assert hold["legal_hold_reason"] == "Indagine fiscale 2026"

    status = retention.get_document_retention_status(lib_id, "doc_audit_123")
    assert status["legal_hold"] is True
    assert status["legal_hold_reason"] == "Indagine fiscale 2026"


def test_retention_lifecycle_enforcement_with_legal_hold(temp_env):
    store = temp_env["store"]
    retention = temp_env["retention"]

    # Create library and documents
    lib = store.create_library("HR Department", owner_id="admin")
    lib_id = lib["id"]

    # 1. Expired doc without legal hold (should be purged)
    doc_expired = store.add_document(
        library_id=lib_id,
        filename="old_resumes_2020.pdf",
        media_type="application/pdf",
        content=b"vecchio curriculum",
        storage_path="old_resumes_2020.pdf",
        extracted_text="vecchio curriculum",
        chunks=[("vecchio curriculum", "Pag 1")],
    )

    # 2. Expired doc WITH legal hold (must NOT be purged)
    doc_protected = store.add_document(
        library_id=lib_id,
        filename="dispute_contract.pdf",
        media_type="application/pdf",
        content=b"contratto con contenzioso in corso",
        storage_path="dispute_contract.pdf",
        extracted_text="contratto con contenzioso in corso",
        chunks=[("contratto con contenzioso in corso", "Art 1")],
    )

    # Manually age the documents in DB to simulate 100 days ago
    old_date = (datetime.now(UTC) - timedelta(days=100)).isoformat()
    with store._connection() as conn:
        conn.execute("UPDATE documents SET created_at = ? WHERE id IN (?, ?)", (old_date, doc_expired["id"], doc_protected["id"]))
        conn.commit()

    # Set policy: 30 days retention with purge action
    retention.set_library_policy(lib_id, retention_days=30, action="purge", actor="admin")

    # Set legal hold on protected doc
    retention.set_document_legal_hold(
        library_id=lib_id,
        document_id=doc_protected["id"],
        legal_hold=True,
        reason="Litigation Hold Legal Dept",
        actor="legal_counsel",
    )

    # 1. Run dry-run enforcement
    dry_report = retention.evaluate_retention(library_id=lib_id, dry_run=True, store=store)
    assert dry_report["dry_run"] is True
    assert len(dry_report["purged"]) == 1
    assert dry_report["purged"][0]["document_id"] == doc_expired["id"]
    assert len(dry_report["legal_hold_protected"]) == 1
    assert dry_report["legal_hold_protected"][0]["document_id"] == doc_protected["id"]

    # Verify doc was not deleted in dry run
    docs_after_dry = store.list_documents(lib_id)
    assert len(docs_after_dry) == 2

    # 2. Run actual enforcement
    live_report = retention.evaluate_retention(library_id=lib_id, dry_run=False, store=store)
    assert live_report["dry_run"] is False
    assert len(live_report["purged"]) == 1
    assert len(live_report["legal_hold_protected"]) == 1

    # Verify doc_expired is purged and doc_protected is preserved
    docs_after_live = store.list_documents(lib_id)
    doc_ids_remaining = [d["id"] for d in docs_after_live]
    assert doc_expired["id"] not in doc_ids_remaining
    assert doc_protected["id"] in doc_ids_remaining


def test_cross_library_federated_search(temp_env):
    store = temp_env["store"]
    actor = temp_env["admin_auth"]

    # Create 3 department libraries
    lib_hr = store.create_library("HR Library", owner_id="admin")
    lib_legal = store.create_library("Legal Library", owner_id="admin")
    lib_tech = store.create_library("Tech Library", owner_id="admin")

    # Ingest documents in each
    store.add_document(
        library_id=lib_hr["id"],
        filename="policy_ferie.txt",
        media_type="text/plain",
        content=b"Tutti i dipendenti hanno diritto a 26 giorni di ferie retribuite all'anno.",
        storage_path="policy_ferie.txt",
        extracted_text="Tutti i dipendenti hanno diritto a 26 giorni di ferie retribuite all'anno.",
        chunks=[("Tutti i dipendenti hanno diritto a 26 giorni di ferie retribuite all'anno.", "Par 1")],
    )

    store.add_document(
        library_id=lib_legal["id"],
        filename="clausola_ferie_contratto.txt",
        media_type="text/plain",
        content=b"La gestione delle ferie e dei permessi e regolata dal CCNL Commercio.",
        storage_path="clausola_ferie_contratto.txt",
        extracted_text="La gestione delle ferie e dei permessi e regolata dal CCNL Commercio.",
        chunks=[("La gestione delle ferie e dei permessi e regolata dal CCNL Commercio.", "Art 5")],
    )

    store.add_document(
        library_id=lib_tech["id"],
        filename="server_setup.txt",
        media_type="text/plain",
        content=b"Deploy del cluster Kubernetes con configurazione ingress TLS.",
        storage_path="server_setup.txt",
        extracted_text="Deploy del cluster Kubernetes con configurazione ingress TLS.",
        chunks=[("Deploy del cluster Kubernetes con configurazione ingress TLS.", "Sec 1")],
    )

    # Federated search across all libraries
    citations, profile = store.search_federated(
        query="ferie dipendenti",
        library_ids=None,
        limit=5,
        actor=actor,
    )

    assert profile["mode"] == "federated"
    assert profile["libraries_searched"] >= 3
    assert len(citations) >= 2

    # Check provenance tags
    library_names = [c["library_name"] for c in citations]
    assert "HR Library" in library_names
    assert "Legal Library" in library_names

    # Check targeted federated search (only HR and Tech)
    targeted_citations, targeted_profile = store.search_federated(
        query="ferie",
        library_ids=[lib_hr["id"], lib_tech["id"]],
        limit=5,
        actor=actor,
    )
    assert targeted_profile["libraries_searched"] == 2
    for c in targeted_citations:
        assert c["library_id"] in [lib_hr["id"], lib_tech["id"]]


def test_federated_search_never_crosses_into_a_library_the_caller_cannot_see(temp_env):
    """The only test above searches as admin, who can see everything — it never
    exercises the isolation boundary the feature exists to respect. A viewer with
    no membership in the private library must never see it in federated results,
    whether the search is unscoped or explicitly names that library's id."""
    store = temp_env["store"]
    admin = temp_env["admin_auth"]
    outsider = temp_env["viewer_auth"]

    lib_secret = store.create_library("Secret HR Salaries", "desc", "private", owner_id="admin")
    lib_shared = store.create_library("Public Handbook", "desc", "shared", owner_id="admin")

    store.add_document(
        library_id=lib_secret["id"],
        filename="salaries.txt",
        media_type="text/plain",
        content=b"Il CEO guadagna 500000 euro all'anno.",
        storage_path="salaries.txt",
        extracted_text="Il CEO guadagna 500000 euro all'anno.",
        chunks=[("Il CEO guadagna 500000 euro all'anno.", "Par 1")],
    )
    store.add_document(
        library_id=lib_shared["id"],
        filename="handbook.txt",
        media_type="text/plain",
        content=b"L'azienda offre 500000 opportunita' di crescita ai dipendenti.",
        storage_path="handbook.txt",
        extracted_text="L'azienda offre 500000 opportunita' di crescita ai dipendenti.",
        chunks=[("L'azienda offre 500000 opportunita' di crescita ai dipendenti.", "Par 1")],
    )

    # Sanity check: the admin (who can see both) does get the secret library back.
    admin_citations, _ = store.search_federated(query="500000", library_ids=None, limit=10, actor=admin)
    assert lib_secret["id"] in {c["library_id"] for c in admin_citations}

    # Unscoped: the outsider's federated search must silently exclude what they can't see.
    citations, profile = store.search_federated(query="500000", library_ids=None, limit=10, actor=outsider)
    assert lib_secret["id"] not in {c["library_id"] for c in citations}
    assert profile["libraries_searched"] == 1

    # Explicitly named: asking for the secret library by id must not leak it either —
    # it should be silently skipped, the same way get_library() would refuse it directly.
    targeted, targeted_profile = store.search_federated(
        query="500000", library_ids=[lib_secret["id"], lib_shared["id"]], limit=10, actor=outsider
    )
    assert lib_secret["id"] not in {c["library_id"] for c in targeted}
    assert targeted_profile["libraries_searched"] == 1


def test_retention_endpoints_refuse_a_library_the_actor_cannot_access(temp_env):
    """`_require_role("editor")`/`_verify_api_key` only check the account's global
    role — never whether the actor belongs to `library_id`. Neither the route
    functions nor RetentionEngine checked library membership before this fix:
    any global-editor account could set a legal hold on a library it has no
    membership in, and any authenticated account could read another library's
    retention status and legal-hold reason."""
    import pytest as _pytest
    from fastapi import HTTPException

    from api.retention import (
        SetLegalHoldRequest,
        SetRetentionPolicyRequest,
        get_document_status,
        get_policy,
        set_legal_hold,
        set_policy,
    )

    store = temp_env["store"]
    outsider = temp_env["viewer_auth"]
    lib_secret = store.create_library("Secret HR Salaries", "desc", "private", owner_id="admin")

    for call in (
        lambda: get_policy(lib_secret["id"], actor=outsider, store=store),
        lambda: set_policy(
            lib_secret["id"],
            SetRetentionPolicyRequest(retention_days=30, action="archive"),
            actor=outsider,
            store=store,
        ),
        lambda: set_legal_hold(
            SetLegalHoldRequest(library_id=lib_secret["id"], document_id="doc-1", legal_hold=True),
            actor=outsider,
            store=store,
        ),
        lambda: get_document_status(lib_secret["id"], "doc-1", actor=outsider, store=store),
    ):
        with _pytest.raises(HTTPException) as exc_info:
            call()
        assert exc_info.value.status_code == 404


def test_federated_search_and_stream_endpoints(temp_env):
    client = TestClient(app)
    store = temp_env["store"]
    headers = temp_env["headers"]

    lib_a = store.create_library("Marketing", owner_id="admin")
    lib_b = store.create_library("Sales", owner_id="admin")

    store.add_document(
        library_id=lib_a["id"],
        filename="campagna_2026.txt",
        media_type="text/plain",
        content=b"Campagna promozionale Q3 con focus su sconti enterprise del 20%.",
        storage_path="campagna_2026.txt",
        extracted_text="Campagna promozionale Q3 con focus su sconti enterprise del 20%.",
        chunks=[("Campagna promozionale Q3 con focus su sconti enterprise del 20%.", "Intro")],
    )

    store.add_document(
        library_id=lib_b["id"],
        filename="listino_sales_2026.txt",
        media_type="text/plain",
        content=b"Listino prezzi sales per account enterprise.",
        storage_path="listino_sales_2026.txt",
        extracted_text="Listino prezzi sales per account enterprise.",
        chunks=[("Listino prezzi sales per account enterprise.", "Prezzi")],
    )

    # 1. Search Federated API
    search_resp = client.post(
        "/api/libraries/federated/search",
        json={"query": "sconti enterprise", "limit": 5},
        headers=headers,
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert "results" in search_data
    assert len(search_data["results"]) >= 1
    assert search_data["results"][0]["library_name"] == "Marketing"

    # 2. Ask Federated Stream API
    stream_resp = client.post(
        "/api/libraries/federated/ask/stream",
        json={"question": "Quali sono gli sconti previsti per la campagna enterprise?", "top_k": 3},
        headers=headers,
    )
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers["content-type"]
    content = stream_resp.text
    assert "event: citations" in content
    assert "event: done" in content


def test_retention_rest_api(temp_env):
    client = TestClient(app)
    store = temp_env["store"]
    headers = temp_env["headers"]

    lib = store.create_library("Finance", owner_id="admin")
    lib_id = lib["id"]

    # 1. Set retention policy via PUT
    put_resp = client.put(
        f"/api/retention/policies/{lib_id}",
        json={"retention_days": 180, "action": "soft_delete"},
        headers=headers,
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["retention_days"] == 180
    assert put_resp.json()["action"] == "soft_delete"

    # 2. Get retention policy via GET
    get_resp = client.get(
        f"/api/retention/policies/{lib_id}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["active"] is True
    assert get_resp.json()["retention_days"] == 180

    # 3. Set Legal Hold via POST
    hold_resp = client.post(
        "/api/retention/legal-hold",
        json={
            "library_id": lib_id,
            "document_id": "doc_fin_999",
            "legal_hold": True,
            "reason": "Controllo Agenzia Entrate",
        },
        headers=headers,
    )
    assert hold_resp.status_code == 200
    assert hold_resp.json()["legal_hold"] is True

    # 4. Enforce retention API
    enforce_resp = client.post(
        "/api/retention/enforce",
        json={"library_id": lib_id, "dry_run": True},
        headers=headers,
    )
    assert enforce_resp.status_code == 200
    assert enforce_resp.json()["dry_run"] is True
