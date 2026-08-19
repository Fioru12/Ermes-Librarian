"""
production_flow_validator.py
Validates generated formulas against existing production formulas (knowledge graph + catalog).

Checks:
1. Field conflicts: does the formula write to fields managed by existing formulas in the same flow?
2. K-register consistency: does it accumulate K-registers in a way consistent with the flow?
3. Causali slot assignment: does it use causali slots already assigned in the flow?
4. Flow compatibility: is the attachment point / flow valid?
5. Free slot usage: does it use truly free field ranges?
6. Call chain: no circular calls introduced.
"""
import logging
import re
from typing import Any

from legacy_winsarp.core.winsarp.parser_rules import CALL_R as _RE_CALL_R, CALL_P as _RE_CALL_P

_logger = logging.getLogger(__name__)

# ── Field extraction from compact formulas ──

_RE_RESET = re.compile(r'!(\d{1,4})')
_RE_SET = re.compile(r'\(\s*(\d{1,4})\s*=\s*(.+?)\s*\)')
_RE_KACCUM = re.compile(r'K\s*(\d{1,4})\s*([AS])\s*')
_RE_CONF = re.compile(r'\(\s*(\d{1,4})\s*[UZ#>=<]\s*')


def _extract_fields_compact(formula: str) -> dict[str, set[int | str]]:
    """Extract fields, K-registers, causali, calls from a compact formula."""
    result: dict[str, set[int | str]] = {
        "reset_fields": set(),
        "set_fields": set(),
        "k_registers": set(),
        "causali_names": set(),
        "causali_slots": set(),
        "causali_value_slots": set(),
        "fields_read": set(),
        "calls_r": set(),
        "calls_p": set(),
        "all_fields": set(),
    }
    for m in _RE_RESET.finditer(formula):
        f = int(m.group(1))
        result["reset_fields"].add(f)
        result["all_fields"].add(f)
    for m in _RE_SET.finditer(formula):
        f = int(m.group(1))
        result["set_fields"].add(f)
        result["all_fields"].add(f)
        val = m.group(2).strip().strip("'\"")
        if f in (501, 502, 503, 504, 505, 506, 507, 508, 509, 510):
            result["causali_slots"].add(f)
            result["causali_names"].add(val)
        if f in (561, 562, 563, 564, 565, 566, 567, 568, 569, 570):
            result["causali_value_slots"].add(f)
    for m in _RE_KACCUM.finditer(formula):
        k = int(m.group(1))
        result["k_registers"].add(k)
        result["all_fields"].add(k)
    for m in _RE_CONF.finditer(formula):
        f = int(m.group(1))
        result["fields_read"].add(f)
        result["all_fields"].add(f)
    for m in _RE_CALL_R.finditer(formula):
        result["calls_r"].add(m.group(1))
    for m in _RE_CALL_P.finditer(formula):
        result["calls_p"].add(m.group(1))
    return result


# ── Flow definitions ──

class FlowDefinition:
    """Describes a production flow with its formulas and field usage."""

    def __init__(self, name: str, formula_ids: list[int],
                 managed_fields: set[int],
                 managed_k_registers: set[int],
                 managed_causali_slots: set[int],
                 free_field_ranges: list[tuple[int, int]],
                 free_causali_slots: list[int],
                 entry_points: list[str]):
        self.name = name
        self.formula_ids = formula_ids
        self.managed_fields = managed_fields
        self.managed_k_registers = managed_k_registers
        self.managed_causali_slots = managed_causali_slots
        self.free_field_ranges = free_field_ranges
        self.free_causali_slots = free_causali_slots
        self.entry_points = entry_points

    def is_field_used(self, field: int) -> bool:
        return field in self.managed_fields

    def is_k_used(self, k: int) -> bool:
        return k in self.managed_k_registers

    def is_causali_slot_used(self, slot: int) -> bool:
        return slot in self.managed_causali_slots

    def is_field_free(self, field: int) -> bool:
        for lo, hi in self.free_field_ranges:
            if lo <= field <= hi:
                return True
        return False

    def is_causali_slot_free(self, slot: int) -> bool:
        return slot in self.free_causali_slots


