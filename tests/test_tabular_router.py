"""tests/test_tabular_router.py
Test suite per il modulo Router Agentico Ibrido e arricchimento evidenze tabulari.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.tabular_router import (
    detect_tabular_intent,
    enrich_with_tabular_evidence,
    is_tabular_filename,
)

SAMPLE_CSV = b"""id,nome,dipartimento,stipendio,anno
1,Mario Rossi,Vendite,35000,2024
2,Luigi Bianchi,IT,45000,2024
3,Giulia Verdi,Vendite,38000,2024
"""


def test_detect_tabular_intent():
    assert detect_tabular_intent("Qual è la somma totale degli stipendi del dipartimento IT?") is True
    assert detect_tabular_intent("Quanti dipendenti ci sono in totale nel dataset?") is True
    assert detect_tabular_intent("Mostrami la tabella con la media dei ricavi") is True
    assert detect_tabular_intent("Elenca tutti i record con stipendio maggiore di 40000") is True

    assert detect_tabular_intent("Come faccio a richiedere le ferie?") is False
    assert detect_tabular_intent("Qual è la procedura antincendio?") is False
    assert detect_tabular_intent("") is False


def test_is_tabular_filename():
    assert is_tabular_filename("bilancio.csv") is True
    assert is_tabular_filename("dipendenti.tsv") is True
    assert is_tabular_filename("catalogo.xlsx") is True
    assert is_tabular_filename("documento.pdf") is False
    assert is_tabular_filename("manuale.docx") is False
    assert is_tabular_filename("note.md") is False


def test_enrich_with_tabular_evidence_not_tabular_question():
    mock_store = MagicMock()
    mock_store.list_documents.return_value = [{"id": "doc1", "filename": "bilancio.csv"}]
    res = enrich_with_tabular_evidence("lib1", "Come richiedere un permesso?", store=mock_store)
    assert res == []


def test_enrich_with_tabular_evidence_no_tabular_documents():
    mock_store = MagicMock()
    mock_store.list_documents.return_value = [{"id": "doc1", "filename": "procedura.pdf"}]
    res = enrich_with_tabular_evidence("lib1", "Qual è la somma totale?", store=mock_store)
    assert res == []


def test_enrich_with_tabular_evidence_success():
    mock_doc = {
        "id": "doc_tab_1",
        "filename": "dipendenti.csv",
        "storage_path": "libraries/lib1/dipendenti.csv",
        "version": 2,
    }
    mock_store = MagicMock()
    mock_store.list_documents.return_value = [mock_doc]

    with patch("core.tabular_router.get_storage_provider") as mock_get_storage:
        mock_storage = MagicMock()
        mock_storage.get.return_value = SAMPLE_CSV
        mock_get_storage.return_value = mock_storage

        citations = enrich_with_tabular_evidence(
            "lib1",
            "Qual è la somma totale degli stipendi?",
            store=mock_store,
        )

        assert len(citations) == 1
        cit = citations[0]
        assert cit["document_id"] == "doc_tab_1"
        assert cit["citation"]["filename"] == "dipendenti.csv"
        assert cit["citation"]["version"] == 2
        assert "Tabella: data (3 righe totali)" in cit["excerpt"]
        assert "Mario Rossi" in cit["excerpt"]
        assert cit["is_tabular"] is True
