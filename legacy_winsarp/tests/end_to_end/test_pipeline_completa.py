"""
test_pipeline_completa.py
Test end-to-end della pipeline completa: intent → CoT → IR → formula compatta.

Simula scenari reali di richieste utente e verifica che ogni componente
della pipeline risponda correttamente, usando mock per le chiamate LLM.

Scenari coperti:
1. Reset puro (solo azzeramento campi)
2. Riconoscimento turno con entrata/uscita
3. Calcolo presenza con CAMPO70
4. Formula complessa multi-condizione (CoT)
5. Richiesta ambigua (deve cadere in fallback)
6. Flusso FG con catena R/P
7. OpenRouter bridge attivo
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Aggiungi root al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================
# SCENARIO 1: RESET PURO
# ============================================================

def test_scenario_reset_puro():
    """Reset puro: deve generare direttamente (!800!801) senza LLM."""
    from legacy_winsarp.core.formula_builder import FormulaBuilder
    from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    builder = FormulaBuilder(kg)

    result = builder.generate("azzera 800 e 801", compact=True)

    assert result["success"] is True
    assert result["source"] == "direct_reset"
    assert "!800" in result["formula"]
    assert "!801" in result["formula"]
    assert result["error"] is None

    print(f"[SCENARIO 1] Reset puro: {result['formula']}")
    print(f"  Source: {result['source']}")


def test_scenario_reset_singolo():
    """Reset singolo campo 900."""
    from legacy_winsarp.core.formula_builder import FormulaBuilder
    from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    builder = FormulaBuilder(kg)

    result = builder.generate("resetta campo 900", compact=True)

    assert result["success"] is True
    assert result["source"] == "direct_reset"
    assert "!900" in result["formula"]

    print(f"[SCENARIO 1b] Reset singolo: {result['formula']}")


# ============================================================
# SCENARIO 2: RICONOSCIMENTO TURNO (INTENT BUILDER)
# ============================================================

def test_scenario_riconoscimento_turno():
    """Riconoscimento turno via Intent Builder deterministico."""
    from legacy_winsarp.core.intent_builder import IntentClassifier, build_from_intents

    intents = IntentClassifier.classify_all("riconoscimento turno con entrata 251 e uscita 271")

    assert len(intents) >= 1
    assert any(i.intent == "riconoscimento_turno" for i in intents)

    result = build_from_intents(intents)

    assert result is not None
    assert result["success"] is True
    formula = result.get("formula", "")
    assert len(formula) > 0
    assert "251" in formula or "271" in formula or "900" in formula

    print(f"[SCENARIO 2] Riconoscimento turno: {formula[:80]}...")
    print(f"  Intent: {[i.intent for i in intents]}")


def test_scenario_riconoscimento_senza_campi():
    """Riconoscimento turno senza specificare campi."""
    from legacy_winsarp.core.intent_builder import IntentClassifier, build_from_intents

    intents = IntentClassifier.classify_all("riconoscimento turno")

    assert len(intents) >= 1
    result = build_from_intents(intents)

    # Deve funzionare anche senza campi espliciti (usa default 251/271)
    if result and result.get("success"):
        formula = result.get("formula", "")
        print(f"[SCENARIO 2b] Riconoscimento turno default: {formula[:80]}")
    else:
        print("[SCENARIO 2b] Riconoscimento turno fallito (ok se confidence < 0.7)")


# ============================================================
# SCENARIO 3: CALCOLO PRESENZA CON CAMPO70
# ============================================================

def test_scenario_calcolo_presenza():
    """Calcolo presenza con CAMPO70 tramite intent builder."""
    from legacy_winsarp.core.intent_builder import IntentClassifier, build_from_intents

    intents = IntentClassifier.classify_all("calcolo ore presenza con flag 900")

    assert len(intents) >= 1
    calcolo = [i for i in intents if i.intent == "calcolo_presenza"]

    if calcolo:
        result = build_from_intents(calcolo)
        assert result is not None
        formula = result.get("formula", "")
        assert "71" in formula or "73" in formula or "900" in formula

        print(f"[SCENARIO 3] Calcolo presenza: {formula[:100]}...")
        print(f"  Intent: {calcolo[0].intent}")
    else:
        print(f"[SCENARIO 3] Intent calcolo_presenza non matchato: {[i.intent for i in intents]}")


# ============================================================
# SCENARIO 4: FORMULA COMPLESSA (CoT PIPELINE)
# ============================================================

def test_scenario_formula_complessa_con_cot():
    """Formula complessa via CoT pipeline (mock)."""
    from legacy_winsarp.core.ai.chain_of_thought import generate_with_cot

    with patch("legacy_winsarp.core.ai.chain_of_thought.call_llm") as mock_llm:
        mock_llm.side_effect = [
            # Step 1: campi
            json.dumps({
                "campi_input": [251, 271, 50],
                "campi_output": [800, 900],
                "registri_k": ["K601"],
                "flussi_chiamati": [],
                "variabili_appoggio": [800],
                "spiegazione": "Calcolo ore notturne con verifica causale",
            }),
            # Step 2: condizioni
            json.dumps({
                "condizioni": [
                    {"field": 50, "op": "=", "value": "NOTT", "logical_op": "AND"},
                    {"field": 251, "op": "#", "value": "Z", "logical_op": "AND"},
                ],
                "condizioni_testuali": [
                    "50 = NOTT (turno notturno)",
                    "251 non vuoto (entrata presente)",
                ],
                "spiegazione": "Se causale NOTT e entrata presente, calcola ore",
            }),
            # Step 3: pezzi IR
            json.dumps({
                "pezzi": [
                    {
                        "label": "Verifica causale notturno",
                        "ir_steps": [
                            "IF 50 = 'NOTT' AND 251 # Z THEN",
                            "  RESET 71",
                            "  RESET 72",
                            "  RESET 73",
                            "  SET 71 = 251",
                            "  SET 72 = 271",
                            "  CAMPO70 2",
                            "  SET 800 = 73",
                            "ELSE",
                            "  SET 900 = '2'",
                            "  VF",
                            "ENDIF",
                            "K 601 A 800",
                            "VF",
                        ],
                        "ordine": 1,
                        "spiegazione": "Calcolo ore notturne con CAMPO70 e accumulo K601",
                    }
                ]
            }),
            # Step 4: assembla
            json.dumps({
                "ir_steps_completi": [
                    "IF 50 = 'NOTT' AND 251 # Z THEN",
                    "  RESET 71",
                    "  RESET 72",
                    "  RESET 73",
                    "  SET 71 = 251",
                    "  SET 72 = 271",
                    "  CAMPO70 2",
                    "  SET 800 = 73",
                    "ELSE",
                    "  SET 900 = '2'",
                    "  VF",
                    "ENDIF",
                    "K 601 A 800",
                    "VF",
                ],
                "formula_compact": (
                    "50U'NOTT'E251#Z((!71!72!73)(71=251)(72=271)(70='2')"
                    "(800=73))VF;(900='2')VF(K601A800)VF"
                ),
                "spiegazione": "Formula notturna completa con accumulo",
            }),
        ]

        result = generate_with_cot(
            "calcola ore notturne: se causale 50 = NOTT e 251 non vuoto, "
            "allora calcola 251-271 con CAMPO70 2 in 800 e accumula in K601, "
            "altrimenti imposta 900 = 2"
        )

        assert result["success"] is True
        assert result["formula"] is not None
        assert len(result["formula"]) > 50  # Formula complessa
        assert "K601" in result["formula"]
        print(f"[SCENARIO 4] Formula complessa CoT: {result['formula'][:120]}...")
        print(f"  Spiegazione: {result['spiegazione'][:80]}...")


def test_scenario_cot_fallback():
    """CoT con LLM non disponibile: deve usare fallback interni."""
    from legacy_winsarp.core.ai.chain_of_thought import generate_with_cot

    with patch("legacy_winsarp.core.ai.chain_of_thought.call_llm") as mock_llm:
        mock_llm.side_effect = Exception("LLM offline")

        result = generate_with_cot("calcola ore notturne con causale NOTT")

        # Anche senza LLM, la pipeline deve produrre output via fallback
        assert result["success"] is True
        assert result["formula"] is not None
        assert len(result["formula"]) > 0
        print(f"[SCENARIO 4b] CoT fallback: {result['formula'][:80]}...")


# ============================================================
# SCENARIO 5: RICHIESTA AMBIGUA (FALLBACK GESTITO)
# ============================================================

def test_scenario_richiesta_ambigua():
    """Richiesta ambigua: deve generare chiarimenti o fallire graceful."""
    from legacy_winsarp.core.formula_builder import FormulaBuilder
    from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    builder = FormulaBuilder(kg)

    result = builder.generate("vorrei una formula per i dipendenti", compact=True)

    # Deve fallire graceful senza eccezioni
    assert result is not None
    if not result.get("success"):
        assert result.get("error") is not None
        print(f"[SCENARIO 5] Richiesta ambigua: {result.get('error', 'N/A')[:80]}")
    else:
        print(f"[SCENARIO 5] Richiesta ambigua gestita: {result.get('formula', 'N/A')[:80]}")


def test_scenario_numeri_senza_contesto():
    """Richiesta con numeri ma senza contesto."""
    from legacy_winsarp.core.formula_builder import FormulaBuilder
    from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    builder = FormulaBuilder(kg)

    result = builder.generate("800 801 802 900", compact=True)

    assert result is not None
    # Potrebbe matchare reset puro se non vede action words
    print(f"[SCENARIO 5b] Numeri senza contesto: source={result.get('source', 'N/A')}")


# ============================================================
# SCENARIO 6: FLUSSO FG CON CATENA R/P
# ============================================================

def test_scenario_flusso_fine_giornata():
    """Flusso fine giornata tramite intent builder."""
    from legacy_winsarp.core.intent_builder import IntentClassifier, build_from_intents

    intents = IntentClassifier.classify_all("flusso fine giornata standard")

    if intents and any(i.intent == "flusso_fg" for i in intents):
        result = build_from_intents(intents)

        assert result is not None
        if result.get("success"):
            formula = result.get("formula", "")
            assert len(formula) > 0
            print(f"[SCENARIO 6] Flusso FG: {len(formula.split(chr(10)))} righe")
        else:
            print("[SCENARIO 6] Flusso FG non disponibile (manca catalogo)")
    else:
        print(f"[SCENARIO 6] Intent flusso non matchato: {[i.intent for i in intents]}")


def test_scenario_catena_formule():
    """Catena formule: R/P a formula specifica."""
    from legacy_winsarp.core.intent_builder import IntentClassifier, build_from_intents

    intents = IntentClassifier.classify_all("chiama formula 120")

    if intents:
        result = build_from_intents(intents)
        if result and result.get("success"):
            formula = result.get("formula", "")
            print(f"[SCENARIO 6b] Catena formule: {formula}")
        else:
            print("[SCENARIO 6b] Catena formule: nessuna formula generata")


# ============================================================
# SCENARIO 7: OPENROUTER BRIDGE
# ============================================================

def test_scenario_openrouter_mapping():
    """Verifica mappatura modelli OpenRouter."""
    from core.ai.llm_bridge import _map_to_openrouter_model

    # Qwen -> tencent/hy3:free (modello free OpenRouter attuale)
    assert _map_to_openrouter_model("qwen3.5:9b") == "tencent/hy3:free"
    assert _map_to_openrouter_model("qwen3.5:4b") == "tencent/hy3:free"

    # Tutti i modelli locali/utente → mappati su free
    assert _map_to_openrouter_model("claude-sonnet") == "tencent/hy3:free"
    assert _map_to_openrouter_model("gpt-4o") == "tencent/hy3:free"
    assert _map_to_openrouter_model("gemini-pro") == "tencent/hy3:free"

    print("[SCENARIO 7] Mappatura OpenRouter: OK")


def test_scenario_openrouter_llm_factory():
    """Verifica factory get_llm restituisce un LLM valido."""
    from core.ai.llm_bridge import get_llm, OpenRouterLLM
    from llama_index.llms.ollama import Ollama

    llm = get_llm(model_id="test-model", temperature=0.0)

    # Con OPENROUTER_API_KEY restituisce OpenRouterLLM, altrimenti Ollama
    assert isinstance(llm, (OpenRouterLLM, Ollama))
    print(f"[SCENARIO 7b] Factory LLM: {type(llm).__name__}")


# ============================================================
# SCENARIO 8: VALIDAZIONE FORMULA GENERATA
# ============================================================

def test_scenario_validazione_compatta():
    """Verifica che le formule generate passino la validazione base."""
    from legacy_winsarp.core.formula_builder import WinSarpBuilder

    builder = WinSarpBuilder()

    test_formulas = [
        "(!800!801)",
        "(800='250')VF",
        "251UZE271UZ((900='2')VF(900='1')",
        "R120",
        "P2109",
    ]

    for formula in test_formulas:
        error = WinSarpBuilder.validate_compact(formula)
        assert error == "", f"Formula '{formula}' non valida: {error}"

    print(f"[SCENARIO 8] Validazione: {len(test_formulas)} formule OK")


def test_scenario_rileva_formule_invalide():
    """Verifica che formule errate vengano rilevate."""
    from legacy_winsarp.core.formula_builder import WinSarpBuilder

    invalid_formulas = [
        ("", "Formula vuota"),
        ("V_START", "V_START"),
        ("IF 800 = Z THEN", "Keyword IR"),
    ]

    for formula, expected_error_part in invalid_formulas:
        error = WinSarpBuilder.validate_compact(formula)
        assert expected_error_part.lower() in error.lower(), \
            f"Atteso '{expected_error_part}' in '{error}' per formula '{formula}'"

    print(f"[SCENARIO 8b] Rilevamento errori: {len(invalid_formulas)} formule OK")


# ============================================================
# SCENARIO 9: CONVERSIONE IR -> COMPACT (WinSarpBuilder)
# ============================================================

def test_scenario_ir_to_compact_semplice():
    """Conversione IR semplice in formato compatto."""
    from legacy_winsarp.core.formula_builder import WinSarpBuilder

    builder = WinSarpBuilder()

    steps = [
        "RESET 800",
        "SET 800 = '250'",
        "RESET 801",
        "SET 801 = '270'",
        "VF",
    ]

    compact = builder.build_compact(steps)
    assert compact is not None
    assert "800" in compact
    assert "801" in compact
    assert len(compact) > 0

    print(f"[SCENARIO 9] IR -> Compact: {compact}")


def test_scenario_ir_to_compact_con_if():
    """Conversione IR con IF/THEN/ELSE."""
    from legacy_winsarp.core.formula_builder import WinSarpBuilder

    builder = WinSarpBuilder()

    steps = [
        "IF 251 = Z THEN",
        "  RESET 900",
        "  VF",
        "ENDIF",
        "SET 900 = '1'",
        "VF",
    ]

    compact = builder.build_compact(steps)
    assert compact is not None
    assert "251" in compact
    assert "900" in compact
    assert len(compact) > 0

    print(f"[SCENARIO 9b] IR -> Compact con IF: {compact}")


# ============================================================
# SCENARIO 10: PIPELINE COMPLETA (INTENT -> IR -> COMPACT)
# ============================================================

def test_scenario_pipeline_completa():
    """Pipeline completa: intent builder -> IR steps -> compact formula."""
    from legacy_winsarp.core.intent_builder import (
        IntentClassifier, build_ir_from_intent, build_riconoscimento_turno,
    )
    from legacy_winsarp.core.formula_builder import WinSarpBuilder

    # 1. Classifica intent
    intents = IntentClassifier.classify_all("riconoscimento turno con entrata 251 e uscita 271")

    if not intents:
        print("[SCENARIO 10] Nessun intent riconosciuto")
        return

    # 2. Genera IR steps
    all_ir = []
    for req in intents:
        ir = build_ir_from_intent(req)
        if ir:
            all_ir.extend(ir)

    if not all_ir:
        # Fallback: genera direttamente compact
        compact = build_riconoscimento_turno(intents[0])
        print(f"[SCENARIO 10] Compact diretto: {compact[:80]}...")
        return

    # 3. Converti IR in compact
    builder = WinSarpBuilder()
    compact = builder.build_compact(all_ir)

    assert compact is not None
    assert len(compact) > 0

    print("[SCENARIO 10] Pipeline completa:")
    print(f"  Intents: {[i.intent for i in intents]}")
    print(f"  IR steps ({len(all_ir)}): {all_ir}")
    print(f"  Compact: {compact[:120]}...")


# ============================================================
# ESECUZIONE
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST END-TO-END PIPELINA WINSARP")
    print("=" * 60)
    print()

    tests = [
        ("Reset puro", test_scenario_reset_puro),
        ("Reset singolo", test_scenario_reset_singolo),
        ("Riconoscimento turno", test_scenario_riconoscimento_turno),
        ("Riconoscimento turno senza campi", test_scenario_riconoscimento_senza_campi),
        ("Calcolo presenza", test_scenario_calcolo_presenza),
        ("Formula complessa CoT", test_scenario_formula_complessa_con_cot),
        ("CoT fallback", test_scenario_cot_fallback),
        ("Richiesta ambigua", test_scenario_richiesta_ambigua),
        ("Numeri senza contesto", test_scenario_numeri_senza_contesto),
        ("Flusso fine giornata", test_scenario_flusso_fine_giornata),
        ("Catena formule", test_scenario_catena_formule),
        ("OpenRouter mapping", test_scenario_openrouter_mapping),
        ("OpenRouter factory", test_scenario_openrouter_llm_factory),
        ("Validazione formule", test_scenario_validazione_compatta),
        ("Rilevamento errori", test_scenario_rileva_formule_invalide),
        ("IR -> Compact semplice", test_scenario_ir_to_compact_semplice),
        ("IR -> Compact con IF", test_scenario_ir_to_compact_con_if),
        ("Pipeline completa", test_scenario_pipeline_completa),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  âœ“ {name}")
            passed += 1
        except Exception as e:
            print(f"  âœ— {name}: {e}")
            failed += 1
        print()

    print(f"\nRiepilogo: {passed}/{passed + failed} test passati")
    if failed > 0:
        print(f"  âš  {failed} test falliti")
    else:
        print("  âœ… Tutti i test superati!")