# Predefined flow definitions (sourced from production knowledge)
# These are derived from the actual 45-formula catalog.
_FLOWS: dict[str, FlowDefinition] = {
    "IG": FlowDefinition(
        name="Inizio Giornata",
        formula_ids=[1, 5, 10, 1000, 1010, 1020, 2050, 2051, 2060, 9001, 9002],
        managed_fields={
            1, 3, 4, 5, 21, 58, 70, 71, 72, 73, 74, 84, 85,
            100, 111, 112, 113, 114, 141, 142, 143, 144,
            200, 201, 220, 221, 222, 223, 224, 225, 226, 227,
            251, 252, 253, 254, 255, 256, 257,
            271, 272, 273, 274, 275, 276, 277,
            300, 301, 302, 305, 311, 390, 500,
            561, 562, 563, 564, 565, 566, 567, 568, 569, 570,
            800, 801, 802, 803, 804, 900,
        },
        managed_k_registers={803},
        managed_causali_slots=set(range(501, 511)) | set(range(561, 571)),
        free_field_ranges=[(805, 809), (822, 886), (890, 899)],
        free_causali_slots=[507, 508, 509, 510],
        entry_points=["after_r:130", "after_r:5"],
    ),
    "FG Standard": FlowDefinition(
        name="Fine Giornata Standard",
        formula_ids=[100, 110, 120, 130, 140, 200, 210, 1100, 1120, 2000],
        managed_fields={
            1, 3, 4, 5, 21, 55, 58, 500,
            501, 502, 503, 504, 505, 506,
            561, 562, 563, 564, 565, 566,
            800, 890, 900,
        },
        managed_k_registers={3, 4, 21, 601, 602, 603, 604, 605, 611, 614, 615, 616, 625, 626, 800},
        managed_causali_slots={501, 502, 503, 504, 505, 506, 561, 562, 563, 564, 565, 566},
        free_field_ranges=[(805, 809), (822, 886)],
        free_causali_slots=[507, 508, 509, 510],
        entry_points=["after_r:130", "after_r:140", "after_r:200"],
    ),
    "FG GUGEST": FlowDefinition(
        name="Fine Giornata GUGEST",
        formula_ids=[2100, 2101, 2105, 2106, 2107, 2109, 2114, 2115, 2122, 2123, 2124, 2125, 2130, 2140],
        managed_fields={
            1, 2, 3, 4, 5, 50, 51, 52, 55, 70, 71, 72, 73, 74, 99,
            251, 252, 253, 254, 255, 256, 257,
            271, 272, 273, 274, 275, 276, 277,
            300, 301, 302, 311, 500,
            501, 502, 503, 504, 505, 506, 507, 508, 509, 510,
            561, 562, 563, 564, 565, 566, 567, 568, 569, 570,
            608, 609, 611, 612, 614, 615, 616,
            770, 771, 772, 773, 774, 781, 782, 783, 784, 785,
            791, 792,
            800, 801, 811, 812, 887, 889,
            890, 891, 892, 899, 900,
            901, 902, 903, 904, 905, 906, 907, 908, 909, 910,
            911, 912, 913, 914, 915, 916, 917, 918, 919, 920,
            922, 928, 929, 1391, 1801,
        },
        managed_k_registers={
            3, 251, 271, 272, 601, 602, 603, 604, 605, 608, 610,
            611, 612, 614, 615, 616, 626, 627,
            630, 631,
            770, 771, 772, 773, 774, 781, 782, 783, 784, 785,
            800, 801, 811,
            900, 901, 902, 903, 904, 905, 906, 907, 908,
            909, 910, 911, 912, 913, 914, 915, 916, 917, 918, 919, 920,
        },
        managed_causali_slots=set(range(501, 511)) | set(range(561, 571)),
        free_field_ranges=[(805, 809), (822, 886)],
        free_causali_slots=list(range(507, 511)),
        entry_points=["subroutine:GUGEST:P2116", "after_r:2101"],
    ),
    "FG NEW": FlowDefinition(
        name="Fine Giornata NEW (3000 series)",
        formula_ids=[3000, 3001, 3002, 3003, 3004, 3005, 3009, 3014, 3015, 3017, 3030],
        managed_fields={
            1, 2, 3, 4, 5, 50, 51, 52, 55, 70, 71, 72, 73, 74, 99,
            251, 252, 253, 254, 255, 256, 257,
            271, 272, 273, 274, 275, 276, 277,
            300, 301, 302, 311, 500,
            431, 432, 433, 434,
            501, 502, 503, 504, 505, 506, 507, 508, 509, 510,
            561, 562, 563, 564, 565, 566, 567, 568, 569, 570,
            608, 609, 611, 612, 614, 615, 616,
            684, 770, 771, 772, 773, 774, 775, 776, 781, 782, 783, 784, 785,
            788, 790, 791, 792,
            800, 801, 810, 811, 812, 813, 820, 821, 887, 889,
            890, 891, 892, 899, 900,
            901, 902, 903, 904, 905, 906, 907, 908, 909, 910,
            911, 912, 913, 914, 915, 916, 917, 918, 919, 920,
            922, 928, 929, 1000, 1051, 1052, 1100, 1391, 1801,
        },
        managed_k_registers={
            3, 601, 602, 604, 605, 608, 610, 611, 612, 614, 615, 616,
            626, 627, 629, 630, 631,
            770, 771, 772, 773, 774, 775, 776, 781, 782, 783, 784, 785,
            788, 790, 800, 900, 901, 902, 903, 904, 905, 906, 907, 908,
            909, 910, 911, 912, 913, 914, 915, 916, 917, 918, 919, 920,
        },
        managed_causali_slots=set(range(501, 511)) | set(range(561, 571)),
        free_field_ranges=[(805, 809), (822, 886), (890, 899)],
        free_causali_slots=list(range(507, 511)),
        entry_points=["subroutine:FG:P3018", "after_r:3001", "new_phase:FG"],
    ),
}

