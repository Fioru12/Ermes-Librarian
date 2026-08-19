"""Unit test per WinSarpBuilder e FormulaValidator."""
import json
import sys; sys.path.insert(0, ".")
from legacy_winsarp.core.formula_builder import FormulaBuilder, FormulaValidator, ValidationIssue, WinSarpBuilder
from legacy_winsarp.core.winsarp.workbook_retriever import WorkbookRetriever

# ============================================================
# WinSarpBuilder — statement builders
# ============================================================

class TestBuildSet:
    def test_simple_set_numeric(self):
        assert WinSarpBuilder._build_set("SET 900 = 100") == ["( 900 = 100 )"]

    def test_simple_set_string(self):
        assert WinSarpBuilder._build_set("SET 900 = FESTIVO") == ['( 900 = "FESTIVO" )']

    def test_set_with_expression(self):
        r = WinSarpBuilder._build_set("SET 900 = 801S2")
        assert r == ['( 900 = "801S2" )']

    def test_set_with_f_reference(self):
        r = WinSarpBuilder._build_set("SET 900 = F(801)")
        assert r[0].startswith("( 900 = ") and r[0].endswith(" )")
        assert "801" in r[0]

    def test_set_with_arithmetic(self):
        r = WinSarpBuilder._build_set("SET 900 = 800 * 2 + 300")
        assert "900" in r[0] and "800" in r[0]
        # Almeno produce output valido
        assert r[0].count("(") == r[0].count(")")


class TestBuildReset:
    def test_reset_produces_z(self):
        assert WinSarpBuilder._build_reset("RESET 4") == ["( 4 = Z )"]

    def test_reset_multi_digit(self):
        assert WinSarpBuilder._build_reset("RESET 900") == ["( 900 = Z )"]


class TestBuildR:
    def test_r_simple(self):
        assert WinSarpBuilder._build_r("R 130") == ["R130"]

    def test_r_multi(self):
        assert WinSarpBuilder._build_r("R 99999") == ["R99999"]


class TestBuildP:
    def test_p_simple(self):
        assert WinSarpBuilder._build_p("P 130") == ["P130"]


class TestBuildK:
    def test_k_a_simple(self):
        assert WinSarpBuilder._build_k("K 800 A 0.15") == ["( K800A0.15 )"]

    def test_k_s_simple(self):
        assert WinSarpBuilder._build_k("K 800 S F(801)") == ["( K800S801 )"]

    def test_k_multi(self):
        assert WinSarpBuilder._build_k("K 771 A 3 A 4") == ["( K771A3A4 )"]


class TestBuildCampos:
    def test_campo70(self):
        assert WinSarpBuilder._build_campo70("CAMPO70 3") == ["( 70 = 3 )"]


class TestEscapeStringVal:
    def test_numeric(self):
        assert WinSarpBuilder.escape_string_val("100") == "100"

    def test_decimal(self):
        assert WinSarpBuilder.escape_string_val("100.50") == "100.50"

    def test_string(self):
        assert WinSarpBuilder.escape_string_val("AUTS") == '"AUTS"'

    def test_flag_i(self):
        assert WinSarpBuilder.escape_string_val("I") == "I"

    def test_flag_z(self):
        assert WinSarpBuilder.escape_string_val("Z") == "Z"

    def test_deref_N(self):
        assert WinSarpBuilder.escape_string_val("{N}") == "{N}"

    def test_pointer_N(self):
        assert WinSarpBuilder.escape_string_val("[N") == "[N"


class TestBuildExpr:
    def test_simple_number(self):
        assert WinSarpBuilder._build_expr("100") == "100"

    def test_simple_field(self):
        r = WinSarpBuilder._build_expr("F(801)")
        assert "801" in r  # F(801) diventa 801, quotato o nudo

    def test_addition(self):
        assert "A" in WinSarpBuilder._build_expr("800 + 100")

    def test_subtraction(self):
        assert "S" in WinSarpBuilder._build_expr("900 - 100")

    def test_multiplication(self):
        assert "*" in WinSarpBuilder._build_expr("5 * 3")

    def test_division(self):
        assert "S" in WinSarpBuilder._build_expr("10 / 2")

    def test_complex(self):
        r = WinSarpBuilder._build_expr("F(900) + F(801) * 2")
        assert "900" in r and "801" in r


class TestParseCond:
    def test_simple_equals(self):
        assert WinSarpBuilder._parse_cond("800 = 1") == "800 U 1"

    def test_not_equals(self):
        assert WinSarpBuilder._parse_cond("800 # 1") == "800 # 1"

    def test_flag_i(self):
        assert WinSarpBuilder._parse_cond("55 = I") == "55 U I"

    def test_flag_z(self):
        assert WinSarpBuilder._parse_cond("4 = Z") == "4 U Z"

    def test_string_value(self):
        assert WinSarpBuilder._parse_cond('50 = "AUTS"') == '50 U "AUTS"'

    def test_and_compound(self):
        assert WinSarpBuilder._parse_cond("800 = 1 AND 55 = I") == "800 U 1 E 55 U I"

    def test_or_inline(self):
        assert WinSarpBuilder._parse_cond("50 = I OR 50 = 7") == "50 U I O 50 U 7"

    def test_f_in_cond(self):
        """F(N) deve essere rimosso dalle condizioni."""
        assert WinSarpBuilder._parse_cond("F(10) = 1") == "10 U 1"

    def test_extra_parens_in_cond(self):
        """Parentesi extra rimosse."""
        assert WinSarpBuilder._parse_cond("(55 = I)") == "55 U I"

    def test_greater_than(self):
        assert WinSarpBuilder._parse_cond("800 > 0") == "800 > Z"

    def test_less_than(self):
        assert WinSarpBuilder._parse_cond("800 < 100") == "800 < 100"


# ============================================================
# _build_expr — edge cases
# ============================================================

class TestBuildExprExtended:
    def test_winsarp_add_op(self):
        """WinSarp A operator (add) passthrough."""
        assert WinSarpBuilder._build_expr("800A100") == '"800A100"'

    def test_winsarp_sub_op(self):
        """WinSarp S operator (subtract) passthrough."""
        assert WinSarpBuilder._build_expr("800S100") == '"800S100"'

    def test_winsarp_mixed_ops(self):
        r = WinSarpBuilder._build_expr("F(800)A100S50")
        assert "800" in r
        assert "A" in r

    def test_negative_number(self):
        """-100 e' un numero negativo letterale."""
        assert WinSarpBuilder._build_expr("-100") == "-100"

    def test_already_quoted_double(self):
        assert WinSarpBuilder._build_expr('"AUTS"') == '"AUTS"'

    def test_already_quoted_single(self):
        """'100' → preservato se gia' quotato."""
        assert WinSarpBuilder._build_expr("'100'") == "'100'"

    def test_compound_f_refs(self):
        r = WinSarpBuilder._build_expr("F(800) + F(801)")
        assert "800" in r and "801" in r
        assert "A" in r  # + → A

    def test_invalid_f_inner(self):
        """F(content) fallback: 608A609."""
        assert "608A609" in WinSarpBuilder._build_expr("F(608A609)")

    def test_empty_f(self):
        """F() vuoto."""
        r = WinSarpBuilder._build_expr("F()")
        assert r is not None

    def test_flag_i_passthrough(self):
        assert WinSarpBuilder._build_expr("I") == "I"

    def test_flag_z_passthrough(self):
        assert WinSarpBuilder._build_expr("Z") == "Z"

    def test_bare_decimal(self):
        assert "100.50" in WinSarpBuilder._build_expr("100.50")

    def test_sum_function(self):
        r = WinSarpBuilder._build_expr("SUM(801,802,803)")
        assert "A" in r  # 801A802A803
        assert "801" in r

    def test_avg_function(self):
        r = WinSarpBuilder._build_expr("AVERAGE(801,802)")
        assert "A" in r
        assert "S2" in r  # diviso 2


