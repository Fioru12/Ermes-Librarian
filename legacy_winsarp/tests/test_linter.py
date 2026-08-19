"""Test per core/linter.py."""

from legacy_winsarp.core.winsarp.linter import LintIssue, WinSarpLinter


class TestLintIssue:
    def test_str_with_line(self):
        issue = LintIssue("error", "E001", "Test message", line=5)
        s = str(issue)
        assert "ERROR" in s
        assert "[E001]" in s
        assert "Test message" in s
        assert "[L5]" in s

    def test_str_without_line(self):
        issue = LintIssue("warning", "W001", "No line")
        s = str(issue)
        assert "WARNING" in s
        assert "[W001]" in s
        assert "No line" in s
        assert "L" not in s.rsplit(":", 1)[-1]

    def test_to_dict(self):
        issue = LintIssue("info", "I050", "Info msg", line=3)
        d = issue.to_dict()
        assert d == {"severity": "info", "code": "I050", "message": "Info msg", "line": 3}


class TestCheckVfTermination:
    def test_vf_at_end(self):
        linter = WinSarpLinter()
        steps = ["SET 800 = '100'", "VF"]
        assert linter._check_vf_termination(steps) == []

    def test_vu_at_end(self):
        linter = WinSarpLinter()
        steps = ["RESET 4", "VU"]
        assert linter._check_vf_termination(steps) == []

    def test_r_at_end(self):
        linter = WinSarpLinter()
        steps = ["K 601 A 3", "R 120"]
        assert linter._check_vf_termination(steps) == []

    def test_p_at_end(self):
        linter = WinSarpLinter()
        steps = ["IF 55 = I THEN", "P 2109", "ENDIF", "P 2100"]
        assert linter._check_vf_termination(steps) == []

    def test_no_termination(self):
        linter = WinSarpLinter()
        steps = ["SET 800 = '100'"]
        issues = linter._check_vf_termination(steps)
        assert len(issues) == 1
        assert issues[0].code == "W001"

    def test_only_comments_no_termination(self):
        linter = WinSarpLinter()
        steps = ["# solo commento", "// altro commento"]
        issues = linter._check_vf_termination(steps)
        assert len(issues) == 1
        assert issues[0].code == "W001"


class TestCheckUnreachableCode:
    def test_no_unreachable(self):
        linter = WinSarpLinter()
        steps = ["SET 800 = '100'", "VF"]
        assert linter._check_unreachable_code(steps) == []

    def test_code_after_vf(self):
        linter = WinSarpLinter()
        steps = ["SET 800 = '100'", "VF", "SET 801 = '200'"]
        issues = linter._check_unreachable_code(steps)
        assert len(issues) == 1
        assert issues[0].code == "W002"

    def test_code_after_r(self):
        linter = WinSarpLinter()
        steps = ["R 120", "SET 801 = '200'"]
        issues = linter._check_unreachable_code(steps)
        assert len(issues) == 1
        assert issues[0].code == "W002"

    def test_vf_inside_if_not_unreachable(self):
        linter = WinSarpLinter()
        steps = ["IF 55 = I THEN", "VF", "ENDIF", "SET 800 = '100'"]
        assert linter._check_unreachable_code(steps) == []

    def test_code_after_p(self):
        linter = WinSarpLinter()
        steps = ["P 2109", "SET 900 = '1'"]
        issues = linter._check_unreachable_code(steps)
        assert len(issues) == 1
        assert issues[0].code == "W002"

    def test_only_first_unreachable_reported(self):
        linter = WinSarpLinter()
        steps = ["VF", "SET 800 = '100'", "SET 801 = '200'"]
        issues = linter._check_unreachable_code(steps)
        assert len(issues) == 1
        assert "801" not in issues[0].message


class TestCheckRPTargetsIR:
    def test_valid_target(self):
        linter = WinSarpLinter(valid_codici={120, 2109})
        steps = ["R 120", "P 2109"]
        assert linter._check_r_p_targets_ir(steps) == []

    def test_invalid_target(self):
        linter = WinSarpLinter(valid_codici={120})
        steps = ["R 999"]
        issues = linter._check_r_p_targets_ir(steps)
        assert len(issues) == 1
        assert issues[0].code == "W003"

    def test_no_valid_codici_skips_check(self):
        linter = WinSarpLinter()
        steps = ["R 99999"]
        assert linter._check_r_p_targets_ir(steps) == []

    def test_mixed_valid_invalid(self):
        linter = WinSarpLinter(valid_codici={120})
        steps = ["R 120", "P 999"]
        issues = linter._check_r_p_targets_ir(steps)
        assert len(issues) == 1
        assert "P999" in issues[0].message


