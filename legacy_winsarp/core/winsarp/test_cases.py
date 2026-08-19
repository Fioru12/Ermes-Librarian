"""
test_cases.py
Test-driven validation for WinSarp formulas.
Defines per-pattern test cases (input/output expectations) and runs them
through the FormulaSimulator to catch logical errors before delivery.

The simulator works with IR steps.  For formulas generated via our pipeline
we have the IR steps available.  For formulas from other sources we attempt
to parse the compact form back into IR steps (works for simple cases).
"""
import re
import logging
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)


@dataclass
class PatternTestCase:
    name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    pattern_ids: list[int] = field(default_factory=list)
    input_fields: dict[str, str] = field(default_factory=dict)
    expected: dict[str, str] = field(default_factory=dict)
    expected_kregs: dict[str, float] | None = None


@dataclass
class TestResult:
    test_name: str
    passed: bool
    actual: dict[str, str]
    expected: dict[str, str]
    mismatches: list[str] = field(default_factory=list)
    error: str | None = None
    kreg_actual: dict[str, float] | None = None
    kreg_expected: dict[str, float] | None = None
    kreg_mismatches: list[str] = field(default_factory=list)


# ── Pattern Test Cases ──────────────────────────────────────────────

PATTERN_TEST_CASES: list[PatternTestCase] = [
    # ── Split festivo/notturno (Patterns 130, 3004) ─────────────
    PatternTestCase(
        name="fg_split_festivo_notturno",
        description="SFN causale con split ore notturne in giorno festivo",
        keywords=["festivo", "notturno", "straordinario", "SFN", "maggiorazioni"],
        pattern_ids=[130, 3004],
        input_fields={"4": "8.00", "21": "3.00", "55": "I"},
        expected={"503": "SFN", "563": "5.00", "564": "3.00"},
        expected_kregs={"K615": 5.0, "K616": 3.0},
    ),
    PatternTestCase(
        name="fg_split_festivo_diurno",
        description="SF causale senza ore notturne in giorno festivo",
        keywords=["festivo", "straordinario", "SF", "maggiorazioni"],
        pattern_ids=[130, 3004],
        input_fields={"4": "6.00", "21": "0.00", "55": "I"},
        expected={"503": "SF", "563": "6.00"},
        expected_kregs={"K615": 6.0},
    ),
    PatternTestCase(
        name="fg_no_festivo_ordinario",
        description="Nessuna causale festivo quando flag 55 != I",
        keywords=["ordinario", "straordinario"],
        pattern_ids=[130, 3004],
        input_fields={"4": "8.00", "21": "0.00", "55": "Z"},
        expected={"503": "", "564": "", "563": ""},
    ),
    # ── Riconoscimento turno (Patterns 5, 10) ───────────────────
    PatternTestCase(
        name="ig_riconoscimento_mattino",
        description="Riconoscimento turno MATTINO (07-14)",
        keywords=["riconoscimento", "turno", "mattino", "matt"],
        pattern_ids=[5, 10],
        input_fields={"801": "8.00", "802": "16.00"},
        expected={"58": "MATT", "100": "I", "900": "1"},
    ),
    PatternTestCase(
        name="ig_riconoscimento_pomeriggio",
        description="Riconoscimento turno POMERIGGIO (14-22)",
        keywords=["riconoscimento", "turno", "pomeriggio", "pome"],
        pattern_ids=[5, 10],
        input_fields={"801": "14.00", "802": "22.00"},
        expected={"58": "POME", "100": "I", "900": "2"},
    ),
    PatternTestCase(
        name="ig_riconoscimento_notte",
        description="Riconoscimento turno NOTTE (22-06)",
        keywords=["riconoscimento", "turno", "notte", "nott"],
        pattern_ids=[5, 10],
        input_fields={"801": "22.00", "802": "6.00"},
        expected={"58": "NOTT", "100": "I", "900": "3"},
    ),
    # ── Esplosione causali (Pattern 2115) ────────────────────────
    PatternTestCase(
        name="dg_esplosione_causali_sfn",
        description="Esplosione causale SFN in K616 e campo 564",
        keywords=["esplosione", "causali", "SFN"],
        pattern_ids=[2115, 3015],
        input_fields={"503": "SFN", "563": "8.00", "564": "3.00"},
        expected={"564": "3.00"},
        expected_kregs={"K616": 3.0, "K615": 8.0},
    ),
    PatternTestCase(
        name="dg_esplosione_causali_sf",
        description="Esplosione causale SF in K615 e campo 563",
        keywords=["esplosione", "causali", "SF"],
        pattern_ids=[2115, 3015],
        input_fields={"503": "SF", "563": "8.00", "564": ""},
        expected={"563": "8.00"},
        expected_kregs={"K615": 8.0},
    ),
]


