"""
test_chain_of_thought.py
Test per il modulo Chain-of-Thought decomposer.
Verifica i fallback e la struttura del modulo,
senza chiamate LLM reali (usa mock).
"""

import json
from unittest.mock import patch

from legacy_winsarp.core.ai.chain_of_thought import (
    ChainOfThoughtEngine,
    CoTStep1_Fields,
    CoTStep2_Conditions,
    CoTStep3_IR_Piece,
    CoTStep4_Final,
    generate_with_cot,
)


# ============================================================
# TEST STRUTTURALI (senza LLM)
# ============================================================


class TestCoTStep1Fields:
    """Test per il dataclass CoTStep1_Fields e step1 fallback."""

    def test_empty_constructor(self):
        fields = CoTStep1_Fields()
        assert fields.campi_input == []
        assert fields.campi_output == []
        assert fields.registri_k == []
        assert fields.flussi_chiamati == []
        assert fields.variabili_appoggio == []
        assert fields.spiegazione == ""

    def test_filled_constructor(self):
        fields = CoTStep1_Fields(
            campi_input=[251, 271],
            campi_output=[800, 900],
            registri_k=["K601", "K602"],
            flussi_chiamati=[120, 2109],
            variabili_appoggio=[800],
            spiegazione="Test formula",
        )
        assert 251 in fields.campi_input
        assert 800 in fields.campi_output
        assert "K601" in fields.registri_k
        assert 120 in fields.flussi_chiamati
        assert fields.spiegazione == "Test formula"

    def test_step1_fallback_regex(self):
        """Verifica che il fallback regex estragga i campi."""
        engine = ChainOfThoughtEngine()
        result = engine._step1_fallback("azzera 800 e 801 e imposta 900 = 1")
        assert 800 in result.campi_input
        assert 801 in result.campi_input
        assert 900 in result.campi_input
        assert "Fallback regex" in result.spiegazione


class TestCoTStep2Conditions:
    """Test per CoTStep2_Conditions."""

    def test_empty_constructor(self):
        cond = CoTStep2_Conditions()
        assert cond.condizioni == []
        assert cond.condizioni_testuali == []
        assert cond.spiegazione == ""

    def test_with_conditions(self):
        cond = CoTStep2_Conditions(
            condizioni=[{"field": 251, "op": "=", "value": "Z"}],
            condizioni_testuali=["entrata vuota"],
            spiegazione="Test condizioni",
        )
        assert len(cond.condizioni) == 1
        assert cond.condizioni[0]["field"] == 251


class TestCoTStep3IRPiece:
    """Test per CoTStep3_IR_Piece."""

    def test_minimal_piece(self):
        piece = CoTStep3_IR_Piece(label="Test", ir_steps=["SET 800 = '100'", "VF"])
        assert piece.label == "Test"
        assert len(piece.ir_steps) == 2
        assert piece.ordine == 0

    def test_ordering(self):
        p1 = CoTStep3_IR_Piece(label="A", ir_steps=[], ordine=2)
        p2 = CoTStep3_IR_Piece(label="B", ir_steps=[], ordine=1)
        pieces = sorted([p1, p2], key=lambda x: x.ordine)
        assert pieces[0].label == "B"


class TestCoTStep4Final:
    """Test per CoTStep4_Final."""

    def test_minimal_final(self):
        final = CoTStep4_Final(
            ir_steps_completi=["RESET 800", "VF"],
            formula_compact="(!800)\nVF;",
        )
        assert len(final.ir_steps_completi) == 2
        assert "!800" in final.formula_compact


# ============================================================
# TEST MINI CONVERTER
# ============================================================