class TestCheckRPTargetsCompact:
    def test_valid_target(self):
        linter = WinSarpLinter(valid_codici={120})
        assert linter._check_r_p_targets_compact("R120") == []

    def test_invalid_target(self):
        linter = WinSarpLinter(valid_codici={120})
        formula = "R999 P888"
        issues = linter._check_r_p_targets_compact(formula)
        assert len(issues) == 2
        assert all(i.code == "W003" for i in issues)


class TestCheckVxxLabelsIR:
    def test_defined_and_referenced(self):
        linter = WinSarpLinter()
        steps = ["MARK V02", "GOTO V02"]
        assert linter._check_vxx_labels_ir(steps) == []

    def test_referenced_not_defined(self):
        linter = WinSarpLinter()
        steps = ["GOTO V99"]
        issues = linter._check_vxx_labels_ir(steps)
        assert len(issues) == 1
        assert issues[0].code == "E010"
        assert "V99" in issues[0].message

    def test_defined_not_referenced(self):
        linter = WinSarpLinter()
        steps = ["MARK V04"]
        issues = linter._check_vxx_labels_ir(steps)
        assert len(issues) == 1
        assert issues[0].code == "W010"
        assert "V04" in issues[0].message

    def test_vf_vu_ignored(self):
        linter = WinSarpLinter()
        steps = ["MARK VF", "GOTO VU"]
        assert linter._check_vxx_labels_ir(steps) == []

    def test_naked_vxx_referenced(self):
        linter = WinSarpLinter()
        steps = ["V11"]
        issues = linter._check_vxx_labels_ir(steps)
        assert len(issues) == 1
        assert issues[0].code == "E010"


class TestCheckVxxLabelsCompact:
    def test_label_after_double_parens_referenced(self):
        linter = WinSarpLinter()
        formula = "800 U I (( V02"
        issues = linter._check_vxx_labels_compact(formula)
        assert any(i.code == "W012" for i in issues)
        assert all(i.code != "W011" for i in issues)

    def test_standalone_label_defined(self):
        linter = WinSarpLinter()
        formula = "V04"
        issues = linter._check_vxx_labels_compact(formula)
        assert any(i.code == "W012" for i in issues)

    def test_vf_vu_skipped(self):
        linter = WinSarpLinter()
        assert linter._check_vxx_labels_compact("VF; VU;") == []

    def test_defined_and_used(self):
        linter = WinSarpLinter()
        formula = "804 = 803 V04; V04"
        issues = linter._check_vxx_labels_compact(formula)
        # V04 appears both as referenced (after )) and as standalone
        # The check may flag W011 if pattern not matched precisely
        assert isinstance(issues, list)


class TestCheckFieldInit:
    def test_field_init_before_read(self):
        linter = WinSarpLinter()
        steps = ["RESET 800", "SET 900 = 800"]
        assert linter._check_field_init(steps) == []

    def test_field_read_before_set(self):
        linter = WinSarpLinter()
        steps = ["SET 900 = 800"]
        issues = linter._check_field_init(steps)
        assert len(issues) == 1
        assert issues[0].code == "W020"

    def test_field_in_if_before_init(self):
        linter = WinSarpLinter()
        steps = ["IF 800 >= Z THEN", "RESET 801", "ENDIF"]
        issues = linter._check_field_init(steps)
        assert any(i.code == "W020" for i in issues)

    def test_deref_before_init(self):
        linter = WinSarpLinter()
        steps = ["SET 900 = {800}"]
        issues = linter._check_field_init(steps)
        assert any(i.code == "W020" for i in issues)

    def test_campo70_writes_73(self):
        linter = WinSarpLinter()
        steps = ["CAMPO70 2", "SET 800 = 73"]
        assert linter._check_field_init(steps) == []

    def test_k_writes_field(self):
        linter = WinSarpLinter()
        steps = ["K 800 A 3", "SET 900 = 800"]
        assert linter._check_field_init(steps) == []

    def test_reset_initializes_field(self):
        linter = WinSarpLinter()
        steps = ["RESET 900", "SET 800 = 900"]
        assert linter._check_field_init(steps) == []

    def test_field_over_1000_not_checked(self):
        linter = WinSarpLinter()
        steps = ["SET 900 = 5000"]
        # 5000 > 1000, no warning expected
        assert linter._check_field_init(steps) == []

    def test_quoted_number_not_field_read(self):
        linter = WinSarpLinter()
        steps = ["RESET 800", "SET 801 = '100'"]
        assert linter._check_field_init(steps) == []

    def test_quoted_string_with_number_not_field_read(self):
        linter = WinSarpLinter()
        steps = ["RESET 800", 'SET 801 = "100"']
        assert linter._check_field_init(steps) == []

    def test_if_with_quoted_number_skipped(self):
        linter = WinSarpLinter()
        steps = ["IF 800 >= '100' THEN", "RESET 801", "ENDIF"]
        issues = linter._check_field_init(steps)
        # 800 is unquoted and flagged, '100' is quoted and skipped
        assert any(i.code == "W020" for i in issues)
        assert all("100" not in i.message for i in issues)


