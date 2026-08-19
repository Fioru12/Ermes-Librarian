"""
test_logic_test_generator.py
Test per il generatore automatico di test case da regole NL.
"""

from legacy_winsarp.core.winsarp.logic_test_generator import LogicTestGenerator, generate_tests_from_request


class TestSplitClauses:
    """Test per _split_clauses: divide regole in clausole condizione→conseguenza."""

    def test_simple_se(self):
        gen = LogicTestGenerator()
        clauses = gen._split_clauses("se ≤12 = 0, 13-15 = 15")
        assert len(clauses) == 2
        assert clauses[0]["conseguenza"] == "0"
        assert clauses[1]["conseguenza"] == "15"

    def test_with_altrimenti(self):
        gen = LogicTestGenerator()
        clauses = gen._split_clauses("se ≤12 = 0, altrimenti = 15")
        assert len(clauses) == 2
        assert clauses[1]["condizione"] is None  # else

    def test_single_clause(self):
        gen = LogicTestGenerator()
        clauses = gen._split_clauses("se pausa <= 0.30 → tutto OK")
        assert len(clauses) == 1

    def test_empty_text(self):
        gen = LogicTestGenerator()
        clauses = gen._split_clauses("")
        assert clauses == []


class TestExpandTestValues:
    """Test per _expand_test_values: range e operatori → valori di test."""

    def test_simple_range(self):
        gen = LogicTestGenerator()
        values = gen._expand_test_values("13-15", "=")
        assert "13" in values
        assert "14" in values
        assert "15" in values
        assert len(values) >= 3

    def test_less_equal(self):
        gen = LogicTestGenerator()
        values = gen._expand_test_values("≤12", "<=")
        assert "0" in values
        assert "12" in values
        assert len(values) >= 2

    def test_greater_equal(self):
        gen = LogicTestGenerator()
        values = gen._expand_test_values("6", ">=")
        assert "6" in values
        assert all(int(v) >= 6 for v in values)

    def test_single_value(self):
        gen = LogicTestGenerator()
        values = gen._expand_test_values("15", "=")
        assert values == ["15"]

    def test_tra_range(self):
        gen = LogicTestGenerator()
        values = gen._expand_test_values("tra 6 e 8", "=")
        assert "6" in values
        assert "7" in values
        assert "8" in values


class TestParseConsequence:
    """Test per _parse_consequence: conseguenze testuali → output dict."""

    def test_numeric_value(self):
        gen = LogicTestGenerator()
        result = gen._parse_consequence("0", 800)
        assert result == {"800": "0"}

    def test_value_15(self):
        gen = LogicTestGenerator()
        result = gen._parse_consequence("15", 801)
        assert result == {"801": "15"}

    def test_tutto_ok(self):
        gen = LogicTestGenerator()
        result = gen._parse_consequence("tutto OK", 800)
        assert result is None  # nessun output atteso

    def test_taglia_a(self):
        gen = LogicTestGenerator()
        result = gen._parse_consequence("taglia a 30", 800)
        assert result == {"800": "30"}

    def test_explicit_field(self):
        gen = LogicTestGenerator()
        result = gen._parse_consequence("800 = 0", 800)
        assert result == {"800": "0"}

    def test_imposta_valore(self):
        gen = LogicTestGenerator()
        result = gen._parse_consequence("imposta 15", 800)
        assert result == {"800": "15"}

    def test_flag_values(self):
        gen = LogicTestGenerator()
        r1 = gen._parse_consequence("I", 900)
        assert r1 == {"900": "I"}
        r2 = gen._parse_consequence("Z", 900)
        assert r2 == {"900": "Z"}


class TestGenerateFromNL:
    """Test end-to-end: NL → test case strutturati."""

    def test_rule_pausa_base(self):
        """Regola pause base: se ≤12 → 0, 13-15 → 15"""
        tests = generate_tests_from_request("se ≤12 = 0, 13-15 = 15")
        assert len(tests) >= 2
        # Verifica struttura
        for t in tests:
            assert "input" in t
            assert "output" in t

    def test_rule_with_field_context(self):
        """Regola con campo esplicito: se pausa ≤ 30 → OK"""
        field_ctx = {"pausa": 800}
        tests = generate_tests_from_request("se pausa ≤ 30 = 0, altrimenti = 30", field_ctx)
        assert len(tests) >= 2
        # else clause
        else_tests = [t for t in tests if t["output"].get("800") == "30"]
        assert len(else_tests) >= 1

    def test_rule_altrimenti(self):
        """Regola con else"""
        tests = generate_tests_from_request("se ≤12 = 0, altrimenti = 15")
        assert len(tests) >= 2
        # else test dovrebbe avere input alto
        else_tests = [t for t in tests if t["output"].get("800") == "15"]
        assert len(else_tests) >= 1

    def test_rule_range_explicit(self):
        """Regola con range esplicito"""
        tests = generate_tests_from_request("se 13-15 = 15")
        assert len(tests) >= 3
        for t in tests:
            val = int(list(t["input"].values())[0])
            assert 13 <= val <= 15

    def test_no_rules_empty(self):
        """Testo senza regole → lista vuota"""
        tests = generate_tests_from_request("nessuna regola qui")
        assert tests == []

    def test_multiple_conditions(self):
        """Regola multi-condizione"""
        tests = generate_tests_from_request("se <= 0 → I, 1-5 → Z, >5 → I")
        assert len(tests) >= 3

    def test_parse_num(self):
        assert LogicTestGenerator._parse_num("12") == 12
        assert LogicTestGenerator._parse_num("12.5") == 12
        assert LogicTestGenerator._parse_num("0") == 0


class TestNormalizeVal:
    """Test per _normalize_val."""

    def test_boolean_values(self):
        gen = LogicTestGenerator()
        assert gen._normalize_val("i") == "I"
        assert gen._normalize_val("vero") == "I"
        assert gen._normalize_val("z") == "Z"
        assert gen._normalize_val("falso") == "Z"

    def test_numeric(self):
        gen = LogicTestGenerator()
        assert gen._normalize_val("15") == "15"
        assert gen._normalize_val("'15'") == "15"
        assert gen._normalize_val('"15"') == "15"


class TestEdgeCases:
    """Test casi limite."""

    def test_empty_rule(self):
        tests = generate_tests_from_request("")
        assert tests == []

    def test_none_field_context(self):
        tests = generate_tests_from_request("se ≤12 = 0", None)
        assert len(tests) >= 1

    def test_large_range(self):
        """Range grande deve produrre valori spaziati"""
        gen = LogicTestGenerator()
        values = gen._expand_test_values("1-100", "=")
        assert len(values) >= 3  # almeno edge + mid
        assert "1" in values
        assert "100" in values

    def test_threshold_night_crossing(self):
        """Superamento mezzanotte: valore 24+"""
        gen = LogicTestGenerator()
        values = gen._expand_test_values(">=24", ">=")
        assert "24" in values
