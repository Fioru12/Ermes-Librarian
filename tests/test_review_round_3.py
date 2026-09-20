"""Terza tornata di una revisione esterna (21 settembre 2026): sei cablaggi.

Ognuno era vero. Nessuno era coperto da un test, perche' ognuno stava
nello spazio fra due componenti testati bene da soli.
"""

import contextlib
import io
import os
import zipfile

import pytest
from fastapi.testclient import TestClient

import api.auth
import api.libraries
import config
from api import app
from core.database_backend import _qmark_to_format, _translate_params
from core.document_parser import DocumentParseError, _validate_office_archive, extract_source_units
from core.pii_filter import regex_rejection_reason

PASSWORD = "StrongPassword!123"


# ------------------------------------------------------------- regex custom PII


@pytest.mark.parametrize("bomba", ["(a+)+", "(\\w+\\s?)*$", "(a|aa)+b", "((x)*)+"])
def test_catastrophic_backtracking_patterns_are_refused(bomba):
    assert regex_rejection_reason(bomba) is not None


@pytest.mark.parametrize(
    "buona",
    [
        r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
        r"(?:\+39)?\s?3\d{2}[\s.-]?\d{6,7}",
        r"(ab)+c",
        r"[0-9]{16}",
        r"[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]",
    ],
)
def test_ordinary_pii_patterns_are_accepted(buona):
    assert regex_rejection_reason(buona) is None


def test_an_invalid_regex_is_refused_with_the_parser_reason():
    assert "regex non valida" in (regex_rejection_reason("(") or "")


# ------------------------------------------------------------- XML DOCTYPE


def _docx_with_document_xml(document_xml: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="x"/>')
        z.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def test_a_doctype_after_4096_bytes_of_padding_is_still_refused():
    """Il controllo guardava solo i primi 4096 byte: 4097 byte di commento
    prima del DOCTYPE lo aggiravano, e ElementTree espandeva le entita'
    interne."""
    padding = b"<!-- " + b"x" * 5000 + b" -->\n"
    bomba = (
        b'<?xml version="1.0"?>\n'
        + padding
        + b'<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>\n'
        + b'<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>&lol2;</w:t></w:r></w:p></w:body></w:document>'
    )
    with pytest.raises(DocumentParseError):
        extract_source_units("bomba.docx", _docx_with_document_xml(bomba))


def test_office_archive_guard_still_accepts_a_plain_archive():
    _validate_office_archive(_docx_with_document_xml(b"<w:document/>"), "docx")


# ------------------------------------------------------------- translator


def test_question_marks_inside_string_literals_are_not_placeholders():
    assert _qmark_to_format("SELECT 1 WHERE a = ? AND b = 'perche?' AND c = ?") == (
        "SELECT 1 WHERE a = %s AND b = 'perche?' AND c = %s"
    )


def test_double_question_mark_is_the_jsonb_operator_not_two_placeholders():
    sql, _ = _translate_params("SELECT 1 WHERE j ?? 'k' AND a = ?", ("x",), "format")
    assert sql == "SELECT 1 WHERE j ? 'k' AND a = %s"


# ------------------------------------------------------------- rotte


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(
        BASE_DIR=str(app_dir), DATABASE_URL="", ADMIN_USERNAME="capo", ADMIN_PASSWORD=PASSWORD, API_KEY=""
    )
    for percorso in ("config.cfg", "api.auth.cfg", "api.libraries.cfg", "api.pii.cfg", "api.backup.cfg"):
        with contextlib.suppress(AttributeError):
            monkeypatch.setattr(percorso, test_cfg)
    monkeypatch.setattr(api.libraries, "_store", None)
    api.auth.session_store.clear()
    api.auth.login_guard.clear()
    from core.governance import create_or_update_user, ensure_default_admin
    from core.rate_limiter import get_rate_limiter

    get_rate_limiter().reset()
    ensure_default_admin(test_cfg.USERS_FILE, "capo", PASSWORD)
    create_or_update_user(test_cfg.USERS_FILE, "ospite", "viewer", PASSWORD)
    return test_cfg


def _accedi(username):
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": PASSWORD}).status_code == 200
    return client


def test_pii_test_endpoint_is_admin_only(istanza):
    ospite = _accedi("ospite")
    assert ospite.post("/api/pii/test", json={"text": "IBAN IT60X0542811101000000123456"}).status_code == 403
    capo = _accedi("capo")
    assert capo.post("/api/pii/test", json={"text": "IBAN IT60X0542811101000000123456"}).status_code == 200


def test_pii_test_endpoint_is_rate_limited(istanza, monkeypatch):
    from core.rate_limiter import get_rate_limiter

    limiter = get_rate_limiter()
    monkeypatch.setattr(limiter.config, "max_requests_per_minute", 2)
    limiter.reset()
    capo = _accedi("capo")
    esiti = [capo.post("/api/pii/test", json={"text": "x"}).status_code for _ in range(4)]
    assert esiti[-1] == 429


def test_a_catastrophic_custom_rule_cannot_be_saved(istanza):
    capo = _accedi("capo")
    risposta = capo.post(
        "/api/pii/config",
        json={"enabled_patterns": {}, "custom_rules": [{"name": "bomba", "pattern": "(a+)+$", "replacement": "[X]"}]},
    )
    assert risposta.status_code == 400
    assert "backtracking" in risposta.text


def test_backup_create_is_rate_limited(istanza, monkeypatch):
    from core.rate_limiter import get_rate_limiter

    limiter = get_rate_limiter()
    monkeypatch.setattr(limiter.config, "max_requests_per_minute", 1)
    limiter.reset()
    capo = _accedi("capo")
    primo = capo.post("/backup/create")
    secondo = capo.post("/backup/create")
    assert primo.status_code != 429
    assert secondo.status_code == 429


def test_a_failed_login_does_not_rewrite_the_users_file(istanza):
    prima = os.stat(istanza.USERS_FILE).st_mtime_ns
    client = TestClient(app)
    for _ in range(3):
        assert client.post("/api/auth/login", json={"username": "capo", "password": "sbagliata"}).status_code == 401
    assert os.stat(istanza.USERS_FILE).st_mtime_ns == prima