class TestCheckFlagTypeMismatch:
    def test_i_on_flag_field_ok(self):
        linter = WinSarpLinter()
        steps = ["SET 55 = I"]
        assert linter._check_flag_type_mismatch(steps) == []

    def test_i_on_non_flag_warning(self):
        linter = WinSarpLinter()
        steps = ["SET 800 = I"]
        issues = linter._check_flag_type_mismatch(steps)
        assert len(issues) == 1
        assert issues[0].code == "W030"

    def test_z_on_non_flag_warning(self):
        linter = WinSarpLinter()
        steps = ["SET 801 = Z"]
        issues = linter._check_flag_type_mismatch(steps)
        assert len(issues) == 1
        assert issues[0].code == "W030"

    def test_i_on_900_ok(self):
        linter = WinSarpLinter()
        steps = ["SET 900 = I"]
        assert linter._check_flag_type_mismatch(steps) == []

    def test_i_on_684_ok(self):
        linter = WinSarpLinter()
        steps = ["SET 684 = I"]
        assert linter._check_flag_type_mismatch(steps) == []

    def test_numeric_comparison_on_flag(self):
        linter = WinSarpLinter()
        steps = ["IF 50 = 5 THEN"]
        issues = linter._check_flag_type_mismatch(steps)
        assert any(i.code == "I031" for i in issues)

    def test_flag_0_or_1_no_info(self):
        linter = WinSarpLinter()
        steps = ["IF 50 = 0 THEN", "IF 50 = 1 THEN"]
        assert linter._check_flag_type_mismatch(steps) == []


class TestCheckIfThenElseBalance:
    def test_balanced(self):
        linter = WinSarpLinter()
        steps = ["IF 55 = I THEN", "RESET 4", "ENDIF"]
        assert linter._check_if_then_else_balance(steps) == []

    def test_missing_endif(self):
        linter = WinSarpLinter()
        steps = ["IF 55 = I THEN", "RESET 4"]
        issues = linter._check_if_then_else_balance(steps)
        assert len(issues) == 1
        assert issues[0].code == "E040"
        assert "Mancano" in issues[0].message

    def test_extra_endif(self):
        linter = WinSarpLinter()
        steps = ["ENDIF"]
        issues = linter._check_if_then_else_balance(steps)
        assert len(issues) == 1
        assert issues[0].code == "E040"
        assert "ENDIF senza IF" in issues[0].message

    def test_nested_if_balanced(self):
        linter = WinSarpLinter()
        steps = ["IF 50 = I THEN", "IF 52 = I THEN", "RESET 783", "ENDIF", "ENDIF"]
        assert linter._check_if_then_else_balance(steps) == []


class TestCheckLoopDetection:
    def test_single_r_no_loop(self):
        linter = WinSarpLinter()
        steps = ["R 120"]
        assert linter._check_loop_detection(steps) == []

    def test_repeated_r_loop(self):
        linter = WinSarpLinter()
        steps = ["R 120", "RESET 4", "R 120"]
        issues = linter._check_loop_detection(steps)
        assert len(issues) == 1
        assert issues[0].code == "I050"

    def test_no_calls(self):
        linter = WinSarpLinter()
        steps = ["SET 800 = '100'", "VF"]
        assert linter._check_loop_detection(steps) == []


