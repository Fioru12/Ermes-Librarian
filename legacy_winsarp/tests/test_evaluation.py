"""Tests for core/evaluation module."""
import sys; sys.path.insert(0, ".")
from legacy_winsarp.core.evaluation.formula_validator import FormulaValidator
from legacy_winsarp.core.evaluation.semantic_evaluator import SemanticEvaluator, EvaluationScore


FORMULA130 = """21 U Z ( V04
( 504 = "SFN" )
21 > 4 (( 564 = 4 )( K21 S 4 )( !4 ) V05
( 564 = 21 )( K4 S 21 )( !21 )( 503 = "SF" )( 563 = 4 )( !4 )( K601 A 563 A 564 )( K604 A 563 A 564 )( K615 A 563 )( K616 A 564 )
R 200"""

FORMULA130_VF = FORMULA130 + "\nVF"


class TestFormulaValidator:
    def test_valid_formula130(self):
        r = FormulaValidator.validate_compact(FORMULA130)
        assert r.is_valid, f"Errors: {r.errors}"

    def test_valid_formula130_with_vf(self):
        r = FormulaValidator.validate_compact(FORMULA130_VF)
        assert r.is_valid

    def test_empty_formula(self):
        r = FormulaValidator.validate_compact("")
        assert not r.is_valid

    def test_vf_line(self):
        r = FormulaValidator.validate_compact("VF")
        assert r.is_valid

    def test_vu_line(self):
        r = FormulaValidator.validate_compact("VU")
        assert r.is_valid

    def test_v04_line(self):
        r = FormulaValidator.validate_compact("V04")
        assert r.is_valid

    def test_v05_line(self):
        r = FormulaValidator.validate_compact("V05")
        assert r.is_valid

    def test_r_line(self):
        r = FormulaValidator.validate_compact("R 200")
        assert r.is_valid

    def test_p_line(self):
        r = FormulaValidator.validate_compact("P 130")
        assert r.is_valid

    def test_set_line(self):
        r = FormulaValidator.validate_compact('( 504 = "SFN" )')
        assert r.is_valid

    def test_reset_line(self):
        r = FormulaValidator.validate_compact("( !4 )")
        assert r.is_valid

    def test_field_ref(self):
        r = FormulaValidator.validate_compact("( 504 )")
        assert r.is_valid

    def test_k_line(self):
        r = FormulaValidator.validate_compact("( K601 A 563 A 564 )")
        assert r.is_valid

    def test_comparison_line(self):
        r = FormulaValidator.validate_compact("21 > 4 (( 564 = 4 )( K21 S 4 )( !4 )")
        assert r.is_valid

    def test_invalid_line(self):
        r = FormulaValidator.validate_compact("FOOBAR")
        assert not r.is_valid

    def test_unbalanced_parens(self):
        r = FormulaValidator.validate_compact("( 504 = \"SFN\" ")
        assert not r.is_valid

    def test_invalid_r_line(self):
        r = FormulaValidator.validate_compact("R 200 X")
        assert not r.is_valid

    def test_missing_vf_warning(self):
        """VF mancante genera warning ma non errore."""
        r = FormulaValidator.validate_compact(FORMULA130)
        assert r.is_valid
        assert any("senza VF" in w for w in r.warnings)


class TestSemanticEvaluator:
    def test_exact_match(self):
        s = SemanticEvaluator.evaluate(FORMULA130, FORMULA130)
        assert s.exact_match
        assert s.score == 1.0

    def test_normalized_match(self):
        s = SemanticEvaluator.evaluate(
            FORMULA130 + "\nVF",
            FORMULA130 + "\n  VF  ",
        )
        assert s.normalized_match
        assert not s.exact_match

    def test_structural_match(self):
        g = FORMULA130.replace(" ", "").replace("\n", "")
        e = FORMULA130.replace(" ", "").replace("\n", "")
        s = SemanticEvaluator.evaluate(g, e)
        assert s.structural_match

    def test_no_match(self):
        s = SemanticEvaluator.evaluate("VF", FORMULA130)
        assert not s.exact_match
        assert s.score < 0.5

    def test_missing_line_detection(self):
        g = FORMULA130.replace("R 200", "VF").replace("VF", "").strip()
        if not g.endswith("VF"):
            g += "\nVF"
        s = SemanticEvaluator.evaluate(g, FORMULA130 + "\nVF")
        assert s.missing_lines

    def test_batch_evaluation(self):
        results = SemanticEvaluator.evaluate_batch(
            [FORMULA130, "VF"],
            [FORMULA130, "VU"],
        )
        assert len(results) == 2
        assert results[0].exact_match
        assert not results[1].exact_match

    def test_summary_empty(self):
        summary = SemanticEvaluator.summary([])
        assert summary["count"] == 0

    def test_summary(self):
        s1 = EvaluationScore(exact_match=True, line_accuracy=1.0, char_similarity=1.0, score=1.0)
        s2 = EvaluationScore(exact_match=False, line_accuracy=0.0, char_similarity=0.0, score=0.0)
        summary = SemanticEvaluator.summary([s1, s2])
        assert summary["count"] == 2
        assert summary["exact_matches"] == 1
        assert summary["avg_score"] == 0.5