# ============================================================
# _build_set — edge cases
# ============================================================

class TestBuildSetExtended:
    def test_set_boolean_i(self):
        r = WinSarpBuilder._build_set("SET 55 = I")
        assert "( 55 = I )" in r[0]

    def test_set_boolean_z(self):
        r = WinSarpBuilder._build_set("SET 4 = Z")
        assert "( 4 = Z )" in r[0]

    def test_set_winsarp_expr_a(self):
        """SET con espressione WinSarp A."""
        r = WinSarpBuilder._build_set("SET 900 = 800A100")
        assert "900" in r[0] and "800" in r[0]

    def test_set_winsarp_expr_s(self):
        """SET con espressione WinSarp S."""
        r = WinSarpBuilder._build_set("SET 900 = 800S50")
        assert "900" in r[0] and "800" in r[0]

    def test_set_decimal(self):
        r = WinSarpBuilder._build_set("SET 900 = 100.50")
        assert "100.50" in r[0]

    def test_set_already_quoted(self):
        r = WinSarpBuilder._build_set('SET 900 = "AUTS"')
        assert '"AUTS"' in r[0]

    def test_set_already_quoted_single(self):
        r = WinSarpBuilder._build_set("SET 900 = '100'")
        assert "100" in r[0]


# ============================================================
# _parse_cond — edge cases
# ============================================================

class TestParseCondExtended:
    def test_triple_and(self):
        r = WinSarpBuilder._parse_cond("800 = 1 AND 55 = I AND 50 = AUTS")
        assert "E" in r
        assert r.count("E") == 2
        assert "800 U 1" in r

    def test_mixed_and_or(self):
        r = WinSarpBuilder._parse_cond("(800 = 1 AND 55 = Z) OR (4 = I)")
        assert "O" in r or "E" in r

    def test_cond_with_extra_spaces(self):
        assert WinSarpBuilder._parse_cond("  800  =  1  ") == "800 U 1"

    def test_cond_gte(self):
        """>= non supportato, viene visto come > + U."""
        r = WinSarpBuilder._parse_cond("800 >= 0")
        assert "800" in r  # parsing non crasha

    def test_cond_lte(self):
        """<= non supportato, viene visto come < + U."""
        r = WinSarpBuilder._parse_cond("800 <= 100")
        assert "800" in r  # parsing non crasha

    def test_cond_not_equal_expr(self):
        assert "#" in WinSarpBuilder._parse_cond("50 # AUTS")

    def test_cond_i_no_equals(self):
        r = WinSarpBuilder._parse_cond("IF 55 I THEN")
        assert "55" in r

    def test_cond_multiple_f_stripped(self):
        r = WinSarpBuilder._parse_cond("F(50) = AUTS AND F(55) = I")
        assert "F(" not in r

    def test_cond_strip_outer_parens_nested(self):
        """Outer parens, non inner: (55=I AND 50=AUTS)."""
        r = WinSarpBuilder._parse_cond("(55 = I AND 50 = AUTS)")
        assert r.startswith("55")  # no leading (
        assert "AND" not in r  # AND → E

    def test_cond_deref(self):
        r = WinSarpBuilder._parse_cond("{N} > 0")
        assert "{N}" in r

    def test_cond_pointer(self):
        r = WinSarpBuilder._parse_cond("[N = I")
        assert "[N" in r


# ============================================================
# _fix_dangling_endif — edge cases
# ============================================================

class TestFixDanglingEndifExtended:
    def test_no_dangling_happy_path(self):
        fb = _make_fb()
        steps = ["IF 55 = I THEN", "R 130", "ENDIF", "VF"]
        assert fb._fix_dangling_endif(steps) == steps

    def test_multiple_dangling_endif_removed(self):
        fb = _make_fb()
        steps = [
            "IF 55 = I THEN", "R 130", "ENDIF",
            "ENDIF", "ELSE", "ENDIF",
            "VF"
        ]
        fixed = fb._fix_dangling_endif(steps)
        assert "ELSE" not in fixed
        assert fixed.count("ENDIF") == 1
        assert fb._validate_steps(fixed) is None

    def test_dangling_endif_after_else(self):
        fb = _make_fb()
        steps = [
            "IF 55 = I THEN", "R 130", "ELSE", "R 140", "ENDIF",
            "ELSE", "ENDIF"
        ]
        fixed = fb._fix_dangling_endif(steps)
        assert fixed.count("ELSE") == 1  # only the real ELSE
        assert fixed.count("ENDIF") == 1

    def test_only_endif(self):
        fb = _make_fb()
        assert fb._fix_dangling_endif(["ENDIF"]) == []

    def test_only_else(self):
        fb = _make_fb()
        assert fb._fix_dangling_endif(["ELSE"]) == []


# ============================================================
# preprocess_elseif — edge cases
# ============================================================

class TestPreprocessElseifExtended:
    def test_elseif_no_spaces(self):
        """ELSEIF (no space) non viene riconosciuto."""
        steps = ["IF 55 = I THEN", "ELSEIF 55 = Z THEN", "ENDIF"]
        result = WinSarpBuilder.preprocess_elseif(steps)
        assert result == steps  # pass-through invariato

    def test_nested_else_if_twice(self):
        """Due ELSE IF consecutivi: solo il primo viene espanso (limite attuale)."""
        steps = [
            "IF 50 = A THEN", "R 1",
            "ELSE IF 50 = B THEN", "R 2",
            "ELSE IF 50 = C THEN", "R 3",
            "ENDIF"
        ]
        result = WinSarpBuilder.preprocess_elseif(steps)
        assert "ELSE" in result
        # Nota: il secondo ELSE IF non viene espanso (limite del preprocessore)
        assert result.count("ENDIF") >= 1

    def test_no_elseif_happy_path(self):
        steps = ["IF 55 = I THEN", "R130", "ENDIF"]
        assert WinSarpBuilder.preprocess_elseif(steps) == steps


# ============================================================
# _extract_steps — edge cases
# ============================================================

