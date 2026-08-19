"""
test_glossary_offline.py

Test offline del glossario semantico WinSarp, senza dipendere da LLM esterni.
Valida che:
1. expand_query riconosca correttamente i concetti di business
2. resolve_synonyms risolva i sinonimi senza cascate
3. QueryEnricher produca contesto arricchito
4. route_and_process con LLM mockato usi il glossario per classificare

Nessun call_llm, nessun OpenRouter, nessun Ollama.
"""

import sys

sys.path.insert(0, "C:/ProgettoRAG_DEV")

from legacy_winsarp.core.winsarp.glossary import (
    expand_query,
    resolve_synonyms,
    CONCEPT_TO_FIELD,
    CONCEPT_TO_FORMULA,
    SCENARIO_FLOWS,
    BUSINESS_RULES,
)
from legacy_winsarp.core.intent_router import route_and_process, QueryEnricher


# ============================================================
# TEST 1: expand_query riconosce concetti business
# ============================================================

def test_expand_straordinario_festivo_notturno():
    r = expand_query("straordinario festivo notturno con autorizzazione")
    assert "straordinario festivo notturno" in r["matched_concepts"]
    assert "autorizzazione straordinario" in r["matched_concepts"]
    # Campi attesi: 4 (straord), 21 (notturno), 55 (festivo), 820/821 (auts)
    assert 4 in r["fields"]
    assert 21 in r["fields"]
    assert 55 in r["fields"]
    assert 820 in r["fields"]
    # Formule: 130 (straord festivo), 3004, 3017 (auts)
    assert 130 in r["formulas"]
    assert 3017 in r["formulas"]
    # Causali: SFN / SNF
    assert "SFN" in r["causali"] or "SNF" in r["causali"]
    # Scenari: straordinario_con_auts deve matchare
    assert "straordinario_con_auts" in r["matched_scenarios"]
    print("  [OK] straordinario festivo notturno + auts")


def test_expand_turnista_notte_pausa():
    r = expand_query("gestisci il turnista notturno con pausa pranzo")
    assert "turno notturno" in r["matched_concepts"]
    assert "pausa pranzo" in r["matched_concepts"]
    # Campi: 58 (tipo turno), 900 (flag), 3020 (pausa)
    assert 58 in r["fields"]
    assert 900 in r["fields"]
    assert 3020 in r["formulas"]
    print("  [OK] turnista notte + pausa pranzo")


def test_expand_arrotondamento_quarti():
    r = expand_query("arrotonda le ore ai quarti d'ora")
    assert "arrotondamento quarti" in r["matched_concepts"]
    assert "arrotondamento" in r["matched_concepts"]
    # Regole: BR011 (quarti standard)
    assert "BR011" in r["matched_rules"]
    print("  [OK] arrotondamento quarti")


def test_expand_festivo_domenica():
    r = expand_query("come gestire un giorno festivo di domenica")
    assert "festivo" in r["matched_concepts"]
    assert "domenica" in r["matched_concepts"]
    # Formule festività
    assert 2109 in r["formulas"] or 3009 in r["formulas"]
    print("  [OK] festivo domenica")


# ============================================================
# TEST 2: resolve_synonyms senza cascate
# ============================================================

def test_resolve_synonyms_no_cascade():
    out = resolve_synonyms("ore normali e lavoro di notte con sa")
    # "ore normali" -> "ore ordinarie"
    assert "ore ordinarie" in out
    # "lavoro di notte" -> "notturno"
    assert "notturno" in out
    # "sa" -> "straordinario diurno"
    assert "straordinario diurno" in out
    # Nessuna fusione deforme tipo "maggiorazionnotturna"
    assert "maggiorazionnotturna" not in out
    print("  [OK] resolve_synonyms no cascade")


def test_resolve_synonyms_turno():
    out = resolve_synonyms("maggiorazione notturna per turnista")
    assert "maggiorazione notturna" in out
    assert "turnista" in out
    # "n" (sigla) non deve espandersi dentro "con" o "turnista"
    assert "maggiorazionnotturna" not in out
    print("  [OK] resolve_synonyms turno")


# ============================================================
# TEST 3: QueryEnricher produce contesto
# ============================================================

def test_query_enricher_context():
    e = QueryEnricher()
    ctx = e.enrich("come calcolo lo straordinario notturno per un festivo?")
    assert len(ctx) > 100
    # Deve contenere riferimenti a campi/formule dal glossario
    assert "21" in ctx or "55" in ctx or "130" in ctx
    print("  [OK] QueryEnricher context len=%d" % len(ctx))


# ============================================================
# TEST 4: route_and_process con LLM mockato
# ============================================================

