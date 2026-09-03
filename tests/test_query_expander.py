"""
tests/test_query_expander.py
Unit tests for core/query_expander.py (Enterprise Query Expansion & Synonym Disambiguation).
"""
from __future__ import annotations

import pytest
from core.query_expander import expand_query, ENTERPRISE_SYNONYMS


def test_expand_query_empty():
    assert expand_query("") == [""]
    assert expand_query("   ") == ["   "]


def test_expand_query_acronym():
    # TFR dovrebbe essere espanso con "trattamento fine rapporto" o "liquidazione"
    res = expand_query("Come si richiede il TFR?")
    assert len(res) >= 2
    assert res[0] == "Come si richiede il TFR?"
    assert "trattamento fine rapporto" in res[1].lower() or "liquidazione" in res[1].lower()


def test_expand_query_synonyms_smart_working():
    res = expand_query("policy smart working")
    assert len(res) >= 2
    assert "lavoro agile" in res[1].lower() or "lavoro da remoto" in res[1].lower()


def test_expand_query_no_matches():
    query = "XYZ123456789 non-existent term"
    res = expand_query(query)
    assert res == [query]