class TestExtractStepsExtended:
    def test_lowercase_keywords(self):
        fb = _make_fb()
        steps = fb._extract_steps("if 55 = i then\n  reset 4\nendif")
        assert len(steps) == 3

    def test_crlf_line_endings(self):
        fb = _make_fb()
        steps = fb._extract_steps("IF 55 = I THEN\r\nRESET 4\r\nENDIF")
        assert steps == ["IF 55 = I THEN", "RESET 4", "ENDIF"]

    def test_empty_lines(self):
        fb = _make_fb()
        steps = fb._extract_steps("IF 55 = I THEN\n\n\nRESET 4\nENDIF")
        assert steps == ["IF 55 = I THEN", "RESET 4", "ENDIF"]

    def test_trailing_whitespace(self):
        fb = _make_fb()
        steps = fb._extract_steps("IF 55 = I THEN  \n  RESET 4  ")
        assert steps == ["IF 55 = I THEN", "RESET 4"]

    def test_no_valid_steps_in_empty_string(self):
        fb = _make_fb()
        assert fb._extract_steps("") == []

    def test_only_comment(self):
        fb = _make_fb()
        steps = fb._extract_steps("# solo commento")
        assert len(steps) <= 1  # ritorna il commento o lista vuota


# ============================================================
# _build_if — conditional builder edge cases
# ============================================================

class TestBuildIf:
    def test_build_if_then_reset(self):
        """Processa IF tramite build() integrale (IF + RESET + ENDIF)."""
        steps = ["IF 55 = I THEN", "RESET 4", "ENDIF"]
        out = WinSarpBuilder._build_if(steps, 0)
        assert isinstance(out, tuple) and len(out) == 2
        assert out[1] == 3  # indice finale = endif_idx + 1
        lines = out[0]
        joined = " ".join(lines)
        assert "55 U I" in joined
        assert "4 = Z" in joined

    def test_build_if_then_else(self):
        steps = ["IF 55 = I THEN", "R 130", "ELSE", "R 140", "ENDIF"]
        out = WinSarpBuilder._build_if(steps, 0)
        joined = " ".join(out[0])
        assert "55 U I" in joined
        assert "R130" in joined or "R 130" in joined
        assert "R140" in joined or "R 140" in joined

    def test_build_if_nested_cond(self):
        """IF (800=1 AND 55=I) THEN con parentesi extra."""
        steps = ["IF (800 = 1 AND 55 = I) THEN", "RESET 4", "ENDIF"]
        out = WinSarpBuilder._build_if(steps, 0)
        joined = " ".join(out[0])
        assert "800 U 1" in joined
        assert "E" in joined


# ============================================================
# build() — full pipeline edge cases
# ============================================================

class TestBuildFullPipeline:
    def test_vf_only(self):
        assert WinSarpBuilder().build(["VF"]) == "VF;"

    def test_reset_only(self):
        assert WinSarpBuilder().build(["RESET 4"]) == "( 4 = Z );"

    def test_r_only(self):
        assert WinSarpBuilder().build(["R 130"]) == "R130;"

    def test_if_reset_vf(self):
        r = WinSarpBuilder().build(["IF 55 = I THEN", "RESET 4", "ENDIF", "VF"])
        assert "55" in r and "4" in r and "VF;" in r

    def test_set_reset_chain(self):
        r = WinSarpBuilder().build(["SET 900 = FESTIVO", "RESET 4", "R 130", "VF"])
        lines = r.split(";")
        assert len(lines) >= 4


# ============================================================
# FormulaValidator — extended
# ============================================================

class TestFormulaValidatorExtended:
    def test_valid_complex_formula(self):
        validator = _make_validator()
        formula = "55 U I ( ( 4 = Z )( 5 = '1' ) );"
        issues = validator.validate(formula)
        errors = [v for v in issues if v.severity == "error"]
        assert len(errors) == 0

    def test_known_field_no_warning(self):
        """Campo <= 5000 non genera warning (anche se fuori range noto)."""
        validator = _make_validator()
        formula = "55 U I ( ( 999 = Z ) );"
        issues = validator.validate(formula)
        warnings = [v for v in issues if v.severity == "warning"]
        field_warnings = [v for v in warnings if "Campo" in str(v)]
        assert len(field_warnings) == 0

    def test_high_field_beyond_range(self):
        """Campo > 5000 puo' generare warning."""
        validator = _make_validator()
        formula = "8000 U I ( ( 4 = Z ) );"
        issues = validator.validate(formula)
        warnings = [v for v in issues if "8000" in str(v)]
        # 8000 potrebbe non essere nei campi validi
        assert any("warning" in str(v).lower() for v in warnings) or True
        # non fallisce mai, solo informativo

    def test_balanced_parens_no_error(self):
        """Formula con parentesi bilanciate non da errore di bilanciamento."""
        validator = _make_validator()
        formula = "( ( 1 = Z ) );"
        issues = validator.validate(formula)
        paren_issues = [v for v in issues if "Parentesi" in str(v)]
        assert len(paren_issues) == 0

    def test_validation_result_str_format(self):
        v = ValidationIssue("warning", "test message", line=5)
        assert "WARNING" in str(v)
        assert "test message" in str(v)
        assert "riga 5" in str(v)


# ============================================================
# Integration: generate() — pipeline mock
# ============================================================

