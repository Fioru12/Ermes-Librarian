"""tests/test_tabular_engine.py
Test suite per il motore sandboxed di analisi tabulare e schema introspection (CSV, XLSX).
"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api import app
from api.auth import _verify_api_key
from core.tabular_engine import (
    TabularQueryError,
    format_markdown_table,
    get_tabular_schema,
    infer_data_type,
    query_tabular_data,
    sanitize_column_name,
    validate_sql_query,
)


# ── Test Sanitizzazione e Inferenza Tipi ──────────────────────────────────────────


def test_sanitize_column_name():
    assert sanitize_column_name("Nome Dipendente", 0) == "nome_dipendente"
    assert sanitize_column_name("123 Fatturato ($)", 1) == "col_123_fatturato"
    assert sanitize_column_name("   ", 2) == "col_2"
    assert sanitize_column_name("valid_name", 3) == "valid_name"


def test_infer_data_type():
    assert infer_data_type(["10", "20", "300"]) == "INTEGER"
    assert infer_data_type(["10", "20.5", "300"]) == "REAL"
    assert infer_data_type(["1,000.50", "20.5"]) == "REAL"
    assert infer_data_type(["test", "10", "20"]) == "TEXT"
    assert infer_data_type(["", "  "]) == "TEXT"


def test_format_markdown_table():
    assert format_markdown_table([], []) == ""
    cols = ["nome", "valore"]
    rows = [["Alice", 100], ["Bob", 200]]
    md = format_markdown_table(cols, rows)
    assert "| nome | valore |" in md
    assert "| Alice | 100 |" in md
    assert "| Bob | 200 |" in md


# ── Test Validatore SQL di Sicurezza ────────────────────────────────────────────


def test_validate_sql_query_valid():
    assert validate_sql_query("SELECT * FROM data") == "SELECT * FROM data"
    assert (
        validate_sql_query(
            "WITH summary AS (SELECT department, SUM(salary) as total FROM data GROUP BY department) SELECT * FROM summary"
        )
        is not None
    )
    assert validate_sql_query("EXPLAIN QUERY PLAN SELECT * FROM data") == "EXPLAIN QUERY PLAN SELECT * FROM data"


def test_validate_sql_query_forbidden():
    with pytest.raises(TabularQueryError, match="solo query SELECT"):
        validate_sql_query("DROP TABLE data")

    with pytest.raises(TabularQueryError, match="solo query SELECT"):
        validate_sql_query("INSERT INTO data VALUES (1, 'hack')")

    with pytest.raises(TabularQueryError, match="multi-istruzione"):
        validate_sql_query("SELECT * FROM data; DROP TABLE data")

    with pytest.raises(TabularQueryError, match="multi-istruzione"):
        validate_sql_query("SELECT * FROM data WHERE 1=1; PRAGMA table_info(data)")


# ── Test Ingestion CSV & Query ──────────────────────────────────────────────────


SAMPLE_CSV = b"""id,nome,dipartimento,stipendio,anno
1,Mario Rossi,Vendite,35000,2024
2,Luigi Bianchi,IT,45000,2024
3,Giulia Verdi,Vendite,38000,2024
4,Anna Neri,IT,52000,2024
5,Paolo Gialli,HR,30000,2024
"""


def test_csv_schema_introspection():
    schema = get_tabular_schema(SAMPLE_CSV, "stipendi.csv", table_name="data")
    assert schema.table_name == "data"
    assert schema.row_count == 5
    col_names = [c.name for c in schema.columns]
    assert "nome" in col_names
    assert "dipartimento" in col_names
    assert "stipendio" in col_names
    assert len(schema.sample_rows) == 5


def test_csv_sql_aggregations():
    # Test aggregazioni SUM, AVG, GROUP BY
    query = """
    SELECT dipartimento, COUNT(*) as n_dipendenti, AVG(stipendio) as stipendio_medio, SUM(stipendio) as tot_stipendi
    FROM data
    GROUP BY dipartimento
    ORDER BY tot_stipendi DESC
    """
    res = query_tabular_data(SAMPLE_CSV, "stipendi.csv", query)
    assert res.row_count == 3
    assert res.columns == ["dipartimento", "n_dipendenti", "stipendio_medio", "tot_stipendi"]
    # IT ha 45000 + 52000 = 97000 (top 1)
    assert res.rows[0][0] == "IT"
    assert res.rows[0][1] == 2
    assert res.rows[0][3] == 97000
    assert "| dipartimento | n_dipendenti |" in res.markdown_table


def test_csv_where_filter():
    query = "SELECT nome, stipendio FROM data WHERE stipendio > 40000 ORDER BY stipendio DESC"
    res = query_tabular_data(SAMPLE_CSV, "stipendi.csv", query)
    assert res.row_count == 2
    assert res.rows[0][0] == "Anna Neri"
    assert res.rows[1][0] == "Luigi Bianchi"


# ── Test Ingestion Excel XLSX ──────────────────────────────────────────────────


def _create_dummy_xlsx() -> bytes:
    """Crea uno zip OpenXML/XLSX minimale con sharedStrings e sheet1."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # sharedStrings.xml
        shared_strings = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="6" uniqueCount="6">
    <si><t>Prodotto</t></si>
    <si><t>Categoria</t></si>
    <si><t>Prezzo</t></si>
    <si><t>Laptop</t></si>
    <si><t>Elettronica</t></si>
    <si><t>Mouse</t></si>
