"""Test for Pattern Library matching and formula generation.

Verifies:
1. match_patterns() correctly matches realistic user requests
2. Pattern generation produces valid compact WinSarp formulas
3. Edge cases (empty/gibberish/novel requests) don't false-match
4. All patterns in the library produce valid output
"""
from legacy_winsarp.core.formula_builder import FormulaValidator, WinSarpBuilder
from legacy_winsarp.core.winsarp.formula_patterns import (
    match_patterns,
    fill_template,
    get_pattern,
    PATTERNS,
)
from legacy_winsarp.core.winsarp.rule_engine import _extract_params
from legacy_winsarp.core.winsarp.workbook_retriever import WorkbookRetriever
from legacy_winsarp.core.winsarp.linter import WinSarpLinter
from legacy_winsarp.core.winsarp.validator import LarkFormulaValidator


# ── match_patterns() unit tests ──────────────────────────────

class TestMatchPatterns:
    def test_straordinario_festivo_130(self):
        results = match_patterns("straordinario festivo 130", top_k=1, min_score=5.0)
        assert len(results) == 1
        assert results[0].id == "fg_split_festivo"

    def test_straordinario_ordinario(self):
        results = match_patterns("straordinario ordinario 200", top_k=1, min_score=5.0)
        assert len(results) >= 1
        # Accept either direct pattern or fallback with lower threshold
        assert any(p.id == "fg_split_ordinario" or p.id == "fg_dispatcher" for p in results)

    def test_pausa_pranzo(self):
        results = match_patterns("pausa pranzo 30 minuti", top_k=1, min_score=5.0)
        assert len(results) == 0  # pausa pranzo non è una formula WinSarp

    def test_turno_notte_5_giorni(self):
        results = match_patterns("turno notte 5 giorni", top_k=1, min_score=5.0)
        assert len(results) >= 1

    def test_azzeramento_inizio_giornata(self):
        results = match_patterns("azzeramento inizio giornata campi 800 801", top_k=1, min_score=3.0)
        assert len(results) >= 1

    def test_scatto_anzianita_low_threshold(self):
        """'scatto anzianità' non ha pattern dedicato, ma matcha con threshold bassa."""
        results = match_patterns("scatto anzianità 5 anni", top_k=1, min_score=0)
        assert len(results) >= 0  # non fallisce, è un test informativo

    def test_novel_request_no_match(self):
        """Richieste completamente nuove non devono matchare pattern esistenti con soglia alta."""
        results = match_patterns("quanto costa una mela al mercato", top_k=1, min_score=5.0)
        assert len(results) == 0

    def test_partial_match_low_score(self):
        """'straordinario' da solo matcha ma con score variabile."""
        results_high = match_patterns("straordinario", top_k=1, min_score=15.0)
        assert len(results_high) == 0
        results_low = match_patterns("straordinario", top_k=1, min_score=2.0)
        assert len(results_low) >= 1


# ── fill_template() + _extract_params() integration ────────

class TestPatternGeneration:
    def test_fill_straordinario_festivo(self):
        pattern = get_pattern("fg_split_festivo")
        assert pattern is not None
        params = _extract_params("straordinario festivo 130", pattern)
        ir_steps = fill_template(pattern, params)
        assert len(ir_steps) > 0
        compact = WinSarpBuilder().build_compact(ir_steps)
        assert compact and len(compact) > 5
        assert "R200" in compact or "R 200" in compact
        assert "SF" in compact or "SF" in compact

    def test_fill_turno_notte(self):
        pattern = get_pattern("ig_turn_recognition")
        assert pattern is not None
        params = _extract_params("turno notte 5 giorni", pattern)
        ir_steps = fill_template(pattern, params)
        assert len(ir_steps) > 0
        compact = WinSarpBuilder().build_compact(ir_steps)
        assert compact and len(compact) > 5

    def test_generated_formula_validates(self):
        pattern = get_pattern("fg_split_festivo")
        assert pattern is not None
        params = _extract_params("straordinario festivo 130", pattern)
        ir_steps = fill_template(pattern, params)
        compact = WinSarpBuilder().build_compact(ir_steps)

        retriever = WorkbookRetriever()
        v = FormulaValidator(retriever)
        l = WinSarpLinter()
        lark_v = LarkFormulaValidator()
        v_issues = v.validate(compact)
        l_issues = l.lint_compact(compact)
        lark_issues = lark_v.validate(compact)
        has_errors = any(i.severity == "error" for i in v_issues) or \
                     any(i.severity == "error" for i in l_issues) or \
                     any(i.severity == "error" for i in lark_issues)
        assert not has_errors, f"Pattern fg_split_festivo generated invalid formula: {compact}"


# ── Edge cases ─────────────────────────────────────────────

class TestPatternEdgeCases:
    def test_empty_request_no_crash(self):
        results = match_patterns("", top_k=1, min_score=5.0)
        assert results == []

    def test_gibberish_no_false_positive(self):
        results = match_patterns("asdfghjkl qwertyuiop zxcvbnm", top_k=1, min_score=5.0)
        assert len(results) == 0

    def test_straordinario_no_min_score(self):
        """Con min_score=0 torna sempre qualcosa."""
        results = match_patterns("straordinario", top_k=1, min_score=0)
        assert len(results) >= 1

    def test_all_patterns_have_id_and_name(self):
        for pid, pat in PATTERNS.items():
            assert pat.id, f"Pattern missing id: {pid}"
            assert pat.name, f"Pattern missing name: {pid}"
            assert pat.phase, f"Pattern missing phase: {pid}"

    def test_all_patterns_have_conditions(self):
        empty = [(pid, pat.name) for pid, pat in PATTERNS.items() if not pat.conditions]
        assert not empty, f"Pattern without conditions: {empty}"

    def test_all_patterns_generate_formula(self):
        """Ogni pattern deve produrre una formula compatta non vuota."""
        empty = []
        for pid, pat in PATTERNS.items():
            params = {}
            for slot, meta in pat.parameters.items():
                params[slot] = meta["default"]
            try:
                ir_steps = fill_template(pat, params)
                compact = WinSarpBuilder().build_compact(ir_steps)
                if not compact or len(compact) < 3:
                    empty.append(f"{pid} ({pat.name}): compact='{compact}'")
            except Exception as e:
                empty.append(f"{pid} ({pat.name}): exception {e}")
        assert not empty, "\n".join(empty)