class TestMiniCompact:
    """Test per _mini_compact converter."""

    def test_simple_set(self):
        engine = ChainOfThoughtEngine()
        result = engine._mini_compact([
            "SET 800 = '250'",
            "VF",
        ])
        assert "(800='250')" in result
        assert "VF" in result

    def test_reset(self):
        engine = ChainOfThoughtEngine()
        result = engine._mini_compact([
            "RESET 800",
            "RESET 801",
        ])
        assert "(!800)" in result
        assert "(!801)" in result

    def test_r_and_p(self):
        engine = ChainOfThoughtEngine()
        result = engine._mini_compact([
            "R 120",
            "P 2109",
        ])
        assert "R120" in result
        assert "P2109" in result

    def test_k_accumulo(self):
        engine = ChainOfThoughtEngine()
        result = engine._mini_compact([
            "K 601 A '3'",
            "K 602 A '5'",
        ])
        assert "K601" in result
        assert "K602" in result

    def test_campo70(self):
        engine = ChainOfThoughtEngine()
        result = engine._mini_compact([
            "CAMPO70 2",
            "VF",
        ])
        assert "(70='2')" in result

    def test_if_then(self):
        engine = ChainOfThoughtEngine()
        result = engine._mini_compact([
            "IF 251 = Z THEN",
            "  RESET 900",
            "ENDIF",
            "VF",
        ])
        assert "251 U Z" in result
        assert "(!900)" in result
        assert "VF" in result


# ============================================================
# TEST SAFE PARSE JSON
# ============================================================


class TestSafeParseJson:
    """Test per _safe_parse_json."""

    def test_raw_json(self):
        engine = ChainOfThoughtEngine()
        result = engine._safe_parse_json('{"field": 800, "value": "test"}')
        assert result is not None
        assert result["field"] == 800

    def test_markdown_fence_json(self):
        engine = ChainOfThoughtEngine()
        result = engine._safe_parse_json('```json\n{"field": 800}\n```')
        assert result is not None
        assert result["field"] == 800

    def test_code_fence_no_lang(self):
        engine = ChainOfThoughtEngine()
        result = engine._safe_parse_json('```\n{"field": 800}\n```')
        assert result is not None
        assert result["field"] == 800

    def test_invalid_string(self):
        engine = ChainOfThoughtEngine()
        result = engine._safe_parse_json("Not JSON at all")
        assert result is None

    def test_extract_first_brace(self):
        engine = ChainOfThoughtEngine()
        result = engine._safe_parse_json('Some text before\n{"inner": "value"}\nSome text after')
        assert result is not None
        assert result["inner"] == "value"

    def test_empty_string(self):
        engine = ChainOfThoughtEngine()
        result = engine._safe_parse_json("")
        assert result is None

    def test_none_input(self):
        engine = ChainOfThoughtEngine()
        result = engine._safe_parse_json(None)
        assert result is None


# ============================================================
# TEST _COND_TO_COMPACT
# ============================================================


class TestCondToCompact:
    """Test per _cond_to_compact helper."""

    def test_equals(self):
        from legacy_winsarp.core.ai.chain_of_thought import _cond_to_compact
        result = _cond_to_compact("251 = Z")
        assert "251 U Z" in result

    def test_greater(self):
        from legacy_winsarp.core.ai.chain_of_thought import _cond_to_compact
        result = _cond_to_compact("800 > 0")
        assert "800 >" in result

    def test_not_equal(self):
        from legacy_winsarp.core.ai.chain_of_thought import _cond_to_compact
        result = _cond_to_compact("800 != 0")
        assert "800 #" in result

    def test_greater_equal(self):
        from legacy_winsarp.core.ai.chain_of_thought import _cond_to_compact
        result = _cond_to_compact("800 >= 1")
        assert "800 >U" in result

    def test_less_equal(self):
        from legacy_winsarp.core.ai.chain_of_thought import _cond_to_compact
        result = _cond_to_compact("800 <= 100")
        assert "800 <U" in result


# ============================================================
# TEST PIPELINE FALLBACK (senza LLM)
# ============================================================


