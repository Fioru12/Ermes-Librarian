from modules.winsarp import clean_code, parse_response, validate_winsarp


def test_clean_code_removes_markdown_and_comments():
    raw = """
    ```text
    (500="DURATA?X"); ? commento
    # commento markdown
    ```
    """
    result = clean_code(raw)
    assert result == '(500="DURATA?X");'


def test_validate_winsarp_detects_missing_semicolon():
    errors = validate_winsarp('(500="DURATA")')
    assert any("non termina con ';'" in e for e in errors)


def test_parse_response_splits_formula_and_explanation():
    txt = (
        "Formula 100 - Test\n"
        "[FORMULA]\n"
        "```text\n(500=\"DURATA\");\n```\n"
        "[SPIEGAZIONE]\n"
        "Spiegazione semplice."
    )
    parsed = parse_response(txt, "WinSarp")
    assert parsed["has_split"] is True
    assert parsed["code"] == '(500="DURATA");'
    assert "Spiegazione semplice." in parsed["exp"]


def test_validate_winsarp_detects_forbidden_fields():
    errors = validate_winsarp('(7="TEST");')
    assert any("Campi 7-9 vietati" in e or "vietati" in e.lower() for e in errors)


def test_validate_winsarp_detects_unbalanced_parentheses():
    errors = validate_winsarp('(500="DURATA";')
    assert any("senza la ')' corrispondente" in e for e in errors)


def test_validate_winsarp_detects_unbalanced_quotes():
    errors = validate_winsarp('(500="DURATA\');')
    assert any("bilanciat" in e for e in errors)


def test_validate_winsarp_valid_formula():
    errors = validate_winsarp('(500="DURATA");R110;')
    assert len(errors) == 0


def test_validate_winsarp_detects_field_70_without_reset():
    errors = validate_winsarp('(70="TEST");')
    assert any("manca reset !7x" in e for e in errors)


def test_validate_winsarp_detects_unsupported_operators():
    errors = validate_winsarp('(500=!561!%2);')
    assert any("Operatore non supportato" in e for e in errors)


def test_validate_winsarp_detects_return_code_without_semicolon():
    errors = validate_winsarp('(500="DURATA")R110')
    assert any("Codice di ritorno R senza punto e virgola" in e for e in errors)


def test_parse_response_handles_fallback_phrases():
    txt = "Nel catalogo non e' presente una formula per questo caso."
    parsed = parse_response(txt, "WinSarp")
    assert parsed["has_split"] is False
    assert parsed["code"] == ""
    assert parsed["exp"] == txt


def test_parse_response_case_insensitive_markers():
    txt = (
        "Formula 100\n"
        "[formula]\n"
        "```text\n(500=\"DURATA\");\n```\n"
        "[SPIEGAZIONE]\n"
        "Test"
    )
    parsed = parse_response(txt, "WinSarp")
    assert parsed["has_split"] is True
    assert parsed["code"] == '(500="DURATA");'


def test_clean_code_preserves_question_mark_in_string():
    raw = '(500="DURATA?X"); ? commento'
    result = clean_code(raw)
    assert result == '(500="DURATA?X");'


def test_validate_winsarp_detects_empty_assignment():
    errors = validate_winsarp('(500=);')
    assert any("Valore vuoto" in e for e in errors)


def test_validate_winsarp_detects_forbidden_field_references():
    errors = validate_winsarp('(500=!7!);')
    assert any("Riferimento a campo vietato" in e for e in errors)