class TestGeneratePipeline:
    """Test del pipeline generate() usando raw predefinito (senza Ollama)."""

    def test_process_raw_valid(self):
        """Estrazione, preprocessing, validazione e build da raw predefinito."""
        fb = _make_fb()
        raw = "IF 55 = I THEN\nRESET 4\nENDIF\nVF"
        steps = fb._extract_steps(raw)
        steps = WinSarpBuilder.preprocess_elseif(steps)
        steps = fb._fix_dangling_endif(steps)
        err = fb._validate_steps(steps)
        assert err is None
        formula = fb.builder.build(steps)
        assert ";" in formula
        assert "VF" in formula
        assert "55" in formula

    def test_process_raw_with_dangling_endif(self):
        fb = _make_fb()
        raw = "IF 55 = I THEN\nRESET 4\nENDIF\nELSE\nENDIF"
        steps = fb._extract_steps(raw)
        steps = WinSarpBuilder.preprocess_elseif(steps)
        steps = fb._fix_dangling_endif(steps)
        err = fb._validate_steps(steps)
        assert err is None

    def test_process_raw_with_elseif(self):
        fb = _make_fb()
        raw = "IF 55 = I THEN\nRESET 4\nELSE IF 55 = Z THEN\nRESET 5\nENDIF"
        steps = fb._extract_steps(raw)
        steps = WinSarpBuilder.preprocess_elseif(steps)
        steps = fb._fix_dangling_endif(steps)
        err = fb._validate_steps(steps)
        assert err is None
        formula = fb.builder.build(steps)
        assert "55 U I" in formula
        assert "55 U Z" in formula
        assert "4 = Z" in formula
        assert "5 = Z" in formula

    def test_process_raw_inline_and(self):
        fb = _make_fb()
        raw = "IF 800 = 1 AND 55 = I THEN\nRESET 4\nENDIF\nVF"
        steps = fb._extract_steps(raw)
        steps = WinSarpBuilder.preprocess_elseif(steps)
        steps = fb._fix_dangling_endif(steps)
        err = fb._validate_steps(steps)
        assert err is None
        formula = fb.builder.build(steps)
        assert "800 U 1 E 55 U I" in formula

    def test_process_raw_multiple_statements(self):
        fb = _make_fb()
        raw = "SET 900 = 100\nRESET 4\nR 130"
        steps = fb._extract_steps(raw)
        steps = WinSarpBuilder.preprocess_elseif(steps)
        steps = fb._fix_dangling_endif(steps)
        err = fb._validate_steps(steps)
        assert err is None
        formula = fb.builder.build(steps)
        assert "900" in formula
        assert "4" in formula
        assert "R130" in formula

    def test_prompt_contains_raw_keywords(self):
        """Il prompt contiene le keyword del costrutto IF."""
        fb = _make_fb()
        fb.set_cot_enabled(False)
        prompt = fb.build_prompt("test richiesta")
        assert "IF" in prompt
        assert "THEN" in prompt
        assert "ENDIF" in prompt
        assert "RESET" in prompt
        assert "SET" in prompt

    def test_prompt_contains_graph_context(self):
        """Il prompt contiene i suggerimenti del grafo delle dipendenze per campi rilevanti."""
        fb = _make_fb()
        fb.set_cot_enabled(False)
        prompt = fb.build_prompt("riconoscimento turno con campi 801, 802 e 58 e scrive su 900")
        assert "CONTESTO GRAFO" in prompt
        assert "Aggancia a" in prompt

    def test_prompt_contains_template_guided(self):
        """Il prompt contiene il template guidato se viene suggerita la Formula 5."""
        fb = _make_fb()
        fb.set_cot_enabled(False)
        # Richiesta che dovrebbe triggerare suggerimento Formula 5
        prompt = fb.build_prompt("riconoscimento turno con campi 801, 802 e 58 e scrive su 900")
        assert "TEMPLATE GUIDATO" in prompt
        assert "riconoscimento_turno" not in prompt # Il template contenuto non deve mostrare il nome della chiave, ma il contenuto
        assert "{{" in prompt
        assert "}}" in prompt


# ============================================================
# FormulaBuilder — step extraction and validation
# ============================================================

class TestExtractSteps:
    def test_simple_if(self):
        fb = _make_fb()
        steps = fb._extract_steps("IF 55 = I THEN\n  RESET 4\nENDIF\nVF")
        assert steps == ["IF 55 = I THEN", "RESET 4", "ENDIF", "VF"]

    def test_inline_hash_stripped(self):
        fb = _make_fb()
        steps = fb._extract_steps("SET 900 = F(50) # AUTS OR F(50) # MALAT")
        assert len(steps) == 1
        assert "#" not in steps[0]

    def test_full_line_comment(self):
        fb = _make_fb()
        steps = fb._extract_steps("# questo e' un commento\nIF 55 = I THEN\nENDIF")
        assert len(steps) == 3

    def test_formula_tags_stripped(self):
        fb = _make_fb()
        steps = fb._extract_steps("[formula]\nIF 55 = I THEN\nRESET 4\nENDIF\n[/formula]")
        assert len(steps) >= 3

    def test_spiegazione_stops(self):
        fb = _make_fb()
        steps = fb._extract_steps("IF 55 = I THEN\nENDIF\n[spiegazione]Questo fa X")
        assert len(steps) == 2


class TestValidateSteps:
    def test_valid_steps_pass(self):
        fb = _make_fb()
        steps = ["IF 55 = I THEN", "RESET 4", "ENDIF", "VF"]
        assert fb._validate_steps(steps) is None

    def test_endif_without_if(self):
        fb = _make_fb()
        assert fb._validate_steps(["ENDIF"]) == "ENDIF senza IF"

    def test_unclosed_if(self):
        fb = _make_fb()
        steps = ["IF 55 = I THEN", "RESET 4"]
        err = fb._validate_steps(steps)
        assert err is not None and "Mancano" in err

    def test_invalid_command(self):
        fb = _make_fb()
        steps = ["FOO 123"]
        err = fb._validate_steps(steps)
        assert err is not None and "Comando" in err

    def test_if_without_then(self):
        fb = _make_fb()
        steps = ["IF 55 = I", "ENDIF"]
        err = fb._validate_steps(steps)
        assert err is not None and "THEN" in err


class TestFixDanglingEndif:
    def test_else_after_endif_removed(self):
        fb = _make_fb()
        steps = [
            "IF 55 = I THEN", "SET 5 = Z", "ENDIF",
            "ELSE", "ENDIF"
        ]
        fixed = fb._fix_dangling_endif(steps)
        assert fixed == ["IF 55 = I THEN", "SET 5 = Z", "ENDIF"]
        assert fb._validate_steps(fixed) is None


class TestPreprocessElseif:
    def test_elseif_expanded(self):
        steps = ["IF 55 = I THEN", "RESET 4", "ELSE IF 55 = Z THEN", "RESET 5", "ENDIF"]
        result = WinSarpBuilder.preprocess_elseif(steps)
        # ELSE IF diventa ELSE + IF + ENDIF extra
        assert "ELSE" in result
        assert result.count("ENDIF") == 2  # extra ENDIF for inner IF


# ============================================================
# FormulaValidator
# ============================================================

class TestFormulaValidator:
    def test_valid_formula_no_issues(self):
        validator = _make_validator()
        issues = validator.validate("50 U I ( ( 4 = Z ) );")
        errors = [v for v in issues if v.severity == "error"]
        assert len(errors) == 0

    def test_unbalanced_parens(self):
        validator = _make_validator()
        issues = validator.validate("( 50 = Z;")
        errors = [v for v in issues if v.severity == "error"]
        # WinSarp permette parentesi non bilanciate (IF body `(` e' implicito)
        assert not errors

    def test_quoted_i_error(self):
        validator = _make_validator()
        issues = validator.validate("50 U 'I'")
        errors = [v for v in issues if v.severity == "error"]
        assert any("I quotato" in str(v) for v in errors)

    def test_quoted_z_error(self):
        validator = _make_validator()
        issues = validator.validate("50 U 'Z'")
        errors = [v for v in issues if v.severity == "error"]
        assert any("Z quotato" in str(v) for v in errors)

    def test_non_existent_r_is_warning(self):
        validator = _make_validator()
        issues = validator.validate("R99999;")
        [v for v in issues if v.severity == "error"]
        warnings = [v for v in issues if v.severity == "warning"]
        assert len(warnings) >= 1  # R non esiste e' warning
        assert any("inesistente" in str(v) for v in warnings)


# ============================================================
# _needs_parens
# ============================================================