class TestPipelineFallbacks:
    """Test che i fallback della pipeline funzionino."""

    def test_empty_request(self):
        """Il fallback regex deve estrarre campi anche da richiesta vuota."""
        engine = ChainOfThoughtEngine()
        fields = engine._step1_fallback("")
        assert fields is not None
        assert fields.campi_input == []

    def test_request_with_fields(self):
        engine = ChainOfThoughtEngine()
        fields = engine._step1_fallback("imposta 800 = 250 e azzera 801")
        assert 800 in fields.campi_input
        assert 801 in fields.campi_input

    def test_step3_fallback_no_conditions(self):
        engine = ChainOfThoughtEngine()
        fields = CoTStep1_Fields(campi_output=[800, 801])
        conditions = CoTStep2_Conditions()
        pieces = engine._step3_fallback(fields, conditions)
        assert len(pieces) == 1
        assert "Formula generica (fallback)" in pieces[0].label

    def test_step3_fallback_with_conditions(self):
        engine = ChainOfThoughtEngine()
        fields = CoTStep1_Fields(campi_output=[900])
        conditions = CoTStep2_Conditions(
            condizioni=[{"field": 251, "op": "=", "value": "Z"}]
        )
        pieces = engine._step3_fallback(fields, conditions)
        assert len(pieces) == 1
        assert any("251" in s for s in pieces[0].ir_steps)

    def test_step4_fallback_orders_pieces(self):
        engine = ChainOfThoughtEngine()
        pieces = [
            CoTStep3_IR_Piece(label="Secondo", ir_steps=["RESET 801", "VF"], ordine=2),
            CoTStep3_IR_Piece(label="Primo", ir_steps=["RESET 800", "VF"], ordine=1),
        ]
        final = engine._step4_fallback(pieces)
        assert len(final.ir_steps_completi) >= 1
        assert final.formula_compact is not None

    def test_step4_fallback_empty_pieces(self):
        engine = ChainOfThoughtEngine()
        final = engine._step4_fallback([])
        assert "Nessuna logica generata" in " ".join(final.ir_steps_completi)

    def test_get_pipeline_summary_empty(self):
        engine = ChainOfThoughtEngine()
        summary = engine.get_pipeline_summary()
        assert summary["steps"] == 0
        assert summary["formula_len"] == 0

    def test_get_debug_log_empty(self):
        engine = ChainOfThoughtEngine()
        assert engine.get_debug_log() == []


# ============================================================
# TEST GENERATE_WITH_COT (con mock)
# ============================================================


