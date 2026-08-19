"""
attachment_solver.py
Determines where to attach a new formula in the existing WinSarp formula chain.

Uses winsarp_catalog.json to find the right insertion point:
  - "after_r N": after R N call (append to existing formula)
  - "new_phase": create a new formula in the specified phase
  - "before_r N": before R N call (prepend)
"""
import json
import logging
from pathlib import Path

_logger = logging.getLogger(__name__)

CATALOG_PATH = Path("data/winsarp_catalog.json")


def load_catalog() -> list[dict]:
    """Load the WinSarp formula catalog."""
    if not CATALOG_PATH.exists():
        _logger.warning("Catalog not found at %s", CATALOG_PATH)
        return []
    try:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _logger.warning("Failed to load catalog: %s", e)
        return []


def find_attachment_point(attachment: dict | None,
                          catalog: list[dict] | None = None) -> dict:
    """Determine where to attach a new formula.

    Args:
        attachment: dict from FormulaIntent.attachment
                    {"type": "after_r", "value": 130}
        catalog: optional pre-loaded catalog list

    Returns:
        dict with:
          - type: "append" | "new_formula"
          - target_id: formula ID to modify/create
          - target_phase: "IG" | "FG" | "DG" | "SUB"
          - explanation: human-readable description
    """
    if catalog is None:
        catalog = load_catalog()

    if not attachment:
        return {
            "type": "new_formula",
            "target_id": None,
            "target_phase": "FG",
            "explanation": "No attachment specified — create as standalone FG formula",
        }

    attach_type = attachment.get("type")
    attach_value = attachment.get("value")

    if attach_type == "after_r":
        return _find_after_r(attach_value, catalog)
    elif attach_type == "before_r":
        return _find_before_r(attach_value, catalog)
    elif attach_type == "new_phase":
        phase = attach_value or "FG"
        return {
            "type": "new_formula",
            "target_id": None,
            "target_phase": phase,
            "explanation": f"Create new {phase} formula",
        }
    else:
        return {
            "type": "new_formula",
            "target_id": None,
            "target_phase": "FG",
            "explanation": f"Unknown attachment type '{attach_type}' — create as standalone",
        }


def _find_after_r(r_number: int, catalog: list[dict]) -> dict:
    """Find the formula that calls R N, to attach AFTER it."""
    for entry in catalog:
        calls_r = entry.get("calls_r", [])
        if r_number in [int(x) for x in calls_r]:
            # This formula calls R r_number → new formula goes after that R
            r_call_idx = [int(x) for x in calls_r].index(r_number)
            return {
                "type": "append",
                "target_id": entry.get("id"),
                "target_formula_name": entry.get("name", f"#{entry.get('id')}"),
                "r_call": f"R {r_number}",
                "r_call_index": r_call_idx,
                "explanation": f"Append after R {r_number} in formula #{entry.get('id')}",
            }

    # No formula calls this R — suggest creating a new formula
    _logger.info("No formula calls R %d — creating new formula", r_number)
    return {
        "type": "new_formula",
        "target_id": None,
        "target_phase": "FG",
        "explanation": f"No formula calls R {r_number} — create new standalone formula",
    }


def _find_before_r(r_number: int, catalog: list[dict]) -> dict:
    """Find the formula that calls R N, to insert BEFORE it."""
    for entry in catalog:
        calls_r = entry.get("calls_r", [])
        if r_number in [int(x) for x in calls_r]:
            return {
                "type": "prepend",
                "target_id": entry.get("id"),
                "target_formula_name": entry.get("name", f"#{entry.get('id')}"),
                "r_call": f"R {r_number}",
                "explanation": f"Insert before R {r_number} in formula #{entry.get('id')}",
            }

    return {
        "type": "new_formula",
        "target_id": None,
        "target_phase": "FG",
        "explanation": f"No formula calls R {r_number} — create new standalone",
    }


def format_attachment_instruction(attachment_info: dict, new_formula: str) -> str:
    """Generate a human-readable instruction for formula placement."""
    t = attachment_info["type"]

    if t == "append":
        target = attachment_info.get("target_formula_name", f"#{attachment_info['target_id']}")
        r_call = attachment_info.get("r_call", "")
        return (
            f"APPEND to {target}:\n"
            f"1. Find {r_call} inside the formula\n"
            f"2. Insert the new formula RIGHT AFTER {r_call}\n"
            f"3. New formula:\n{new_formula}"
        )
    elif t == "prepend":
        target = attachment_info.get("target_formula_name", f"#{attachment_info['target_id']}")
        r_call = attachment_info.get("r_call", "")
        return (
            f"PREPEND to {target}:\n"
            f"1. Find {r_call} inside the formula\n"
            f"2. Insert the new formula RIGHT BEFORE {r_call}\n"
            f"3. New formula:\n{new_formula}"
        )
    elif t == "new_formula":
        phase = attachment_info.get("target_phase", "FG")
        return (
            f"NEW {phase} FORMULA:\n"
            f"1. Create a new {phase} formula\n"
            f"2. Place it in the appropriate position in the formula chain\n"
            f"3. Formula:\n{new_formula}"
        )
    return f"Formula:\n{new_formula}"