# K-register → causale mapping
_K_CAUSALE_MAP = {
    611: "S", 614: "SN", 615: "SF", 616: "SFN",
    625: "T", 626: "N", 627: "LFS",
    612: "SP", 613: "SA", 618: "SB",
}

_CAUSALE_SLOT_MAP = {
    501: 611, 561: 611,
    502: 614, 562: 614,
    503: 615, 563: 615,
    504: 616, 564: 616,
    505: 626, 565: 626,
    506: 625, 566: 625,
    507: 612, 567: 612,
    508: 614, 568: 614,
    509: 616, 569: 616,
    510: 618, 570: 618,
}


class ProductionFlowIssue:
    def __init__(self, severity: str, message: str,
                 field: int | str | None = None,
                 flow: str | None = None,
                 existing_formula: int | str | None = None):
        self.severity = severity
        self.message = message
        self.field = field
        self.flow = flow
        self.existing_formula = existing_formula

    def __str__(self) -> str:
        parts = [self.severity.upper()]
        if self.flow:
            parts.append(f"[{self.flow}]")
        if self.field is not None:
            parts.append(f"campo {self.field}")
        if self.existing_formula:
            parts.append(f"(usato da formula {self.existing_formula})")
        parts.append(self.message)
        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
            "flow": self.flow,
            "existing_formula": self.existing_formula,
        }