def _numeric_eq(a: str, b: str) -> bool:
    """Compare two values as numbers if possible, falling back to string equality."""
    try:
        return abs(float(a.replace(',', '.')) - float(b.replace(',', '.'))) < 0.001
    except (ValueError, TypeError):
        return str(a).strip().upper() == str(b).strip().upper()


# ── Simulator-based Test Runner ────────────────────────────────────

def run_test_case(steps: list[str], test: PatternTestCase) -> TestResult:
    """Run a single test case against WinSarp IR steps.

    Returns a TestResult with pass/fail and detailed mismatch info.
    """
    from legacy_winsarp.core.winsarp.simulator import FormulaSimulator

    sim = FormulaSimulator()
    sim._precompute_labels = True
    try:
        result_fields = sim.simulate(steps, dict(test.input_fields))
    except Exception as e:
        _logger.warning("Simulator error in test '%s': %s", test.name, e)
        return TestResult(
            test_name=test.name,
            passed=False,
            actual={},
            expected=test.expected,
            error=f"Simulator error: {e}",
        )

    # Compare expected fields
    mismatches: list[str] = []
    for fld, expected_val in test.expected.items():
        if expected_val == "":
            actual_val = result_fields.get(fld, "")
            if actual_val:
                mismatches.append(f"campo {fld}: atteso vuoto/assente, ottenuto '{actual_val}'")
        else:
            actual_val = result_fields.get(fld, "")
            # Normalize numeric formatting: 5 == 5.0 == 5.00
            if _numeric_eq(actual_val, expected_val):
                continue
            if str(actual_val) != str(expected_val):
                mismatches.append(f"campo {fld}: atteso '{expected_val}', ottenuto '{actual_val}'")

    # Compare K-registers
    kreg_mismatches: list[str] = []
    kreg_actual: dict[str, float] = {}
    if test.expected_kregs:
        kreg_actual = dict(sim.kregs)
        for kreg_name, expected_val in test.expected_kregs.items():
            actual_val = kreg_actual.get(kreg_name, 0.0)
            if abs(actual_val - expected_val) > 0.001:
                kreg_mismatches.append(
                    f"{kreg_name}: atteso {expected_val}, ottenuto {actual_val}"
                )

    passed = len(mismatches) == 0 and len(kreg_mismatches) == 0

    if not passed:
        _logger.info(
            "Test '%s' %s: %d field mismatches, %d K-reg mismatches",
            test.name, "PASSATO" if passed else "FALLITO",
            len(mismatches), len(kreg_mismatches),
        )
        for m in mismatches:
            _logger.info("  Field mismatch: %s", m)
        for m in kreg_mismatches:
            _logger.info("  K-reg mismatch: %s", m)

    return TestResult(
        test_name=test.name,
        passed=passed,
        actual=result_fields,
        expected=test.expected,
        mismatches=mismatches,
        error=None,
        kreg_actual=kreg_actual or None,
        kreg_expected=test.expected_kregs,
        kreg_mismatches=kreg_mismatches,
    )


def match_test_cases(
    user_request: str,
    pattern_id: int | None = None,
) -> list[PatternTestCase]:
    """Find test cases relevant to a user request.

    When pattern_id is known, ONLY match by pattern_id (exact).
    When pattern_id is unknown, use keyword overlap as fallback.
    """
    if not PATTERN_TEST_CASES:
        return []

    # Primary: match by pattern_id
    if pattern_id is not None:
        matched = [tc for tc in PATTERN_TEST_CASES if pattern_id in tc.pattern_ids]
        if matched:
            return matched

    # Fallback: keyword matching (no pattern_id available)
    query_lower = user_request.lower()
    scored: list[tuple[int, PatternTestCase]] = []
    for tc in PATTERN_TEST_CASES:
        kw_match_count = sum(1 for kw in tc.keywords if kw.lower() in query_lower)
        if kw_match_count >= 2:  # Require at least 2 keyword matches
            scored.append((kw_match_count, tc))

    scored.sort(key=lambda x: -x[0])
    return [tc for _, tc in scored]


def validate_with_ir_steps(
    ir_steps: list[str],
    user_request: str,
    pattern_id: int | None = None,
) -> list[TestResult]:
    """Run all matching test cases against IR steps.

    This is the primary entry point — call it when IR steps are available
    (before compact compilation).
    """
    tests = match_test_cases(user_request, pattern_id)
    if not tests:
        return []

    results: list[TestResult] = []
    for test in tests:
        result = run_test_case(ir_steps, test)
        results.append(result)

    return results


