"""
intent_translator.py
Deterministic translator: FormulaIntent (JSON) → WinSarp IR steps → compact formula.

This is 100% deterministic — no LLM, no randomness, no ambiguity.
Given a FormulaIntent, it always produces the same IR steps.
"""
import logging
import re
from typing import Any

from legacy_winsarp.core.intent_extractor import (
    FormulaIntent, IntentBlock, IntentCondition,
    IntentFieldOp, IntentKAccum,
)

_logger = logging.getLogger(__name__)


def _quote_constant(val: Any) -> str:
    """Ensure constant value is quoted appropriately for WinSarp."""
    if val is None:
        return ""
    s_val = str(val).strip()
    if (s_val.startswith("'") and s_val.endswith("'")) or (s_val.startswith('"') and s_val.endswith('"')):
        return s_val
    if s_val.upper() in ("I", "Z"):
        return s_val
    if re.match(r'^[+-]?[0-9:.,]+$', s_val):
        return f"'{s_val}'"
    return f'"{s_val}"'


def translate(intent: FormulaIntent) -> list[str]:
    """Translate a FormulaIntent to WinSarp IR steps.

    Returns a list of IR step strings ready for build_compact().
    """
    steps: list[str] = []

    for block in intent.blocks:
        _translate_block(block, steps, indent=0)

    # Emit top-level K-register accumulations (always unconditional)
    for ka in intent.k_registers:
        step = _translate_kaccum(ka)
        if step:
            steps.append(step)

    steps.append("VF")
    return steps


def _translate_block(block: IntentBlock, steps: list[str], indent: int = 0) -> None:
    """Translate a single IntentBlock to IR steps, appending to steps list."""
    prefix = "  " * indent

    if block.conditions and not block.is_else:
        # Start IF block
        cond_str = _format_conditions(block.conditions, join_op=block.conditions_join)
        steps.append(f"{prefix}IF {cond_str} THEN")

    elif block.is_else:
        steps.append(f"{prefix}ELSE")

    # Operations
    for op in block.operations:
        _translate_operation(op, steps, prefix)

    # K-accumulations
    for ka in block.k_accumulations:
        step = _translate_kaccum(ka)
        if step:
            steps.append(f"{prefix}{step}")

    # Sub-blocks (nested IF/ELSE)
    for sb in block.sub_blocks:
        _translate_block(sb, steps, indent + 1)

    # Close IF
    if block.conditions and not block.is_else:
        steps.append(f"{prefix}ENDIF")

    # Close ELSE
    if block.is_else and not block.sub_blocks:
        # If it's an ELSE with no sub-blocks and no conditions of its own
        # the ENDIF is handled by the parent IF
        pass


def _format_conditions(conditions: list[IntentCondition], join_op: str = "E") -> str:
    """Format conditions for IR IF statement.

    Supports: IF 55 = I THEN, IF 21 > Z THEN, etc.
    Multiple conditions joined with 'E' (AND) or 'O' (OR).
    """
    parts = []
    for c in conditions:
        left = str(c.left_field)
        if c.right_is_field:
            right = str(c.right_value)
        else:
            right = _quote_constant(c.right_value)
        parts.append(f"{left} {_ir_op(c.operator)} {right}")

    return f" {join_op} ".join(parts)


def _ir_op(op: str) -> str:
    """Map the operator to IR form."""
    mapping = {
        "=": "=",
        "#": "#",
        ">": ">",
        "<": "<",
        ">=": ">=",
        "<=": "<=",
    }
    return mapping.get(op, "=")


def _has_arithmetic(source: str) -> bool:
    """Check if a source_field contains arithmetic operators."""
    src = str(source)
    # Direct arithmetic symbols
    if re.search(r'[+\-*/×]', src):
        return True
    # Word-style multiplication: "K626 x 1.25", "K626 X 1.25", "K626 M 1.25"
    if re.search(r'\d+\s*[xXmM×]\s*\d', src):
        return True
    # Simple "field M value" pattern
    if re.search(r'K?\d+\s+[MmXx]\s+[\d.]+', src):
        return True
    return False


def _translate_operation(op: IntentFieldOp, steps: list[str], prefix: str = "") -> None:
    """Translate a single IntentFieldOp and append IR steps."""
    if op.type == "reset":
        steps.append(f"{prefix}RESET {op.field}")
        return

    if op.type == "set":
        if op.source_field is not None and op.value is None:
            src = str(op.source_field)
            if _has_arithmetic(src):
                steps.append(f"{prefix}COMMENT WinSarp: SET {op.field} = {src}")
                m = re.match(r'^(K?\d+)', src)
                if m:
                    steps.append(f"{prefix}SET {op.field} = {m.group(1)}")
                else:
                    steps.append(f"{prefix}SET {op.field} = '0'")
            else:
                steps.append(f"{prefix}SET {op.field} = {src}")
            return
        elif op.value is not None:
            steps.append(f"{prefix}SET {op.field} = {_quote_constant(op.value)}")
            return
        elif op.source_field is not None:
            steps.append(f"{prefix}SET {op.field} = {op.source_field}")
            return

    if op.type == "add":
        val = _quote_constant(op.value) if op.value is not None else op.source_field
        steps.append(f"{prefix}SET {op.field} = {op.field} A {val}")
        return

    if op.type == "sub":
        val = _quote_constant(op.value) if op.value is not None else op.source_field
        steps.append(f"{prefix}SET {op.field} = {op.field} S {val}")
        return

    if op.type == "r_call":
        val = op.value or op.source_field
        steps.append(f"{prefix}R {val}")
        return

    if op.type == "p_call":
        val = op.value or op.source_field
        steps.append(f"{prefix}P {val}")
        return

    if op.type == "campo70":
        steps.append(f"{prefix}CAMPO70 {op.value}")
        return

    if op.type == "comment":
        steps.append(f"{prefix}COMMENT {op.value}")
        return


def _translate_kaccum(ka: IntentKAccum) -> str:
    """Translate K-register accumulation to IR step."""
    return f"K {ka.kreg.replace('K', '')} {ka.operation} {ka.source_field}"


# ── Compact generation wrapper ────────────────────────────────

def translate_and_compact(intent: FormulaIntent, builder: Any) -> str:
    """Translate intent to IR, then build compact formula.

    Args:
        intent: FormulaIntent from intent_extractor
        builder: WinSarpBuilder instance (from legacy_winsarp.core.formula_builder)

    Returns:
        Compact WinSarp formula string.
    """
    steps = translate(intent)
    return builder.build_compact(steps)


def translate_to_steps(intent: FormulaIntent) -> list[str]:
    """Just translate to IR steps (no compact). Useful for testing."""
    return translate(intent)