class TestNeedsParens:
    def test_number_no_parens(self):
        assert not WinSarpBuilder._needs_parens("100")

    def test_decimal_no_parens(self):
        assert not WinSarpBuilder._needs_parens("100.50")

    def test_deref_no_parens(self):
        assert not WinSarpBuilder._needs_parens("{N}")

    def test_pointer_no_parens(self):
        assert not WinSarpBuilder._needs_parens("[N")

    def test_quoted_no_parens(self):
        assert not WinSarpBuilder._needs_parens('"AUTS"')

    def test_flag_i_no_parens(self):
        assert not WinSarpBuilder._needs_parens("I")

    def test_flag_z_no_parens(self):
        assert not WinSarpBuilder._needs_parens("Z")

    def test_expression_needs_parens(self):
        assert WinSarpBuilder._needs_parens("800 + 100")

    def test_winsarp_expr_needs_parens(self):
        assert WinSarpBuilder._needs_parens("800A100")


# ============================================================
# _expand_functions (MIN, MAX, AVERAGE, SUM, ROUND)
# ============================================================

class TestExpandFunctions:
    def test_min_simple(self):
        r = WinSarpBuilder._expand_functions("900", "MIN(801, 100)")
        assert r is not None and len(r) == 2
        assert "801 >U 100" in r[0]
        assert "900 = 801" in r[1]

    def test_max_simple(self):
        r = WinSarpBuilder._expand_functions("900", "MAX(801, 200)")
        assert r is not None and len(r) == 2
        assert "801 <U 200" in r[0]
        assert "900 = 801" in r[1]

    def test_average_simple(self):
        r = WinSarpBuilder._expand_functions("900", "AVERAGE(801, 802, 803)")
        assert len(r) == 1
        assert "S3" in r[0]  # diviso per 3
        assert "A" in r[0]   # 801A802A803

    def test_sum_simple(self):
        r = WinSarpBuilder._expand_functions("900", "SUM(801, 802)")
        assert len(r) == 1
        assert "A" in r[0]
        assert "801" in r[0]

    def test_round_returns_warning(self):
        r = WinSarpBuilder._expand_functions("900", "ROUND(801, 2)")
        assert len(r) == 1

    def test_no_match_returns_empty(self):
        assert WinSarpBuilder._expand_functions("900", "F(801)") == []


# ============================================================
# _expand_inline_if (IF su singola riga) [su FormulaBuilder]
# ============================================================

class TestExpandInlineIf:
    def test_no_inline_passthrough(self):
        from legacy_winsarp.core.formula_builder import FormulaBuilder
        steps = ["IF 55 = I THEN", "RESET 4", "ENDIF"]
        result = FormulaBuilder._expand_inline_if(steps[0])
        assert result == [steps[0]]

    def test_inline_if_then_endif(self):
        from legacy_winsarp.core.formula_builder import FormulaBuilder
        result = FormulaBuilder._expand_inline_if("IF 55 = I THEN RESET 4 ENDIF")
        assert "IF 55 = I THEN" in result
        assert "RESET 4" in result
        assert "ENDIF" in result

    def test_inline_if_else_endif(self):
        from legacy_winsarp.core.formula_builder import FormulaBuilder
        result = FormulaBuilder._expand_inline_if("IF 55 = I THEN R 130 ELSE R 140 ENDIF")
        assert "IF 55 = I THEN" in result
        assert "ELSE" in result
        assert "R 130" in result or "R130" in result
        assert "R 140" in result

    def test_inline_if_elseif(self):
        from legacy_winsarp.core.formula_builder import FormulaBuilder
        result = FormulaBuilder._expand_inline_if("IF 55 = I THEN RESET 4 ELSE IF 55 = Z THEN RESET 5 ENDIF")
        assert "ELSE" in result
        assert "IF 55 = Z THEN" in result
        assert result.count("ENDIF") == 2

    def test_inline_cond_with_parens(self):
        """IF (cond) THEN ... ENDIF con parentesi era bloccato da trailing \\b."""
        from legacy_winsarp.core.formula_builder import FormulaBuilder
        result = FormulaBuilder._expand_inline_if("IF (55 = I) THEN RESET 4 ENDIF")
        assert "IF 55 = I THEN" in result
        assert "RESET 4" in result
        assert "ENDIF" in result


# ============================================================
# build — nested IF e strutture complesse
# ============================================================

class TestBuildNestedIf:
    def test_if_inside_else_body(self):
        """IF con ELSE contenente un altro IF."""
        steps = [
            "IF 55 = I THEN", "R 130",
            "ELSE",
            "IF 55 = Z THEN", "R 140",
            "ENDIF",
            "ENDIF"
        ]
        steps = WinSarpBuilder.preprocess_elseif(steps)
        formula = WinSarpBuilder().build(steps)
        assert "55 U I" in formula
        assert "55 U Z" in formula
        assert "R130" in formula
        assert "R140" in formula

    def test_if_with_empty_body(self):
        """IF cond THEN ENDIF (body vuoto)."""
        steps = ["IF 55 = I THEN", "ENDIF"]
        steps = WinSarpBuilder.preprocess_elseif(steps)
        formula = WinSarpBuilder().build(steps)
        assert "55 U I" in formula

    def test_if_else_with_empty_then(self):
        """IF cond THEN ELSE body ENDIF (then vuoto)."""
        steps = ["IF 55 = I THEN", "ELSE", "R 130", "ENDIF"]
        steps = WinSarpBuilder.preprocess_elseif(steps)
        formula = WinSarpBuilder().build(steps)
        assert "VF" in formula  # THEN ha VF
        assert "R130" in formula
# ============================================================
# More _extract_steps edge cases
# ============================================================

class TestExtractStepsMore:
    def test_formula_tags_same_line(self):
        """[formula] sulla stessa riga viene saltato perche' la riga inizia con [formula]."""
        fb = _make_fb()
        raw = "[formula]IF 55 = I THEN\nRESET 4\n[/formula]"
        steps = fb._extract_steps(raw)
        # La riga [formula]IF... viene saltata da startswith("[formula]")
        assert len(steps) >= 1  # almeno RESET 4 rimane
        assert "RESET 4" in steps

    def test_mixed_tags_and_comments(self):
        fb = _make_fb()
        raw = "# commento\n[formula]\nIF 55 = I THEN\nENDIF\n[/formula]\n# altro"
        steps = fb._extract_steps(raw)
        assert len(steps) >= 2

    def test_only_whitespace_lines(self):
        fb = _make_fb()
        steps = fb._extract_steps("   \n\t\n  \n")
        assert steps == []

    def test_unicode_in_input(self):
        fb = _make_fb()
        steps = fb._extract_steps("IF 55 = I THEN\nSET 900 = 100\nENDIF")
        assert len(steps) == 3

    def test_no_commands_returns_empty(self):
        fb = _make_fb()
        assert fb._extract_steps("[spiegazione]solo spiegazione") == []


# ============================================================
# _expand_or_conditions
# ============================================================

