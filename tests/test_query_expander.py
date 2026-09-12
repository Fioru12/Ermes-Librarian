"""
tests/test_query_expander.py
Unit tests for core/query_expander.py (Enterprise Query Expansion & Dynamic Synonym Disambiguation).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.query_expander import (
    add_custom_synonym,
    delete_custom_synonym,
    expand_query,
    get_all_synonyms,
    load_custom_synonyms,
)


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


def test_custom_synonyms_crud_and_persistence(tmp_path: Path):
    syn_file = tmp_path / "custom_synonyms.json"

    # Inizialmente vuoto
    assert load_custom_synonyms(syn_file) == {}

    # Aggiungi un sinonimo aziendale personalizzato
    saved = add_custom_synonym("ddt", ["documento di trasporto", "bolla di consegna"], filepath=syn_file)
    assert "ddt" in saved
    assert "documento di trasporto" in saved["ddt"]
    assert "bolla di consegna" in saved["ddt"]

    # Ricarica da file
    loaded = load_custom_synonyms(syn_file)
    assert loaded == saved

    # Espansione con il termine custom
    res = expand_query("Dove trovo il ddt del fornitore?", filepath=syn_file)
    assert len(res) >= 2
    assert "documento di trasporto" in res[1].lower() or "bolla di consegna" in res[1].lower()

    # Cancellazione
    assert delete_custom_synonym("ddt", filepath=syn_file) is True
    assert load_custom_synonyms(syn_file) == {}
    assert delete_custom_synonym("ddt", filepath=syn_file) is False


def test_custom_synonyms_merge_precedence(tmp_path: Path):
    syn_file = tmp_path / "custom_synonyms.json"

    # Sovrascrivi/arricchisci un termine gia' presente in ENTERPRISE_SYNONYMS (es. tfr)
    add_custom_synonym("tfr", ["indennita aziendale di fine rapporto"], filepath=syn_file)

    all_syns = get_all_synonyms(filepath=syn_file)
    assert "tfr" in all_syns
    # Il termine custom compare per primo
    assert all_syns["tfr"][0] == "indennita aziendale di fine rapporto"
    assert "trattamento fine rapporto" in all_syns["tfr"]


def test_expand_query_multi_word_priority(tmp_path: Path):
    syn_file = tmp_path / "custom_synonyms.json"

    # Termine a due parole e termine a una parola
    add_custom_synonym("conto corrente", ["iban", "rapporto bancario"], filepath=syn_file)
    add_custom_synonym("conto", ["fattura", "saldo"], filepath=syn_file)

    res = expand_query("aggiorna conto corrente", filepath=syn_file)
    assert len(res) >= 2
    # Deve preferire l'espansione del composto più lungo "conto corrente"
    assert "iban" in res[1].lower() or "rapporto bancario" in res[1].lower()


def test_custom_synonyms_validation(tmp_path: Path):
    syn_file = tmp_path / "custom_synonyms.json"

    with pytest.raises(ValueError, match="non puo' essere vuoto"):
        add_custom_synonym("  ", ["qualcosa"], filepath=syn_file)

    with pytest.raises(ValueError, match="almeno un sinonimo valido diverso"):
        add_custom_synonym("parola", ["parola", "  "], filepath=syn_file)


def test_corrupted_json_handled_gracefully(tmp_path: Path):
    syn_file = tmp_path / "bad.json"
    syn_file.write_text("{ questo non e' un json valido }", encoding="utf-8")

    # Non deve sollevare eccezioni non gestite ma restituire dizionario vuoto
    assert load_custom_synonyms(syn_file) == {}