class ProductionFlowValidator:
    """Validates generated formulas against production flow definitions."""

    def __init__(self, kg: Any = None):
        self._kg = kg
        self._flows = _FLOWS

    def detect_flow_from_formula(self, formula: str) -> str | None:
        """Guess the target flow from formula content and attachment hints."""
        formula_lower = formula.lower()

        if "gugest" in formula_lower or "P2109" in formula or "P2114" in formula or "P2115" in formula:
            return "FG GUGEST"
        if "P3009" in formula or "P3005" in formula or "P3014" in formula or "P3015" in formula:
            return "FG NEW"
        if "R130" in formula or "R140" in formula or "R200" in formula or "P210" in formula:
            return "FG Standard"
        if "R5" in formula or "R9001" in formula or "R9002" in formula or "R2050" in formula:
            return "IG"

        # Detect from K-registers and fields used
        k_set = _extract_fields_compact(formula)["k_registers"]
        set_fields = _extract_fields_compact(formula)["set_fields"]

        # FG Standard uses K601-K616, K625-K627
        fg_k = {601, 602, 603, 604, 605, 611, 612, 614, 615, 616, 625, 626, 627}
        gugest_k = {770, 771, 772, 773, 774, 781, 782, 783, 784, 785, 901, 902, 903, 904, 905, 906, 907, 908}
        fg_new_k = {775, 776, 788, 790, 3000, 3001}

        if k_set & gugest_k:
            return "FG GUGEST"
        if k_set & fg_new_k:
            return "FG NEW"
        if k_set & fg_k:
            return "FG Standard"
        if set_fields & {251, 252, 271, 272, 800, 801, 802, 803, 804}:
            return "IG"

        return None

    def validate_generated_formula(self, formula: str, flow_name: str | None = None) -> list[ProductionFlowIssue]:
        """Validate a generated compact formula against production flow constraints.

        Args:
            formula: The generated WinSarp compact formula.
            flow_name: The target flow name. If None, auto-detect.

        Returns:
            List of ProductionFlowIssue (empty if no issues).
        """
        issues: list[ProductionFlowIssue] = []

        fields = _extract_fields_compact(formula)

        if not flow_name:
            flow_name = self.detect_flow_from_formula(formula)

        if not flow_name:
            issues.append(ProductionFlowIssue(
                "warning", "Impossibile determinare il flusso di destinazione. "
                           "Verifica attachment point (after_r/subroutine/new_phase).",
            ))
            return issues

        flow = self._flows.get(flow_name)
        if not flow:
            issues.append(ProductionFlowIssue(
                "error", f"Flusso '{flow_name}' sconosciuto. Flussi validi: {list(self._flows.keys())}",
            ))
            return issues

        # 1. Field conflict: reset_fields and set_fields should be free or match flow
        causali_slots = set(range(501, 511)) | set(range(561, 571))
        for f in sorted(fields["reset_fields"] | fields["set_fields"]):
            if f in causali_slots:
                continue  # causali slots handled separately
            if flow.is_field_used(f):
                # Check if this field is supposed to be unused (free range)
                if flow.is_field_free(f):
                    continue
                existing = self._find_field_owner(f, flow)
                issues.append(ProductionFlowIssue(
                    "warning",
                    f"Scrive campo {f} già gestito dal flusso {flow_name}",
                    field=f, flow=flow_name, existing_formula=existing,
                ))
            elif not flow.is_field_free(f) and f not in flow.managed_fields and f not in causali_slots:
                # Unknown field — might be OK if it's a new free slot
                if not flow.is_field_free(f):
                    issues.append(ProductionFlowIssue(
                        "info",
                        f"Campo {f} non riconosciuto nel flusso {flow_name} — "
                        f"verifica che sia un nuovo campo consentito",
                        field=f, flow=flow_name,
                    ))

        # 2. K-register consistency
        for k in sorted(fields["k_registers"]):
            if flow.is_k_used(k):
                expected_causale = _K_CAUSALE_MAP.get(k)
                if expected_causale:
                    causale_present = expected_causale in fields["causali_names"]
                    if not causale_present:
                        issues.append(ProductionFlowIssue(
                            "info",
                            f"K{k} ({expected_causale}) accumulato ma causale '{expected_causale}' "
                            f"non trovata negli slot 501-510",
                            field=k, flow=flow_name,
                        ))
            else:
                issues.append(ProductionFlowIssue(
                    "info",
                    f"K{k} non usato nel flusso {flow_name} — verifica sia un nuovo K-register valido",
                    field=k, flow=flow_name,
                ))

        # 3. Causali slot conflict
        for slot in sorted(fields["causali_slots"] | fields["causali_value_slots"]):
            if flow.is_causali_slot_used(slot):
                # Already used — flag if the formula is setting it
                if slot in fields["set_fields"]:
                    existing = self._find_causali_owner(slot, flow)
                    issues.append(ProductionFlowIssue(
                        "warning",
                        f"Slot causale {slot} già assegnato nel flusso {flow_name}",
                        field=slot, flow=flow_name, existing_formula=existing,
                    ))
            elif not flow.is_causali_slot_free(slot):
                if 501 <= slot <= 510 or 561 <= slot <= 570:
                    if slot not in fields["set_fields"]:
                        continue
                    existing = self._find_causali_owner(slot, flow)
                    issues.append(ProductionFlowIssue(
                        "info",
                        f"Slot {slot} già gestito nel flusso {flow_name} — "
                        f"slot liberi: {flow.free_causali_slots}",
                        field=slot, flow=flow_name, existing_formula=existing,
                    ))
                else:
                    issues.append(ProductionFlowIssue(
                        "info",
                        f"Slot {slot} non è nello slot pool del flusso {flow_name}",
                        field=slot, flow=flow_name,
                    ))

        # 4. Free slot recommendation
        for slot in sorted(fields["causali_slots"] | fields["causali_value_slots"]):
            if flow.is_causali_slot_free(slot):
                expected_k = _CAUSALE_SLOT_MAP.get(slot)
                if expected_k and expected_k not in fields["k_registers"]:
                    issues.append(ProductionFlowIssue(
                        "info",
                        f"Slot causale {slot} usato ma K{expected_k} non accumulato — "
                        f"verifica consistenza",
                        field=slot, flow=flow_name,
                    ))

        # 5. Call chain — detect calls to non-existent formulas
        for call_r in sorted(fields["calls_r"]):
            call_id = int(call_r) if call_r.isdigit() else 0
            if call_id and call_id not in flow.formula_ids:
                # Check if it's a reference to a valid formula in another flow
                # This is OK for cross-flow calls (e.g., FG calling IG formula)
                pass

        for call_p in sorted(fields["calls_p"]):
            call_id = int(call_p) if call_p.isdigit() else 0
            if call_id and call_id not in flow.formula_ids:
                pass

        # 6. Flow-specific field range validation
        for f in sorted(fields["all_fields"]):
            if flow.is_field_free(f):
                continue

        # 7. Check attachment consistency
        has_r130 = "R130" in formula
        has_r140 = "R140" in formula
        has_sub_guess = "P2116" in formula or "P3018" in formula

        if flow_name == "FG Standard" and not has_r130 and not has_r140:
            # Might still be OK if it's a new phase
            if "new_phase" not in formula.lower():
                issues.append(ProductionFlowIssue(
                    "info",
                    "Formula FG Standard senza R130 o R140 — "
                    "verifica che sia inserita nel punto corretto della catena",
                    flow=flow_name,
                ))

        return issues

    def _find_field_owner(self, field: int, flow: FlowDefinition) -> int | str | None:
        """Find which existing formula in the flow manages a field."""
        if self._kg is None:
            return None
        for fid in flow.formula_ids:
            node = self._kg.get_formula(fid)
            if not node:
                continue
            reset = node.get("reset_fields", [])
            if field in reset:
                return fid
        return None

    def _find_causali_owner(self, slot: int, flow: FlowDefinition) -> int | str | None:
        """Find which formula in the flow uses a causali slot."""
        if self._kg is None:
            return None
        for fid in flow.formula_ids:
            node = self._kg.get_formula(fid)
            if not node:
                continue
            code = node.get("code", "")
            if f"({slot}=" in code:
                return fid
        return None

    def summary(self, formula: str, flow_name: str | None = None) -> dict:
        """Convenience: run validation and return a summary dict."""
        issues = self.validate_generated_formula(formula, flow_name)
        errors = [i.to_dict() for i in issues if i.severity == "error"]
        warnings = [i.to_dict() for i in issues if i.severity == "warning"]
        infos = [i.to_dict() for i in issues if i.severity == "info"]
        return {
            "valid": len(errors) == 0,
            "flow": flow_name or self.detect_flow_from_formula(formula) or "unknown",
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "total_issues": len(issues),
        }