def validate_compact_formula(
    compact_formula: str,
    user_request: str,
    pattern_id: int | None = None,
) -> list[TestResult]:
    """Attempt to validate a compact formula by decompiling to IR and running tests.

    This is a fallback for when IR steps are not available.
    Returns empty list if decompilation fails.
    """
    steps = _decompile_compact(compact_formula)
    if not steps:
        return []

    return validate_with_ir_steps(steps, user_request, pattern_id)


def _decompile_compact(formula: str) -> list[str]:
    """Minimal decompiler: extract SET/RESET/K operations from compact WinSarp.

    Handles the simple subset produced by build_compact():
      - ( !N!N... )        → RESET N, RESET N, ...
      - ( N = val )        → SET N = val
      - ( N A val )        → N A val
      - ( N S val )        → N S val
      - ( K N A/S val )    → K N A/S val
      - ( 70 = 'NN' )      → CAMPO70 NN
      - cond ( action )    → IF cond THEN action ENDIF
      - cond (( ... ))     → IF cond THEN ... ENDIF  (double-paren THEN)
      - VF / VU / Vxx      → VF / VU / Vxx
      - [N                 → [N
    """
    # Normalise
    formula = formula.replace(';', '')
    formula = re.sub(r'\s+', ' ', formula).strip()

    # Handle labels and pointer increments first, then paren groups
    tokens = _tokenize_compact(formula)

    steps: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i].strip()

        # Label
        if re.match(r'^V(F|U|\d{2})$', t):
            steps.append(t)
            i += 1
            continue

        # Pointer increment
        if t.startswith('[') and t[1:].isdigit():
            steps.append(t)
            i += 1
            continue

        # R / P call
        if re.match(r'^[RP]\s+\d+$', t):
            steps.append(t)
            i += 1
            continue

        # Paren group
        if t.startswith('(') and t.endswith(')'):
            content = t[1:-1].strip()
            if not content:
                i += 1
                continue

            # Double-paren → THEN body
            if content.startswith('('):
                inner = t[2:-1].strip()
                cond = _extract_nearby_condition(steps, tokens, i)
                if cond:
                    steps.append(f'IF {cond} THEN')
                    inner_steps = _decompile_compact(inner)
                    steps.extend(inner_steps)
                    steps.append('ENDIF')
                else:
                    # No condition found — just parse the inner content
                    inner_tokens = _tokenize_compact(inner)
                    inner_steps = _decompile_tokens(inner_tokens)
                    steps.extend(inner_steps)
                i += 1
                continue

            # Single paren — could be action or condition+action
            parsed = _decompile_single_paren(content, steps, tokens, i)
            steps.extend(parsed)
            i += 1
            continue

        # Unknown token — skip
        i += 1

    return steps


def _tokenize_compact(formula: str) -> list[str]:
    """Split compact formula into tokens: paren groups, labels, calls, pointers."""
    tokens: list[str] = []
    i = 0
    chars = list(formula)

    while i < len(chars):
        ch = chars[i]

        # Paren group — balanced match
        if ch == '(':
            depth = 1
            j = i + 1
            while j < len(chars) and depth > 0:
                if chars[j] == '(':
                    depth += 1
                elif chars[j] == ')':
                    depth -= 1
                j += 1
            tokens.append(''.join(chars[i:j]))
            i = j
            continue

        # Pointer
        if ch == '[':
            j = i + 1
            while j < len(chars) and chars[j].isdigit():
                j += 1
            if j > i + 1:
                tokens.append(''.join(chars[i:j]))
            i = j
            continue

        # Label VF/VU/Vxx
        m = re.match(r'V(F|U|\d{2})\b', formula[i:])
        if m:
            tokens.append(m.group(0))
            i += m.end()
            continue

        # R/P call
        m = re.match(r'[RP]\s+(\d+)\b', formula[i:])
        if m:
            tokens.append(m.group(0))
            i += m.end()
            continue

        i += 1

    return tokens


def _decompile_tokens(tokens: list[str]) -> list[str]:
    """Parse a list of tokens (no condition/THEN structure) into IR steps."""
    steps: list[str] = []
    for t in tokens:
        t = t.strip()
        if re.match(r'^V(F|U|\d{2})$', t):
            steps.append(t)
        elif t.startswith('[') and t[1:].isdigit():
            steps.append(t)
        elif re.match(r'^[RP]\s+\d+$', t):
            steps.append(t)
        elif t.startswith('(') and t.endswith(')'):
            content = t[1:-1].strip()
            steps.extend(_decompile_single_paren_content(content))
        else:
            steps.extend(_decompile_single_paren_content(t))
    return steps