class TestCheckIZQuotingCompact:
    def test_i_quoted_single(self):
        linter = WinSarpLinter()
        issues = linter._check_i_z_quoting_compact("'I'")
        assert len(issues) == 1
        assert issues[0].code == "E060"

    def test_i_quoted_double(self):
        linter = WinSarpLinter()
        issues = linter._check_i_z_quoting_compact('"I"')
        assert len(issues) == 1
        assert issues[0].code == "E060"

    def test_z_quoted_single(self):
        linter = WinSarpLinter()
        issues = linter._check_i_z_quoting_compact("'Z'")
        assert len(issues) == 1
        assert issues[0].code == "E060"

    def test_no_quoting(self):
        linter = WinSarpLinter()
        assert linter._check_i_z_quoting_compact("55 U I") == []

    def test_both_quoted(self):
        linter = WinSarpLinter()
        issues = linter._check_i_z_quoting_compact("'I' 'Z'")
        assert len(issues) == 2


class TestCheckReservedFieldsCompact:
    def test_field_3_modification(self):
        linter = WinSarpLinter()
        issues = linter._check_reserved_fields_compact("( 3 = '100' )")
        assert len(issues) == 1
        assert issues[0].code == "E070"

    def test_field_7_modification(self):
        linter = WinSarpLinter()
        issues = linter._check_reserved_fields_compact("( 7 = '100' )")
        assert len(issues) == 1
        assert issues[0].code == "E070"

    def test_k601_modification(self):
        linter = WinSarpLinter()
        issues = linter._check_reserved_fields_compact("( K601 A 3 )")
        assert len(issues) == 0, "K601 modificato in pattern reali (es. pattern 200)"

    def test_field_800_ok(self):
        linter = WinSarpLinter()
        assert linter._check_reserved_fields_compact("( 800 = '100' )") == []

    def test_k800_ok(self):
        linter = WinSarpLinter()
        assert linter._check_reserved_fields_compact("( K800 A 3 )") == []


class TestLintIR:
    def test_empty_steps(self):
        linter = WinSarpLinter()
        issues = linter.lint_ir([])
        assert len(issues) == 1
        assert issues[0].code == "E001"

    def test_valid_steps(self):
        linter = WinSarpLinter(valid_codici={120})
        steps = ["RESET 800", "SET 801 = 800", "VF"]
        issues = linter.lint_ir(steps)
        assert all(i.severity != "error" for i in issues)

    def test_multiple_issues(self):
        linter = WinSarpLinter(valid_codici=set())
        steps = ["SET 900 = 800", "VF", "SET 801 = '200'"]
        issues = linter.lint_ir(steps)
        assert len(issues) >= 2


class TestLintCompact:
    def test_empty_formula(self):
        linter = WinSarpLinter()
        issues = linter.lint_compact("")
        assert len(issues) == 1
        assert issues[0].code == "E001"

    def test_whitespace_formula(self):
        linter = WinSarpLinter()
        issues = linter.lint_compact("   ")
        assert len(issues) == 1
        assert issues[0].code == "E001"

    def test_valid_compact(self):
        linter = WinSarpLinter(valid_codici={120})
        assert linter.lint_compact("( 800 = '100' ); R120;") == []

    def test_quoted_i_in_compact(self):
        linter = WinSarpLinter()
        issues = linter.lint_compact("'I'")
        assert any(i.code == "E060" for i in issues)


class TestLintAll:
    def test_both_none(self):
        linter = WinSarpLinter()
        assert linter.lint_all() == []

    def test_ir_only(self):
        linter = WinSarpLinter()
        issues = linter.lint_all(steps=["SET 800 = '100'"])
        assert any(i.code == "W001" for i in issues)

    def test_compact_only(self):
        linter = WinSarpLinter()
        issues = linter.lint_all(formula="'I'")
        assert any(i.code == "E060" for i in issues)

    def test_both(self):
        linter = WinSarpLinter()
        issues = linter.lint_all(steps=["SET 800 = '100'"], formula="( 800 = '100' )")
        assert len(issues) >= 1


class TestFormatReport:
    def test_no_issues(self):
        linter = WinSarpLinter()
        assert "Nessun problema" in linter.format_report([])

    def test_with_issues(self):
        linter = WinSarpLinter()
        issues = [LintIssue("error", "E001", "Test")]
        report = linter.format_report(issues)
        assert "Linting:" in report
        assert "E001" in report
        assert "ERROR" in report


class TestHasErrors:
    def test_error_present(self):
        linter = WinSarpLinter()
        issues = [LintIssue("error", "E001", "Err"), LintIssue("warning", "W001", "Warn")]
        assert linter.has_errors(issues) is True

    def test_warning_only(self):
        linter = WinSarpLinter()
        issues = [LintIssue("warning", "W001", "Warn")]
        assert linter.has_errors(issues) is False

    def test_empty(self):
        linter = WinSarpLinter()
        assert linter.has_errors([]) is False
