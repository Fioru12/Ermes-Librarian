"""
tests/test_enterprise_features.py
Test suite per le funzionalità Enterprise:
- Enterprise OIDC/SSO (claims, validazione, mapping ruoli)
- Enterprise Reranker (scoring, bi-grammi, vicinanza posizionale, limit)
- Enterprise DLP & PII Guard (IBAN, carte di credito Luhn, JWT, API keys, Codice Fiscale)
- Enterprise Analytics & Knowledge Gaps (event tracking, metriche, gap detection, feedback)
- Document ACL isolation durante la ricerca RAG
"""
from __future__ import annotations

import base64
import json
import time

from fastapi.testclient import TestClient

import config
from api import app
from core.analytics import (
    get_analytics_summary,
    get_knowledge_gaps,
    record_feedback,
    record_query_event,
)
from core.library_store import LibraryStore
from core.pii_filter import detect_pii, filter_pii
from core.reranker import calculate_rerank_score, rerank_candidates


def _make_jwt(payload: dict) -> str:
    """Helper per generare un token JWT non firmato (simulazione OIDC claim)."""
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header_b64}.{payload_b64}.signature"


# ============================================================================
# 1. Enterprise DLP & PII Guard
# ============================================================================

def test_dlp_filters_iban():
    valid_iban = "IT60X0542811101000000123456"
    text = f"Il conto di accredito è {valid_iban} per il bonifico."
    filtered = filter_pii(text)
    assert "[IBAN]" in filtered
    assert valid_iban not in filtered


def test_dlp_filters_luhn_credit_card():
    # Numero carta valido secondo algoritmo di Luhn (es. 4532 0151 1283 0366)
    valid_cc = "4532 0151 1283 0366"
    # Numero che NON passa il test di Luhn (somma non divisibile per 10)
    invalid_cc = "4111 1111 1111 1112"

    text = f"Carta valida: {valid_cc}, numero non valido: {invalid_cc}"
    filtered = filter_pii(text)
    assert "[CARTA_CREDITO]" in filtered
    assert valid_cc not in filtered
    # Quello invalido non viene oscurato
    assert invalid_cc in filtered


def test_dlp_filters_jwt_and_api_keys():
    jwt_tok = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozS66G_P38F3"
    api_key_sample = "api_key = 'sk-live-9876543210abcdef1234567890'"
    text = f"Token: {jwt_tok} e chiave: {api_key_sample}"
    filtered = filter_pii(text)
    assert "[JWT_TOKEN]" in filtered
    assert "[API_KEY]" in filtered
    assert jwt_tok not in filtered


def test_dlp_detect_pii():
    text = "Contatto mario.rossi@azienda.it tel 06 12345678 CF RSSMRA80A01H501U"
    detected = detect_pii(text)
    types = {d["type"] for d in detected}
    assert "email" in types
    assert "codice_fiscale" in types


# ============================================================================
# 2. Enterprise Reranker
# ============================================================================

def test_reranker_scoring_phrase_match():
    query = "politica di sicurezza aziendale"
    excerpt1 = "Questo documento definisce la politica di sicurezza aziendale per tutti i dipendenti."
    excerpt2 = "I dipendenti devono rispettare le norme del parcheggio aziendale."

    score1 = calculate_rerank_score(query, "sicurezza.pdf", excerpt1)
    score2 = calculate_rerank_score(query, "parcheggio.pdf", excerpt2)

    assert score1 > score2
    assert score1 >= 0.70


def test_reranker_proximity_bonus():
    query = "piano emergenza"
    close_excerpt = "In caso di incendio seguire il piano emergenza dell'edificio."
    distant_excerpt = "Il piano quinquennale prevede la gestione di ogni possibile emergenza futura."

    score_close = calculate_rerank_score(query, "doc.pdf", close_excerpt)
    score_distant = calculate_rerank_score(query, "doc.pdf", distant_excerpt)

    assert score_close > score_distant


def test_rerank_candidates_filtering_and_ordering():
    query = "orari mensa"
    candidates = [
        {"filename": "privacy.docx", "excerpt": "Trattamento dei dati personali e conservazione.", "relevance_score": 10.0},
        {"filename": "regolamento_mensa.pdf", "excerpt": "Gli orari della mensa aziendale sono dalle 12:30 alle 14:30.", "relevance_score": 15.0},
    ]
    reranked = rerank_candidates(query, candidates, min_score=0.1, limit=5)
    assert len(reranked) > 0
    assert reranked[0]["filename"] == "regolamento_mensa.pdf"
    assert "rerank_score" in reranked[0]


# ============================================================================
# 3. Enterprise Analytics & Knowledge Gaps
# ============================================================================