def _extract_nearby_condition(steps: list[str], tokens: list[str], idx: int) -> str | None:
    """Find the condition that governs a THEN body.

    Checks:
    1. The token immediately before this one (if it's a condition)
    2. Any pending condition from the steps list
    """
    # Check the previous token
    if idx > 0:
        prev = tokens[idx - 1].strip()
        cond = _cond_from_string(prev)
        if cond:
            return cond

    # Check the last step for a condition
    for s in reversed(steps):
        if _is_cond_like(s):
            return s
        # Don't look past actions
        if s.startswith(('SET', 'RESET', 'K ', 'IF ', 'ENDIF')):
            break

    return None


def _is_cond_like(s: str) -> bool:
    """Check if a string looks like a compact WinSarp condition."""
    return bool(re.search(r'\d+\s+[U<>=#]\s+', s)) and not s.startswith(('SET', 'RESET', 'K ', 'IF ', 'ENDIF', 'V'))


def _cond_from_string(s: str) -> str | None:
    """Try to parse s as a compact condition: N U val or similar."""
    s = s.strip()
    if not s:
        return None
    # N U val
    m = re.match(r'(\S+)\s+U\s+(.+)', s)
    if m:
        left = m.group(1)
        right = m.group(2).strip("'\"")
        return f'{left} = {right}'
    return None


def _decompile_single_paren(content: str, steps: list[str], tokens: list[str], idx: int) -> list[str]:
    """Parse a single-parenthesised block, which could be:
    - A simple action: ( !800 ) → RESET 800
    - A condition + single action: 55 U I ( K615 A 563 )
    - A condition without explicit paren after: 55 U I ( VF  ← VF is inside )
    """
    content = content.strip()
    if not content:
        return []

    # Check if content starts with a condition
    m = re.match(r'(\S+\s+U\s+\S+)\s*\((.+)', content)
    if m:
        cond_str = m.group(1).strip()
        body = m.group(2).strip()
        cond = _cond_from_string(cond_str)
        if cond:
            result = [f'IF {cond} THEN']
            inner_steps = _decompile_simple_body(body)
            result.extend(inner_steps)
            result.append('ENDIF')
            return result

    # No condition detected — parse as simple actions
    return _decompile_single_paren_content(content)


def _decompile_single_paren_content(content: str) -> list[str]:
    """Parse the content of a parenthesised group as simple IR steps."""
    content = content.strip()
    if not content:
        return []

    # RESET multipli: !N!N!N...
    if content.startswith('!'):
        return [f'RESET {r}' for r in re.findall(r'!(\d+)', content)]

    # CAMPO70
    m = re.match(r'70\s*=\s*[\'"]?(\d+)[\'"]?', content)
    if m:
        return [f'CAMPO70 {m.group(1)}']

    # K-register
    m = re.match(r'K\s*(\d+)\s+([AS])\s+(.+)', content, re.IGNORECASE)
    if m:
        return [f'K {m.group(1)} {m.group(2).upper()} {m.group(3).strip()}']

    # Field A/S
    m = re.match(r'(\d+)\s+([AS])\s+(.+)', content, re.IGNORECASE)
    if m:
        val = m.group(3).strip().strip("'\"")
        return [f'{m.group(1)} {m.group(2).upper()} {val}']

    # SET: N = val
    m = re.match(r'(\d+)\s*=\s*(.+)', content)
    if m:
        return [f'SET {m.group(1)} = {m.group(2).strip()}']

    # R / P call
    m = re.match(r'[RrPp]\s+(\d+)', content)
    if m:
        return [content.upper() if content[0] in 'Rr' else content]

    # Label
    mc = re.match(r'V(F|U|\d{2})$', content)
    if mc:
        return [content]

    return []


def _decompile_simple_body(body: str) -> list[str]:
    """Decompile the body inside a THEN block (after the condition)."""
    body = body.strip()
    if not body:
        return []

    # Re-tokenise the body to handle nested actions
    tokens = _tokenize_compact(body)
    return _decompile_tokens(tokens)


def tests_to_dict(tests: list[TestResult]) -> dict:
    """Convert a list of TestResult to a JSON-serialisable dict."""
    return {
        "total": len(tests),
        "passed": sum(1 for t in tests if t.passed),
        "failed": sum(1 for t in tests if not t.passed),
        "details": [
            {
                "test": t.test_name,
                "passed": t.passed,
                "error": t.error,
                "mismatches": t.mismatches,
                "kreg_mismatches": t.kreg_mismatches,
            }
            for t in tests
        ],
    }