class TestGenerateWithCot:
    """Test generate_with_cot con LLM mockato."""

    def test_success(self):
        """Verifica che con risposte valide la pipeline produca output."""
        with patch("legacy_winsarp.core.ai.chain_of_thought.call_llm") as mock_llm:
            # Mock delle 4 chiamate LLM
            mock_llm.side_effect = [
                # Step 1: Identifica campi
                json.dumps({
                    "campi_input": [251, 271],
                    "campi_output": [900],
                    "registri_k": [],
                    "flussi_chiamati": [],
                    "variabili_appoggio": [],
                    "spiegazione": "Riconoscimento turno: entrata e uscita",
                }),
                # Step 2: Identifica condizioni
                json.dumps({
                    "condizioni": [{"field": 251, "op": "=", "value": "Z", "logical_op": "AND"}],
                    "condizioni_testuali": ["entrata vuota"],
                    "spiegazione": "Se entrata vuota, flag=2",
                }),
                # Step 3: Costruisci pezzi IR
                json.dumps({
                    "pezzi": [
                        {
                            "label": "Riconoscimento turno",
                            "ir_steps": [
                                "RESET 900",
                                "IF 251 = Z AND 271 = Z THEN",
                                "  SET 900 = '2'",
                                "  VF",
                                "ENDIF",
                                "SET 900 = '1'",
                                "SET 900 = 271 S 251",
                                "VF",
                            ],
                            "ordine": 1,
                            "spiegazione": "Calcolo ore presenza",
                        }
                    ]
                }),
                # Step 4: Assembla formula finale
                json.dumps({
                    "ir_steps_completi": [
                        "RESET 900",
                        "IF 251 = Z AND 271 = Z THEN",
                        "  SET 900 = '2'",
                        "  VF",
                        "ENDIF",
                        "SET 900 = '1'",
                        "SET 900 = 271 S 251",
                        "VF",
                    ],
                    "formula_compact": "(!900)251UZE271UZ((900='2')VF(900='1')(900=271S251)VF",
                    "spiegazione": "Formula riconoscimento turno completa",
                }),
            ]

            result = generate_with_cot("riconoscimento turno con entrata 251 e uscita 271")
            assert result["success"] is True
            assert result["formula"] is not None
            assert len(result["formula"]) > 0
            assert result["spiegazione"] is not None

    def test_empty_response(self):
        """Se l'LLM non produce output, la pipeline produce formula di fallback."""
        with patch("legacy_winsarp.core.ai.chain_of_thought.call_llm") as mock_llm:
            # Tutte le risposte LLM falliscono -> pipeline usa fallback interni
            mock_llm.side_effect = Exception("LLM non disponibile")
            result = generate_with_cot("test request")
            # La pipeline ha fallback interni, quindi produce output anche senza LLM
            assert result["success"] is True  # fallback funziona
            assert result["formula"] is not None
            assert len(result["formula"]) > 0

    def test_partial_response(self):
        """Se qualche step fallisce, il fallback deve produrre output."""
        with patch("legacy_winsarp.core.ai.chain_of_thought.call_llm") as mock_llm:
            mock_llm.side_effect = [
                # Step 1 funziona
                json.dumps({
                    "campi_input": [800],
                    "campi_output": [801],
                    "registri_k": [],
                    "flussi_chiamati": [],
                    "variabili_appoggio": [],
                    "spiegazione": "Test",
                }),
                # Step 2 fallisce
                Exception("LLM errore step 2"),
                # Step 3 non chiamato
                json.dumps({"pezzi": []}),
                # Step 4 non chiamato
                json.dumps({"ir_steps_completi": [], "formula_compact": ""}),
            ]
            result = generate_with_cot("test")
            # Il fallback dello step 2 deve produrre condizioni vuote
            # e il resto della pipeline deve continuare
            assert result is not None

    def test_complex_formula(self):
        """Test con formula complessa multi-condizione."""
        with patch("legacy_winsarp.core.ai.chain_of_thought.call_llm") as mock_llm:
            mock_llm.side_effect = [
                # Step 1
                json.dumps({
                    "campi_input": [251, 271, 252, 272, 50, 55],
                    "campi_output": [800, 900, 801],
                    "registri_k": ["K601", "K602"],
                    "flussi_chiamati": [2109],
                    "variabili_appoggio": [800, 801],
                    "spiegazione": "Formula complessa con più condizioni",
                }),
                # Step 2
                json.dumps({
                    "condizioni": [
                        {"field": 50, "op": "=", "value": "I", "logical_op": "AND"},
                        {"field": 55, "op": "=", "value": "I", "logical_op": "AND"},
                        {"field": 251, "op": "=", "value": "Z", "logical_op": "OR"},
                    ],
                    "condizioni_testuali": [
                        "50 = I (turno attivo)",
                        "55 = I (festivo)",
                        "251 vuoto (senza entrata)",
                    ],
                    "spiegazione": "Tre condizioni combinate",
                }),
                # Step 3
                json.dumps({
                    "pezzi": [
                        {
                            "label": "Verifica condizioni turno",
                            "ir_steps": [
                                "IF 50 = I AND 55 = I THEN",
                                "  P 2109",
                                "ENDIF",
                            ],
                            "ordine": 1,
                            "spiegazione": "Se turno attivo e festivo, chiama festività",
                        },
                        {
                            "label": "Calcolo presenza",
                            "ir_steps": [
                                "IF 251 = Z OR 271 = Z THEN",
                                "  SET 900 = '2'",
                                "  VF",
                                "ENDIF",
                                "RESET 71",
                                "RESET 72",
                                "RESET 73",
                                "SET 71 = 251",
                                "SET 72 = 271",
                                "CAMPO70 2",
                                "SET 800 = 73",
                            ],
                            "ordine": 2,
                            "spiegazione": "Calcolo ore presenza con CAMPO70",
                        },
                    ]
                }),
                # Step 4
                json.dumps({
                    "ir_steps_completi": [
                        "IF 50 = I AND 55 = I THEN",
                        "  P 2109",
                        "ENDIF",
                        "IF 251 = Z OR 271 = Z THEN",
                        "  SET 900 = '2'",
                        "  VF",
                        "ENDIF",
                        "RESET 71",
                        "RESET 72",
                        "RESET 73",
                        "SET 71 = 251",
                        "SET 72 = 271",
                        "CAMPO70 2",
                        "SET 800 = 73",
                        "K 601 A 3",
                        "K 602 A 3",
                        "R 120",
                        "VF",
                    ],
                    "formula_compact": (
                        "50UIE55UI(P2109"
                        "251UZO271UZ((900='2')VF"
                        "(!71!72!73)(71=251)(72=271)(70='2')(800=73)"
                        "(K601A'3')(K602A'3')R120"
                        "VF"
                    ),
                    "spiegazione": "Formula complessa: verifica turno + calcolo presenza + accumuli",
                }),
            ]

            result = generate_with_cot(
                "calcola ore presenza con turno festivo, "
                "se 50=I e 55=I chiama P2109, "
                "poi calcola 251-271 in 800 con CAMPO70 2"
            )
            assert result["success"] is True
            assert "2109" in result.get("formula", "") or "2109" in str(result.get("ir_steps", ""))

    def test_richiesta_semplice(self):
        """Anche richieste semplici devono passare la pipeline."""
        with patch("legacy_winsarp.core.ai.chain_of_thought.call_llm") as mock_llm:
            mock_llm.side_effect = [
                json.dumps({
                    "campi_input": [800],
                    "campi_output": [801],
                    "registri_k": [],
                    "flussi_chiamati": [],
                    "variabili_appoggio": [800, 801],
                    "spiegazione": "Copia valore",
                }),
                json.dumps({
                    "condizioni": [],
                    "condizioni_testuali": ["sempre vero"],
                    "spiegazione": "Nessuna condizione",
                }),
                json.dumps({
                    "pezzi": [{
                        "label": "Copia valore",
                        "ir_steps": [
                            "SET 801 = 800",
                            "VF",
                        ],
                        "ordine": 1,
                        "spiegazione": "Copia 800 in 801",
                    }]
                }),
                json.dumps({
                    "ir_steps_completi": ["SET 801 = 800", "VF"],
                    "formula_compact": "(801=800)VF",
                    "spiegazione": "Formula semplice copia valore",
                }),
            ]
            result = generate_with_cot("imposta 801 = 800")
            assert result["success"] is True
            assert "801" in result["formula"]


# ============================================================
# TEST INTEGRAZIONE CON WINSPARPBUILDER
# ============================================================


class TestWinSarpBuilderIntegration:
    """Verifica che _ir_to_compact usi correttamente WinSarpBuilder."""

    def test_uses_builder(self):
        engine = ChainOfThoughtEngine()
        steps = ["RESET 800", "SET 800 = '250'", "VF"]
        compact = engine._ir_to_compact(steps)
        assert compact is not None
        assert len(compact) > 0

    def test_fallback_on_builder_error(self):
        """Se WinSarpBuilder fallisce, deve usare mini_compact."""
        engine = ChainOfThoughtEngine()
        with patch("legacy_winsarp.core.formula_builder.WinSarpBuilder.build_compact") as mock_build:
            mock_build.side_effect = Exception("Builder fallito")
            steps = ["SET 800 = '100'", "VF"]
            compact = engine._ir_to_compact(steps)
            assert compact is not None
            assert "800" in compact