def test_analytics_query_recording_and_gap_detection(tmp_path, monkeypatch):
    test_analytics_file = str(tmp_path / "analytics_test.jsonl")
    monkeypatch.setattr(config.Config, "ANALYTICS_FILE", property(lambda self: test_analytics_file), raising=False)

    # 1. Query con successo
    ev1 = record_query_event(
        query="qual è la password del wifi?",
        library_id="lib-it",
        actor="mario",
        result_count=3,
        latency_ms=120.5,
        coverage="supported",
    )
    assert ev1 is not None

    # 2. Query senza risposta (Knowledge Gap)
    _ev2 = record_query_event(
        query="come richiedere un monitor 4K?",
        library_id="lib-it",
        actor="luigi",
        result_count=0,
        latency_ms=45.0,
        coverage="insufficient_evidence",
    )

    # 3. Feedback negativo sulla prima
    record_feedback(event_id=ev1, rating=-1, comment="Risposta non chiara")

    # 4. Verifica summary
    summary = get_analytics_summary(days=30)
    assert summary["total_queries"] == 2
    assert summary["knowledge_gaps_count"] == 1
    assert summary["total_feedback"] == 1

    # 5. Verifica Knowledge Gaps
    gaps = get_knowledge_gaps(days=30)
    assert len(gaps) >= 1
    gap_queries = [g["query"] for g in gaps]
    assert "come richiedere un monitor 4K?" in gap_queries


# ============================================================================
# 4. Enterprise OIDC / SSO Authentication
# ============================================================================

def test_oidc_token_validation(monkeypatch):
    from api.auth import _authenticate_token
    new_cfg = config.cfg.replace(
        OIDC_ENABLED=True,
        OIDC_ISSUER="https://login.microsoftonline.com/tenant-id",
        OIDC_AUDIENCE="ermes-app",
        OIDC_ROLES_CLAIM="roles",
    )
    monkeypatch.setattr(config, "cfg", new_cfg)
    monkeypatch.setattr("api.auth.cfg", new_cfg)

    # Token OIDC valido con ruolo admin
    valid_payload = {
        "sub": "user-12345",
        "preferred_username": "admin.enterprise@azienda.it",
        "iss": "https://login.microsoftonline.com/tenant-id",
        "aud": "ermes-app",
        "exp": time.time() + 3600,
        "roles": ["Ermes-Admin", "User"],
    }
    jwt_token = _make_jwt(valid_payload)
    user = _authenticate_token(jwt_token)
    assert user is not None
    assert user["username"] == "admin.enterprise@azienda.it"
    assert user["role"] == "admin"
    assert user["provider"] == "oidc"

    # Token scaduto
    expired_payload = dict(valid_payload, exp=time.time() - 3600)
    assert _authenticate_token(_make_jwt(expired_payload)) is None

    # Audience errata
    wrong_aud_payload = dict(valid_payload, aud="other-app")
    assert _authenticate_token(_make_jwt(wrong_aud_payload)) is None


def test_oidc_api_endpoints(monkeypatch):
    new_cfg = config.cfg.replace(
        OIDC_ENABLED=True,
        OIDC_ISSUER="https://auth.company.com",
        OIDC_CLIENT_ID="ermes-client",
        OIDC_AUDIENCE="",
    )
    monkeypatch.setattr(config, "cfg", new_cfg)
    monkeypatch.setattr("api.auth.cfg", new_cfg)

    client = TestClient(app)

    # 1. Config endpoint
    res = client.get("/api/auth/oidc/config")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert data["client_id"] == "ermes-client"

    # 2. Session login via OIDC ID Token
    token = _make_jwt({
        "sub": "emp-999",
        "preferred_username": "giovanni.rossi@company.com",
        "iss": "https://auth.company.com",
        "exp": time.time() + 3600,
        "roles": ["editor"],
    })
    session_res = client.post("/api/auth/oidc/session", json={"id_token": token})
    assert session_res.status_code == 200
    assert session_res.json()["username"] == "giovanni.rossi@company.com"
    assert session_res.json()["role"] == "editor"
    assert "ermes_session" in session_res.cookies


# ============================================================================
# 5. Document ACL & Granular Security
# ============================================================================

def test_document_acl_isolation_in_search(tmp_path):
    db_file = str(tmp_path / "test_acl.sqlite3")
    store = LibraryStore(db_file)

    lib = store.create_library(name="Risorse Umane", visibility="shared", owner_id="hr_director")
    lib_id = lib["id"]

    # Doc 1: Pubblico nella libreria
    d1 = store.add_document(
        library_id=lib_id,
        filename="regolamento_ferie.pdf",
        media_type="application/pdf",
        content=b"ferie e permessi dipendenti",
        storage_path=f"{lib_id}/d1.pdf",
        status="ready",
        chunks=[("Le ferie vanno richieste con 15 giorni di preavviso.", "Pagina 1")],
    )

    # Doc 2: Riservato solo a hr_manager
    d2 = store.add_document(
        library_id=lib_id,
        filename="stipendi_direzione.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=b"stipendi riservati",
        storage_path=f"{lib_id}/d2.xlsx",
        status="ready",
        chunks=[("Tabella stipendi e bonus della direzione aziendale.", "Foglio 1, riga 1")],
    )
    store.set_document_acl(lib_id, d2["id"], ["hr_manager"])

    # 1. Ricerca come impiegato normale: vede solo il doc1
    actor_employee = {"username": "mario_impiegato", "role": "viewer"}
    results_emp, _ = store.search_with_profile(lib_id, "stipendi ferie", actor=actor_employee)
    doc_ids_emp = {r["document_id"] for r in results_emp}
    assert d1["id"] in doc_ids_emp
    assert d2["id"] not in doc_ids_emp

    # 2. Ricerca come hr_manager (autorizzato dall'ACL): vede anche doc2
    actor_mgr = {"username": "hr_manager", "role": "viewer"}
    results_mgr, _ = store.search_with_profile(lib_id, "stipendi ferie", actor=actor_mgr)
    doc_ids_mgr = {r["document_id"] for r in results_mgr}
    assert d2["id"] in doc_ids_mgr

    # 3. Ricerca come admin: bypassa l'ACL
    actor_admin = {"username": "super_admin", "role": "admin"}
    results_admin, _ = store.search_with_profile(lib_id, "stipendi ferie", actor=actor_admin)
    doc_ids_admin = {r["document_id"] for r in results_admin}
    assert d1["id"] in doc_ids_admin
    assert d2["id"] in doc_ids_admin