</sst>"""
        zf.writestr("xl/sharedStrings.xml", shared_strings)

        # sheet1.xml
        sheet_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <sheetData>
        <row r="1">
            <c r="A1" t="s"><v>0</v></c>
            <c r="B1" t="s"><v>1</v></c>
            <c r="C1" t="s"><v>2</v></c>
        </row>
        <row r="2">
            <c r="A2" t="s"><v>3</v></c>
            <c r="B2" t="s"><v>4</v></c>
            <c r="C2"><v>1200</v></c>
        </row>
        <row r="3">
            <c r="A3" t="s"><v>5</v></c>
            <c r="B3" t="s"><v>4</v></c>
            <c r="C3"><v>25</v></c>
        </row>
    </sheetData>
</worksheet>"""
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        zf.writestr("[Content_Types].xml", "<Types></Types>")

    buf.seek(0)
    return buf.read()


def test_xlsx_ingestion_and_query():
    xlsx_bytes = _create_dummy_xlsx()
    schema = get_tabular_schema(xlsx_bytes, "catalogo.xlsx")
    assert schema.row_count == 2
    assert "prodotto" in [c.name for c in schema.columns]

    res = query_tabular_data(xlsx_bytes, "catalogo.xlsx", "SELECT prodotto, prezzo FROM data WHERE prezzo > 100")
    assert res.row_count == 1
    assert res.rows[0][0] == "Laptop"
    assert res.rows[0][1] == 1200


# ── Test API Endpoints ─────────────────────────────────────────────────────────


@pytest.fixture
def client():
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "admin", "role": "admin"}
    yield TestClient(app)
    app.dependency_overrides.pop(_verify_api_key, None)


def test_api_tabular_schema_and_query(client):
    mock_doc = {
        "id": "doc_tabular_1",
        "filename": "bilancio.csv",
        "storage_path": "libraries/lib1/bilancio.csv",
    }
    mock_lib = {"id": "lib1", "name": "Finanza"}

    mock_store = MagicMock()
    mock_store.get_library.return_value = mock_lib
    mock_store.get_document.return_value = mock_doc

    from api.libraries import get_library_store

    app.dependency_overrides[get_library_store] = lambda: mock_store

    try:
        with patch("api.tabular.get_storage_provider") as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.get.return_value = SAMPLE_CSV
            mock_get_storage.return_value = mock_storage

            # 1. GET schema
            resp_schema = client.get(
                "/api/libraries/lib1/documents/doc_tabular_1/schema",
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp_schema.status_code == 200
            data_schema = resp_schema.json()
            assert data_schema["document_id"] == "doc_tabular_1"
            assert data_schema["row_count"] == 5

            # 2. POST query-table (valid SQL)
            resp_query = client.post(
                "/api/libraries/lib1/documents/doc_tabular_1/query-table",
                json={"query": "SELECT dipartimento, SUM(stipendio) as tot FROM data GROUP BY dipartimento"},
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp_query.status_code == 200
            data_query = resp_query.json()
            assert data_query["row_count"] == 3
            assert "markdown_table" in data_query

            # 3. POST query-table (unsafe SQL -> 400)
            resp_unsafe = client.post(
                "/api/libraries/lib1/documents/doc_tabular_1/query-table",
                json={"query": "DELETE FROM data"},
                headers={"Authorization": "Bearer test-key"},
            )
            assert resp_unsafe.status_code == 400
            assert "solo query SELECT" in resp_unsafe.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_library_store, None)


def test_api_tabular_non_tabular_file(client):
    mock_doc = {
        "id": "doc_pdf_1",
        "filename": "documento.pdf",
        "storage_path": "libraries/lib1/documento.pdf",
    }
    mock_store = MagicMock()
    mock_store.get_library.return_value = {"id": "lib1"}
    mock_store.get_document.return_value = mock_doc

    from api.libraries import get_library_store

    app.dependency_overrides[get_library_store] = lambda: mock_store

    try:
        resp = client.get(
            "/api/libraries/lib1/documents/doc_pdf_1/schema",
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code == 400
        assert "non è un formato tabulare" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_library_store, None)