def _mock_call_llm(prompt, model_id=None, temp=0.0, json_mode=False, timeout=30):
    """Mock che simula l'LLM: se la query espansa contiene il marcatore
    '[Glossario:' (aggiunto da expand_query quando trova concetti),
    classifica come retrieval, altrimenti clarification."""
    low = prompt.lower()
    # expand_query aggiunge '[Glossario: campi: [...]; formule: [...]' solo se trova qualcosa
    if "[glossario:" in low:
        return (
            '{"action": "retrieval", "confidence": 0.9, '
            '"campi_coinvolti": [4, 21, 55], "formula_riferimento": 130, '
            '"descrizione_richiesta": "straordinario festivo notturno", '
            '"parole_chiave": ["straordinario", "festivo", "notturno"], '
            '"motivazione": "Classificato tramite glossario"}'
        )
    return (
        '{"action": "clarification", "confidence": 0.3, '
        '"campi_coinvolti": [], "formula_riferimento": null, '
        '"descrizione_richiesta": "non classificato", '
        '"parole_chiave": [], "motivazione": "fallback"}'
    )


def test_route_with_glossary_mocked(monkeypatch=None):
    """Verifica che route_and_process, con LLM mockato, riceva il contesto
    dal glossario e classifichi correttamente."""
    import legacy_winsarp.core.intent_router as ir
    if monkeypatch is not None:
        monkeypatch.setattr(ir, "call_llm", _mock_call_llm)
        monkeypatch.setattr(ir, "_search_documentazione", lambda req: "")
    else:
        # Mock manuale per esecuzione diretta (no pytest)
        ir.call_llm = _mock_call_llm
        ir._search_documentazione = lambda req: ""

    res = route_and_process(
        "come gestire lo straordinario notturno festivo per un turnista?",
        model_id=None,
    )
    assert res["action"] == "retrieval"
    assert res["confidence"] >= 0.9
    print("  [OK] route_and_process con glossario -> retrieval (conf=%.2f)" % res["confidence"])


def test_route_without_glossary_mocked(monkeypatch=None):
    """Senza glossario (query vuota/ambigua) deve andare in clarification."""
    import legacy_winsarp.core.intent_router as ir
    if monkeypatch is not None:
        monkeypatch.setattr(ir, "call_llm", _mock_call_llm)
        monkeypatch.setattr(ir, "_search_documentazione", lambda req: "")
    else:
        ir.call_llm = _mock_call_llm
        ir._search_documentazione = lambda req: ""

    res = route_and_process("salve", model_id=None)
    assert res["action"] == "clarification"
    print("  [OK] route_and_process senza contesto -> clarification")


# ============================================================
# TEST 5: Integrità strutturale del glossario
# ============================================================

def test_glossary_integrity():
    # Tutti i campi in CONCEPT_TO_FIELD devono essere int o 'Kxxx'
    for concept, m in CONCEPT_TO_FIELD.items():
        for f in m["fields"]:
            assert isinstance(f, int) or (isinstance(f, str) and f.startswith("K")), (
                f"Campo non valido in {concept}: {f}"
            )
    # Ogni formula in CONCEPT_TO_FORMULA deve avere descrizione
    for concept, m in CONCEPT_TO_FORMULA.items():
        assert m.get("description"), f"Manca descrizione per {concept}"
    # Ogni scenario deve avere flows
    for name, s in SCENARIO_FLOWS.items():
        assert s.get("flows"), f"Scenario {name} senza flows"
    # BUSINESS_RULES devono avere id e rule
    for r in BUSINESS_RULES:
        assert r.get("id") and r.get("rule"), "Regola senza id/rule"
    print("  [OK] glossario integro: %d concetti, %d formule, %d scenari, %d regole" % (
        len(CONCEPT_TO_FIELD), len(CONCEPT_TO_FORMULA), len(SCENARIO_FLOWS), len(BUSINESS_RULES)))


if __name__ == "__main__":
    print("=== TEST GLOSSARIO OFFLINE ===\n")
    test_expand_straordinario_festivo_notturno()
    test_expand_turnista_notte_pausa()
    test_expand_arrotondamento_quarti()
    test_expand_festivo_domenica()
    print()
    test_resolve_synonyms_no_cascade()
    test_resolve_synonyms_turno()
    print()
    test_query_enricher_context()
    print()
    # I test con monkeypatch richiedono pytest; se lanciati direttamente,
    # simuliamo con un mock manuale
    import legacy_winsarp.core.intent_router as ir
    orig = ir.call_llm
    ir.call_llm = _mock_call_llm
    ir._search_documentazione = lambda req: ""
    try:
        test_route_with_glossary_mocked(None)
        test_route_without_glossary_mocked(None)
    finally:
        ir.call_llm = orig
    print()
    test_glossary_integrity()
    print("\n=== TUTTI I TEST PASSATI ===")