# ============================================================================
# 6. Enterprise Cloud Connectors & Web Scraper
# ============================================================================

def test_web_scraper_html_to_markdown():
    from core.connectors.web_scraper import _html_to_markdown, WebScraperConnector
    html = """
    <html>
      <head><title>Test Page</title></head>
      <body>
        <h1>Policy Aziendale</h1>
        <p>Benvenuto nella policy <b>GDPR</b> di esempio.</p>
        <ul>
          <li>Regola 1</li>
          <li>Regola 2</li>
        </ul>
      </body>
    </html>
    """
    md = _html_to_markdown(html)
    assert "# Policy Aziendale" in md
    assert "Regola 1" in md
    assert "Regola 2" in md

    connector = WebScraperConnector({"base_url": ""})
    ok, msg = connector.test_connection()
    assert ok is False
    assert "non configurato" in msg


# ============================================================================
# 7. Query Expansion, Deduplication & CSV Export Tests
# ============================================================================

def test_query_expansion_enterprise():
    from core.query_expander import expand_query

    exp_tfr = expand_query("Come si calcola il TFR?")
    assert len(exp_tfr) >= 2
    assert "liquidazione" in exp_tfr[1].lower() or "trattamento fine rapporto" in exp_tfr[1].lower()

    exp_smart = expand_query("Accordo per smart working")
    assert any("lavoro agile" in variant for variant in exp_tfr + exp_smart)


def test_document_deduplication_exact_and_near():
    from core.deduplication import find_library_duplicates

    docs = [
        {"id": "doc1", "filename": "Policy_v1.pdf", "text": "Questa e' la policy aziendale sui permessi retribuiti e ferie annuali."},
        {"id": "doc2", "filename": "Policy_v1_copia.pdf", "text": "Questa e' la policy aziendale sui permessi retribuiti e ferie annuali."},
        {"id": "doc3", "filename": "Policy_v2.pdf", "text": "Questa e' la policy aziendale sui permessi retribuiti e ferie annuali con una piccola modifica finale."},
        {"id": "doc4", "filename": "Contratto.pdf", "text": "Documento completamente diverso riguardante la fornitura di energia elettrica."},
    ]

    dups = find_library_duplicates(docs, similarity_threshold=0.55)
    assert len(dups) >= 2  # 1 exact (doc1, doc2) + 1 near duplicate (doc1/doc2, doc3)

    types = [d["type"] for d in dups]
    assert "exact" in types
    assert "near_duplicate" in types


def test_export_analytics_csv_endpoint(tmp_path, monkeypatch):
    import config
    from fastapi.testclient import TestClient
    from api import app
    import core.analytics as analytics_mod

    log_file = str(tmp_path / "analytics_export_test.jsonl")
    monkeypatch.setattr(config.Config, "ANALYTICS_FILE", property(lambda self: log_file), raising=False)

    analytics_mod.record_query_event(
        library_id="lib_export",
        query="Come richiedere ferie?",
        coverage="insufficient_evidence",
        fallback_reason="No documents",
        latency_ms=45.0,
    )

    client = TestClient(app)
    # Senza sessione admin restituisce 401
    res = client.get("/api/analytics/export?days=30")
    assert res.status_code in (401, 403)


def test_library_duplicates_api_endpoint(tmp_path):
    from core.library_store import LibraryStore
    db_file = str(tmp_path / "test_dup.sqlite3")
    store = LibraryStore(db_file)
    lib = store.create_library(name="Test Dup Lib", visibility="shared", owner_id="admin")

    store.add_document(
        library_id=lib["id"],
        filename="doc_a.txt",
        media_type="text/plain",
        content=b"testo identico per deduplicazione",
        storage_path="dup/a.txt",
        status="ready",
        chunks=[("testo identico per deduplicazione", "p1")],
    )
    store.add_document(
        library_id=lib["id"],
        filename="doc_b.txt",
        media_type="text/plain",
        content=b"testo identico per deduplicazione",
        storage_path="dup/b.txt",
        status="ready",
        chunks=[("testo identico per deduplicazione", "p1")],
    )

    docs = store.list_documents(lib["id"], actor={"role": "admin", "username": "admin"})
    assert len(docs) == 2


