"""
test_semantic_validator.py
Test per il validatore semantico dichiarativo di SpecificaFormula.
"""

from legacy_winsarp.core.winsarp.semantic_validator import (
    SemanticIssue,
    valida_specifica_formula,
    valida_formula_compatta,
)


class TestSemanticIssue:
    """Test per la dataclass SemanticIssue."""

    def test_str_with_field(self):
        issue = SemanticIssue("error", "test message", field=800)
        s = str(issue)
        assert "ERROR" in s
        assert "campo 800" in s
        assert "test message" in s

    def test_str_without_field(self):
        issue = SemanticIssue("warning", "test warning")
        s = str(issue)
        assert "WARNING" in s
        assert "test warning" in s
        assert "campo" not in s


class TestValidateSpec:
    """Test per validate_spec su SpecificaFormula JSON."""

    def test_valid_spec(self):
        """Specifica valida non deve produrre errori."""
        spec = {
            "scopo_formula": "test",
            "fase_esecuzione": "DG",
            "logica_passo_passo": "test",
            "campi_input": [251, 271],
            "campi_output": [800],
            "condizioni_azioni": [
                {"condizione": "800 > 0", "azioni": {"801": "'1'"}}
            ],
            "valori_output": {"800": "'0'"},
            "flag_attivazione": "I",
        }
        issues = valida_specifica_formula(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0, f"Errors: {errors}"

    def test_readonly_field_write(self):
        """Scrittura su campo 3 (totale) deve dare errore."""
        spec = {
            "campi_output": [3],
            "condizioni_azioni": [{"condizione": None, "azioni": {"3": "'1'"}}],
        }
        issues = valida_specifica_formula(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1
        assert any("3" in str(e) for e in errors)

    def test_system_field_write(self):
        """Scrittura su campo sistema 7 deve dare errore."""
        spec = {
            "campi_output": [7],
        }
        issues = valida_specifica_formula(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1

    def test_day_flag_write(self):
        """Scrittura su flag giorno 50 deve dare errore."""
        spec = {
            "campi_output": [50],
        }
        issues = valida_specifica_formula(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1

    def test_unknown_field(self):
        """Campo sconosciuto deve dare warning, non errore."""
        spec = {
            "campi_input": [99999],
        }
        issues = valida_specifica_formula(spec)
        warnings = [i for i in issues if i.severity == "warning"]
        assert len(warnings) >= 1

    def test_appoggio_field_write(self):
        """Campo 800 deve essere scrivibile senza errori."""
        spec = {
            "campi_output": [800],
        }
        issues = valida_specifica_formula(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_invalid_flag(self):
        """flag_attivazione invalido."""
        spec = {"flag_attivazione": "X"}
        issues = valida_specifica_formula(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1

    def test_valid_flag_values(self):
        """flag_attivazione 'I' e 'Z' devono essere validi."""
        for f in ("I", "Z", None):
            spec = {"flag_attivazione": f}
            issues = valida_specifica_formula(spec)
            errors = [i for i in issues if i.severity == "error"]
            flag_errors = [e for e in errors if "flag_attivazione" in str(e)]
            assert len(flag_errors) == 0

    def test_invalid_fase(self):
        """Fase non standard deve dare warning."""
        spec = {"fase_esecuzione": "XX"}
        issues = valida_specifica_formula(spec)
        warnings = [i for i in issues if i.severity == "warning"]
        fase_warnings = [w for w in warnings if "fase_esecuzione" in str(w)]
        assert len(fase_warnings) >= 1


class TestValidateCondition:
    """Test per validazione delle condizioni logiche."""

    def test_valid_condition_time_field(self):
        """Condizione su campo tempo."""
        spec = {
            "condizioni_azioni": [
                {"condizione": "271 > 251", "azioni": {"800": "'1'"}}
            ],
        }
        issues = valida_specifica_formula(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_valid_flag_condition(self):
        """Condizione su flag con I/Z."""
        spec = {
            "condizioni_azioni": [
                {"condizione": "55 = I", "azioni": {"800": "'1'"}}
            ],
        }
        issues = valida_specifica_formula(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_condition_unknown_field(self):
        """Condizione su campo sconosciuto."""
        spec = {
            "condizioni_azioni": [
                {"condizione": "99999 > 0", "azioni": {"800": "'1'"}}
            ],
        }
        issues = valida_specifica_formula(spec)
        # Dovrebbe dare warning ma non errore bloccante
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_multi_condition_and(self):
        """Condizione composta con AND."""
        spec = {
            "condizioni_azioni": [
                {"condizione": "55 = I AND 50 = 1", "azioni": {"900": "'1'"}}
            ],
        }
        issues = valida_specifica_formula(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0


class TestValidateCompact:
    """Test per validate_compact su sintassi WinSarp già generata."""

    def test_valid_compact(self):
        """Formula compatta valida."""
        formula = "(!800)(801='250')VF"
        issues = valida_formula_compatta(formula)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_compact_with_k(self):
        """Formula con K accumulo."""
        formula = "(K601 A '3')VF"
        issues = valida_formula_compatta(formula)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_compact_with_reserved_field(self):
        """Reset su campo riservato."""
        formula = "(!3)VF"
        issues = valida_formula_compatta(formula)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1

    def test_compact_empty(self):
        """Formula vuota."""
        issues = valida_formula_compatta("")
        assert len([i for i in issues if i.severity == "error"]) == 0


class TestAllowedOps:
    """Test per la matrice operatore/tipo campo."""

    def test_time_field_ops(self):
        """Campi tempo supportano A, S, U."""
        from legacy_winsarp.core.winsarp.semantic_validator import FIELD_TYPE_TIMBRATURA
        from legacy_winsarp.core.winsarp.semantic_validator import SemanticFormulaValidator
        ops = SemanticFormulaValidator.ALLOWED_OPS_BY_TYPE[FIELD_TYPE_TIMBRATURA]
        assert "A" in ops
        assert "S" in ops
        assert "U" in ops

    def test_appoggio_ops(self):
        """Campi appoggio supportano tutti gli operatori."""
        from legacy_winsarp.core.winsarp.semantic_validator import FIELD_TYPE_APPOGGIO
        from legacy_winsarp.core.winsarp.semantic_validator import SemanticFormulaValidator
        ops = SemanticFormulaValidator.ALLOWED_OPS_BY_TYPE[FIELD_TYPE_APPOGGIO]
        assert "+" in ops
        assert "-" in ops
        assert "*" in ops

    def test_k_totale_ops(self):
        """K totali supportano solo A e S."""
        from legacy_winsarp.core.winsarp.semantic_validator import FIELD_TYPE_K_TOTALE
        from legacy_winsarp.core.winsarp.semantic_validator import SemanticFormulaValidator
        ops = SemanticFormulaValidator.ALLOWED_OPS_BY_TYPE[FIELD_TYPE_K_TOTALE]
        assert "A" in ops
        assert "S" in ops
        assert "+" not in ops