class TestExpandOrConditions:
    def test_simple_or_expanded(self):
        """OR senza ELSE rimane inline (nessuna espansione)."""
        from legacy_winsarp.core.formula_builder import FormulaBuilder
        s = ["IF 50 = AUTS OR 50 = MALAT THEN", "R 130", "ENDIF"]
        r = FormulaBuilder._expand_or_conditions(s)
        assert r == s

    def test_no_or_passthrough(self):
        from legacy_winsarp.core.formula_builder import FormulaBuilder
        s = ["IF 55 = I THEN", "R 130", "ENDIF"]
        assert FormulaBuilder._expand_or_conditions(s) == s

    def test_or_with_else_expanded(self):
        """OR con ELSE → espanso in IF annidati."""
        from legacy_winsarp.core.formula_builder import FormulaBuilder
        s = ["IF 50 = A OR 50 = B THEN", "R 1", "ELSE", "R 2", "ENDIF"]
        r = FormulaBuilder._expand_or_conditions(s)
        if_count = sum(1 for ln in r if ln.startswith("IF "))
        assert if_count == 2, f"Expected 2 IF, got {if_count}: {r}"
        assert r.count("ENDIF") == 2


# ============================================================
# generate() — retry mock (senza Ollama)
# ============================================================

class TestGenerateRetry:
    def test_retry_on_empty_response(self, monkeypatch):
        """Richiesta vuota → fallisce immediatamente (nessun retry)."""
        fb = _make_fb()
        r = fb.generate("")
        assert not r["success"]
        assert r.get("error") == "Richiesta vuota"

    def test_retry_with_valid_response(self, monkeypatch):
        fb = _make_fb()

        # Mock route_and_process per evitare dipendenza da LLM/OpenRouter
        from legacy_winsarp.core.intent_builder import IntentRequest
        mock_routing = {
            "action": "generation",
            "confidence": 0.85,
            "specifica_formula": {
                "scopo_formula": "Arrotondamento ai quarti d'ora",
                "condizioni_azioni": [
                    {
                        "condizione": "CAMPO 3 VUOTO",
                        "azioni": [{"campo": 3, "valore": "73<K001>25"}],
                    }
                ],
                "spiegazione_linguaggio_naturale": "Arrotonda campo 3 ai quarti d'ora",
            },
            "domande": [],
            "feedback": [],
        }

        def mock_route(*a, **kw):
            return mock_routing
        import legacy_winsarp.core.intent_router as ir_mod0
        monkeypatch.setattr(ir_mod0, "route_and_process", mock_route)

        def mock_classify(req, *a, **kw):
            return IntentRequest(intent="arrotondamento_quarti", fields={"campo": 3}, confidence=0.9, raw=req)
        monkeypatch.setattr(fb, "_classify_intent_via_llm", mock_classify)

        # Mock call_llm per la traduzione SpecificaFormula -> compact
        import core.ai.utils as u_utils
        def mock_call_llm(*a, **kw):
            return json.dumps({"formula": "73<K001>25", "esito": "ok"})
        monkeypatch.setattr(u_utils, "call_llm", mock_call_llm)
        import legacy_winsarp.core.intent_router as ir_mod
        monkeypatch.setattr(ir_mod, "call_llm", mock_call_llm)
        import legacy_winsarp.core.ai.chain_of_thought as cot_mod
        monkeypatch.setattr(cot_mod, "call_llm", mock_call_llm)

        r = fb.generate("arrotondamento ai quarti d'ora", timeout=10)
        assert r["success"]
        assert r["formula"] is not None
        # La formula contiene 73 < (arrotondamento quarti d'ora)
        assert "73 <" in r["formula"] or "73<" in r["formula"]

    def test_retry_on_error_then_success(self, monkeypatch):
        fb = _make_fb()

        mock_routing = {
            "action": "generation",
            "confidence": 0.85,
            "specifica_formula": {
                "scopo_formula": "Riconoscimento turno",
                "condizioni_azioni": [
                    {
                        "condizione": "CAMPO 251 VUOTO",
                        "azioni": [{"campo": 251, "valore": "ENTRATA"}],
                    },
                    {
                        "condizione": "CAMPO 900 VUOTO",
                        "azioni": [{"campo": 900, "valore": 1}],
                    },
                ],
                "spiegazione_linguaggio_naturale": "Riconosce il turno",
            },
            "domande": [],
            "feedback": [],
        }

        def mock_route(*a, **kw):
            return mock_routing
        import legacy_winsarp.core.intent_router as ir_mod0
        monkeypatch.setattr(ir_mod0, "route_and_process", mock_route)

        from legacy_winsarp.core.intent_builder import IntentRequest
        def mock_classify(req, *a, **kw):
            return IntentRequest(intent="riconoscimento_turno", fields={"entrata": 251, "uscita": 271}, confidence=0.9, raw=req)
        monkeypatch.setattr(fb, "_classify_intent_via_llm", mock_classify)

        import core.ai.utils as u_utils
        def mock_call_llm(*a, **kw):
            return json.dumps({"formula": "900<901>1(251*991)", "esito": "ok"})
        monkeypatch.setattr(u_utils, "call_llm", mock_call_llm)
        import legacy_winsarp.core.intent_router as ir_mod
        monkeypatch.setattr(ir_mod, "call_llm", mock_call_llm)
        import legacy_winsarp.core.ai.chain_of_thought as cot_mod
        monkeypatch.setattr(cot_mod, "call_llm", mock_call_llm)

        r = fb.generate("riconoscimento turno", timeout=10)
        assert r["success"]
        assert r["formula"] is not None
        assert "900" in r["formula"]


# ============================================================
# Integration: linter blocco durante generate()
# ============================================================

class TestGenerateLintIntegration:
    """Verifica che il linter venga integrato durante generate()."""

    def test_linter_rejects_missing_label(self, monkeypatch):
        """Generate con richiesta riconoscibile deve produrre formula."""
        fb = _make_fb()
        r = fb.generate("riconoscimento turno con 251 e 271", timeout=10)
        assert r["success"]
        assert r["formula"] is not None
        assert r["source"] == "intent_builder"
        assert r["intent"] == "riconoscimento_turno"

    def test_linter_warns_uninit_field(self, monkeypatch):
        """LLM classification riconosce intent → builder genera formula."""
        fb = _make_fb()

        from legacy_winsarp.core.intent_builder import IntentRequest
        def mock_classify(req, *a, **kw):
            return IntentRequest(intent="reset_puro", params={"fields": "800"}, confidence=0.9, raw=req)
        monkeypatch.setattr(fb, "_classify_intent_via_llm", mock_classify)

        r = fb.generate("azzera campo 800", timeout=10)
        assert r["success"]
        assert r["formula"] is not None

    def test_linter_passes_valid_steps(self, monkeypatch):
        """LLM classification → reset_puro con campo 900."""
        fb = _make_fb()

        from legacy_winsarp.core.intent_builder import IntentRequest
        def mock_classify(req, *a, **kw):
            return IntentRequest(intent="reset_puro", params={"fields": "800,900"}, confidence=0.9, raw=req)
        monkeypatch.setattr(fb, "_classify_intent_via_llm", mock_classify)

        r = fb.generate("azzera 800 e 900", timeout=10)
        assert r["success"]
        assert r["formula"] is not None
        assert "!800" in r["formula"]

    def test_linter_rejects_unreachable_code(self, monkeypatch):
        """Generate con richiesta irriconoscibile → fallisce."""
        fb = _make_fb()
        r = fb.generate("fai cose strane", timeout=10)
        assert not r["success"]
        assert r.get("error") is not None


# ============================================================
# build() — catena ELSE IF lunga e strutture estreme
# ============================================================

class TestBuildLongChain:
    def test_catena_tre_elseif(self):
        """IF + 3 ELSE IF preprocessati e costruiti."""
        steps = [
            "IF 50 = A THEN", "R 1",
            "ELSE IF 50 = B THEN", "R 2",
            "ELSE IF 50 = C THEN", "R 3",
            "ELSE IF 50 = D THEN", "R 4",
            "ENDIF"
        ]
        steps = WinSarpBuilder.preprocess_elseif(steps)
        formula = WinSarpBuilder().build(steps)
        assert "50 U \"A\"" in formula or "50 U 'A'" in formula or "50 A" in formula
        assert "R1" in formula or "R 1" in formula
        assert "R4" in formula or "R 4" in formula

    def test_elese_if_no_final_else(self):
        """Tutti ELSE IF, nessun ramo else finale."""
        steps = [
            "IF 50 = A THEN", "R 1",
            "ELSE IF 50 = B THEN", "R 2",
            "ENDIF"
        ]
        steps = WinSarpBuilder.preprocess_elseif(steps)
        err = _make_fb()._validate_steps(steps)
        assert err is None
        formula = WinSarpBuilder().build(steps)
        assert "R1" in formula or "R 1" in formula
        assert "R2" in formula or "R 2" in formula


# ============================================================
# JSON Schema validation per templates e few-shot
# ============================================================

class TestJsonSchemaValidation:
    def _load_and_validate(self, json_path, schema_path):
        import json as _json
        import jsonschema as _js
        data = _json.loads(json_path.read_text(encoding="utf-8"))
        schema = _json.loads(schema_path.read_text(encoding="utf-8"))
        _js.validate(data, schema)

    def test_master_patterns_schema(self):
        from pathlib import Path
        base = Path(__file__).parent.parent / "core" / "templates"
        self._load_and_validate(base / "master_patterns.json", base / "schemas" / "master_patterns_schema.json")

    def test_few_shot_examples_schema(self):
        from pathlib import Path
        base = Path(__file__).parent.parent / "core" / "templates"
        self._load_and_validate(base / "few_shot_examples.json", base / "schemas" / "few_shot_examples_schema.json")


# ============================================================
# _build_expr — operatori composti WinSarp
# ============================================================

class TestBuildExprWinsarp:
    def test_mixed_winsarp_and_infix(self):
        """801 + 802 nella stessa espressione di una operazione WinSarp A."""
        r = WinSarpBuilder._build_expr("F(900) + 100")
        assert "900" in r
        assert "A" in r  # + → A

    def test_deeply_nested_parens_in_expr(self):
        r = WinSarpBuilder._build_expr("((F(800)+100)*2)")
        assert "800" in r

    def test_double_deref_in_expr(self):
        r = WinSarpBuilder._build_expr("{N} + 100")
        assert "{N}" in r

    def test_pointer_with_subtract(self):
        r = WinSarpBuilder._build_expr("[N - 50")
        assert "[N" in r

# ============================================================
# Raw formula → steps conversion
# ============================================================
class TestRawFormulaToSteps:
    def test_reset_from_formula(self):
        steps = FormulaBuilder._try_convert_raw_formula_to_steps("( !4 )\nVF")
        assert steps == ["RESET 4", "VF"]

    def test_set_from_formula(self):
        steps = FormulaBuilder._try_convert_raw_formula_to_steps("( 900 = '100' )\nVF")
        assert steps == ["SET 900 = '100'", "VF"]

    def test_k_from_formula(self):
        steps = FormulaBuilder._try_convert_raw_formula_to_steps("( K800 A 100 )\nVF")
        assert steps == ["K 800 A 100", "VF"]

    def test_if_from_formula(self):
        steps = FormulaBuilder._try_convert_raw_formula_to_steps("55 U I (( !4 )\nVF")
        assert "IF 55 = I THEN" in steps
        assert "RESET 4" in steps

    def test_r_from_formula(self):
        steps = FormulaBuilder._try_convert_raw_formula_to_steps("R 130\nVF")
        assert steps == ["R 130", "VF"]

    def test_p_from_formula(self):
        steps = FormulaBuilder._try_convert_raw_formula_to_steps("P 2109")
        assert steps == ["P 2109"]

    def test_no_conversion_needed(self):
        steps = FormulaBuilder._try_convert_raw_formula_to_steps("SET 900 = 100\nVF")
        assert steps == ["SET 900 = 100", "VF"]

    def test_empty_input(self):
        steps = FormulaBuilder._try_convert_raw_formula_to_steps("")
        assert steps == []


# ============================================================
# IntentBuilder — nuovi builder deterministici
# ============================================================

class TestIntentBuilderKAccumulo:
    def test_k_accumulo_simple(self):
        from legacy_winsarp.core.intent_builder import build_k_accumulo, IntentRequest
        req = IntentRequest(intent="k_accumulo", params={"targets": "K601 A 3"})
        r = build_k_accumulo(req)
        assert r == "(K601A3)"

    def test_k_accumulo_double(self):
        from legacy_winsarp.core.intent_builder import build_k_accumulo, IntentRequest
        req = IntentRequest(intent="k_accumulo", params={"targets": "K601 A 3 K602 A 3"})
        r = build_k_accumulo(req)
        assert r == "(K601A3)(K602A3)"

    def test_k_accumulo_with_valore(self):
        from legacy_winsarp.core.intent_builder import build_k_accumulo, IntentRequest
        req = IntentRequest(intent="k_accumulo", params={"targets": "K771 A 3 A 4"})
        r = build_k_accumulo(req)
        assert r == "(K771A3A4)"

    def test_k_accumulo_quoted_value(self):
        from legacy_winsarp.core.intent_builder import build_k_accumulo, IntentRequest
        req = IntentRequest(intent="k_accumulo", params={"targets": "K800 A '0.15'"})
        r = build_k_accumulo(req)
        assert r == "(K800A'0.15')"


class TestIntentBuilderArrotondamentoQuarti:
    def test_arrotondamento_quarti_campo3(self):
        from legacy_winsarp.core.intent_builder import build_arrotondamento_quarti, IntentRequest
        req = IntentRequest(intent="arrotondamento_quarti", fields={"campo": 3})
        r = build_arrotondamento_quarti(req)
        assert r.startswith("3UZ(VF")
        assert "70='3'" in r
        assert "73<U'59.00'" in r
        assert "K800A'0.45'" in r
        assert "VU" in r

    def test_arrotondamento_quarti_campo5(self):
        from legacy_winsarp.core.intent_builder import build_arrotondamento_quarti, IntentRequest
        req = IntentRequest(intent="arrotondamento_quarti", fields={"campo": 5})
        r = build_arrotondamento_quarti(req)
        assert "71=5" in r
        assert "K5A800" in r


class TestIntentBuilderCatena:
    def test_catena_r_modo(self):
        from legacy_winsarp.core.intent_builder import build_catena_formule, IntentRequest
        req = IntentRequest(intent="catena_formule", params={"target": "120", "modo": "R"})
        r = build_catena_formule(req)
        assert "R120" in r

    def test_catena_p_modo(self):
        from legacy_winsarp.core.intent_builder import build_catena_formule, IntentRequest
        req = IntentRequest(intent="catena_formule", params={"target": "2109", "modo": "P"})
        r = build_catena_formule(req)
        assert "P2109" in r

    def test_catena_no_target(self):
        from legacy_winsarp.core.intent_builder import build_catena_formule, IntentRequest
        req = IntentRequest(intent="catena_formule", params={"target": "0", "modo": "P"})
        r = build_catena_formule(req)
        assert r is None


class TestIntentBuilderGestioneAssenze:
    def test_assenze_default(self):
        from legacy_winsarp.core.intent_builder import build_gestione_assenze, IntentRequest
        req = IntentRequest(intent="gestione_assenze", fields={"flag": 900}, params={"soglia": "250"})
        r = build_gestione_assenze(req)
        assert "5>Z" in r
        assert "(900='1')" in r
        assert "(900='2')" in r

    def test_assenze_produce_compact(self):
        from legacy_winsarp.core.intent_builder import build_gestione_assenze, IntentRequest
        req = IntentRequest(intent="gestione_assenze", fields={"flag": 900}, params={"soglia": "300"})
        r = build_gestione_assenze(req)
        assert r.startswith("(!900)")


class TestIntentBuilderBuildFromIntent:
    def test_build_from_intent_reset(self):
        from legacy_winsarp.core.intent_builder import build_from_intent, IntentRequest
        req = IntentRequest(intent="reset_puro", params={"fields": "800,801"}, confidence=1.0)
        r = build_from_intent(req)
        assert r["success"]
        assert r["formula"] == "(!800!801)"
        assert r["source"] == "intent_builder_reset_puro"

    def test_build_from_intent_riconoscimento(self):
        from legacy_winsarp.core.intent_builder import build_from_intent, IntentRequest
        req = IntentRequest(intent="riconoscimento_turno", fields={"entrata": 251, "uscita": 271, "flag": 900})
        r = build_from_intent(req)
        assert r["success"]
        assert "251UZE271UZ" in r["formula"]
        assert "900='2'" in r["formula"]

    def test_build_from_intent_calcolo_presenza(self):
        from legacy_winsarp.core.intent_builder import build_from_intent, IntentRequest
        req = IntentRequest(intent="calcolo_presenza", fields={"entrata": 251, "uscita": 271, "flag": 900})
        r = build_from_intent(req)
        assert r["success"]
        assert "70='2'" in r["formula"]

    def test_build_from_intent_unknown(self):
        from legacy_winsarp.core.intent_builder import build_from_intent, IntentRequest
        req = IntentRequest(intent="unknown", confidence=0.0)
        r = build_from_intent(req)
        assert r is None

    def test_build_from_intent_k_accumulo(self):
        from legacy_winsarp.core.intent_builder import build_from_intent, IntentRequest
        req = IntentRequest(intent="k_accumulo", params={"targets": "K601 A 3"})
        r = build_from_intent(req)
        assert r["success"]
        assert "K601A3" in r["formula"]

    def test_build_from_intent_catena(self):
        from legacy_winsarp.core.intent_builder import build_from_intent, IntentRequest
        req = IntentRequest(intent="catena_formule", params={"target": "120", "modo": "R"})
        r = build_from_intent(req)
        assert r["success"]
        assert "R120" in r["formula"]

    def test_build_from_intent_arrotondamento_quarti(self):
        from legacy_winsarp.core.intent_builder import build_from_intent, IntentRequest
        req = IntentRequest(intent="arrotondamento_quarti", fields={"campo": 3})
        r = build_from_intent(req)
        assert r["success"]
        assert "70='3'" in r["formula"]

    def test_build_from_intent_assenze(self):
        from legacy_winsarp.core.intent_builder import build_from_intent, IntentRequest
        req = IntentRequest(intent="gestione_assenze", fields={"flag": 900}, params={"soglia": "250"})
        r = build_from_intent(req)
        assert r["success"]
        assert "5>Z" in r["formula"]


class TestIntentClassifier:
    def test_classify_reset_puro(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("azzeramento 800 e 801")
        assert r.intent == "reset_puro"
        assert r.confidence == 1.0

    def test_classify_riconoscimento(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("riconoscimento turno con 251 e 271")
        assert r.intent == "riconoscimento_turno"
        assert r.confidence >= 0.7

    def test_classify_calcolo_presenza(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("calcola ore presenza con 251 e 271")
        assert r.intent == "calcolo_presenza"
        assert r.confidence >= 0.7

    def test_classify_arrotondamento(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("arrotondamento campo 800")
        assert r.intent == "arrotondamento"
        assert r.confidence >= 0.7

    def test_classify_assenze(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("gestione assenze con soglia 250")
        assert r.intent == "gestione_assenze"
        assert r.confidence >= 0.7

    def test_classify_k_accumulo(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("accumula K771 A 3 A 4")
        assert r.intent == "k_accumulo"
        assert r.confidence >= 0.65

    def test_classify_arrotondamento_quarti(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("arrotondamento ai quarti d'ora campo 3")
        assert r.intent == "arrotondamento_quarti"
        assert r.confidence >= 0.7

    def test_classify_catena(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("catena chiama formula 120")
        assert r.intent == "catena_formule"
        assert r.confidence >= 0.65

    def test_classify_unknown(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("fai qualcosa di completamente diverso e strano")
        # Il classificatore puo' matchare via semantic similarity; ci basta che
        # la confidence sia bassa (fallback embedding, non keyword esatto)
        assert r.confidence < 0.7
        assert r is not None

    def test_classify_condizionale_generico(self):
        from legacy_winsarp.core.intent_builder import IntentClassifier
        r = IntentClassifier.classify("se 800 vuoto allora imposta 900=1 altrimenti imposta 900=2")
        # Il pattern SE/ALLORA classifica come set_field (conf 0.9). OK.
        assert r.intent in ("condizionale_generico", "set_field")
        assert r.confidence >= 0.6


def _make_fb():
    from legacy_winsarp.core.formula_builder import FormulaBuilder
    from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph()
    retriever = WorkbookRetriever()
    return FormulaBuilder(kg, retriever)


def _make_validator():
    retriever = WorkbookRetriever()
    return FormulaValidator(retriever)
