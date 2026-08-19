#!/usr/bin/env python3
"""
field_usage_stats.py
Analyzes the 4 production flows from production_flow_validator.py
against the 45-formula winsarp_catalog.json.

Reports per flow:
  - Formula IDs and names
  - Used fields (numeric_refs)
  - Used K-registers (extracted from code via K<N>[AS] pattern)
  - Written causali slots (500-510, 561-570)
  - Call chains (calls_r, calls_p)
  - Free field ranges and free causali slots
"""
import json
import re
import sys
from pathlib import Path

# ── Paths ──
ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "winsarp_catalog.json"

# ── Regex for K-register extraction from compact formula code ──
_RE_KACCUM = re.compile(r'K\s*(\d{1,4})\s*[AS]')

# ── Flow definitions (extracted from production_flow_validator.py) ──
# These match _FLOWS in core/production_flow_validator.py

FLOW_DEFS = {
    "IG": {
        "name": "Inizio Giornata",
        "formula_ids": [1, 5, 10, 1000, 1010, 1020, 2050, 2051, 2060, 9001, 9002],
        "managed_fields": {
            1, 3, 4, 5, 21, 58, 70, 71, 72, 73, 74, 84, 85,
            100, 111, 112, 113, 114, 141, 142, 143, 144,
            200, 201, 220, 221, 222, 223, 224, 225, 226, 227,
            251, 252, 253, 254, 255, 256, 257,
            271, 272, 273, 274, 275, 276, 277,
            300, 301, 302, 305, 311, 390, 500,
            561, 562, 563, 564, 565, 566, 567, 568, 569, 570,
            800, 801, 802, 803, 804, 900,
        },
        "managed_k_registers": {803},
        "managed_causali_slots": set(range(501, 511)) | set(range(561, 571)),
        "free_field_ranges": [(805, 809), (822, 886), (890, 899)],
        "free_causali_slots": [507, 508, 509, 510],
        "entry_points": ["after_r:130", "after_r:5"],
    },
    "FG Standard": {
        "name": "Fine Giornata Standard",
        "formula_ids": [100, 110, 120, 130, 140, 200, 210],
        "managed_fields": {
            1, 3, 4, 5, 21, 55, 58, 500,
            501, 502, 503, 504, 505, 506,
            561, 562, 563, 564, 565, 566,
            800, 890, 900,
        },
        "managed_k_registers": {601, 602, 603, 604, 605, 611, 614, 615, 616, 625, 626},
        "managed_causali_slots": {501, 502, 503, 504, 505, 506, 561, 562, 563, 564, 565, 566},
        "free_field_ranges": [(805, 809), (822, 886), (890, 899)],
        "free_causali_slots": [507, 508, 509, 510],
        "entry_points": ["after_r:130", "after_r:140", "after_r:200"],
    },
    "FG GUGEST": {
        "name": "Fine Giornata GUGEST",
        "formula_ids": [2100, 2101, 2105, 2106, 2107, 2109, 2114, 2115, 2122, 2123, 2124, 2125, 2130, 2140],
        "managed_fields": {
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
        "managed_k_registers": {
            3, 251, 271, 272, 601, 602, 603, 604, 605, 610,
            611, 612, 614, 615, 616, 626, 627,
            770, 771, 772, 773, 774, 781, 782, 783, 784, 785,
            800, 900, 901, 902, 903, 904, 905, 906, 907, 908,
            909, 910, 911, 912, 913, 914, 915, 916, 917, 918, 919, 920,
        },
        "managed_causali_slots": set(range(501, 511)) | set(range(561, 571)),
        "free_field_ranges": [(805, 809), (822, 886), (890, 899)],
        "free_causali_slots": [507, 508, 509, 510],
        "entry_points": ["subroutine:GUGEST:P2116", "after_r:2101"],
    },
    "FG NEW": {
        "name": "Fine Giornata NEW (3000 series)",
        "formula_ids": [3000, 3001, 3002, 3003, 3004, 3005, 3009, 3014, 3015, 3017, 3030],
        "managed_fields": {
            1, 2, 3, 4, 5, 50, 51, 52, 55, 70, 71, 72, 73, 74, 99,
            251, 252, 253, 254, 255, 256, 257,
            271, 272, 273, 274, 275, 276, 277,
            300, 301, 302, 311, 500,
            501, 502, 503, 504, 505, 506, 507, 508, 509, 510,
            561, 562, 563, 564, 565, 566, 567, 568, 569, 570,
            608, 609, 611, 612, 614, 615, 616,
            684, 770, 771, 772, 773, 774, 775, 776, 781, 782, 783, 784, 785,
            788, 790, 791, 792,
            800, 801, 811, 812, 820, 821, 887, 889,
            890, 891, 892, 899, 900,
            901, 902, 903, 904, 905, 906, 907, 908, 909, 910,
            911, 912, 913, 914, 915, 916, 917, 918, 919, 920,
            922, 928, 929, 1051, 1052, 1391, 1801,
        },
        "managed_k_registers": {
            3, 601, 602, 604, 605, 610, 611, 612, 614, 615, 616,
            626, 627, 629, 630, 631,
            770, 771, 772, 773, 774, 775, 776, 781, 782, 783, 784, 785,
            788, 790, 800, 900, 901, 902, 903, 904, 905, 906, 907, 908,
            909, 910, 911, 912, 913, 914, 915, 916, 917, 918, 919, 920,
        },
        "managed_causali_slots": set(range(501, 511)) | set(range(561, 571)),
        "free_field_ranges": [(805, 809), (822, 886), (890, 899)],
        "free_causali_slots": list(range(507, 511)),
        "entry_points": ["subroutine:FG:P3018", "after_r:3001", "new_phase:FG"],
    },
}


def load_catalog() -> list[dict]:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def extract_k_registers_from_code(code: str) -> set[int]:
    return {int(m.group(1)) for m in _RE_KACCUM.finditer(code)}


def ranges_to_str(ranges: list[tuple[int, int]]) -> str:
    parts = []
    for lo, hi in ranges:
        if lo == hi:
            parts.append(str(lo))
        else:
            parts.append(f"{lo}-{hi}")
    return ", ".join(parts)


def field_set_to_ranges(fields: set[int]) -> list[tuple[int, int]]:
    if not fields:
        return []
    s = sorted(fields)
    ranges = []
    start = prev = s[0]
    for v in s[1:]:
        if v == prev + 1:
            prev = v
        else:
            ranges.append((start, prev))
            start = prev = v
    ranges.append((start, prev))
    return ranges


def ranges_diff(full: list[tuple[int, int]], used: set[int]) -> list[tuple[int, int]]:
    free = []
    for lo, hi in full:
        for v in range(lo, hi + 1):
            if v not in used:
                if free and free[-1][1] == v - 1:
                    free[-1] = (free[-1][0], v)
                else:
                    free.append((v, v))
    return free


def main() -> None:
    catalog = load_catalog()
    cat_by_id: dict[int, dict] = {f["id"]: f for f in catalog}

    sep = "=" * 78

    for flow_key, fdef in FLOW_DEFS.items():
        print(sep)
        print(f"  FLOW: {flow_key}  —  {fdef['name']}")
        print(sep)

        # ── Formulas in this flow ──
        formulas = []
        for fid in fdef["formula_ids"]:
            entry = cat_by_id.get(fid)
            if entry:
                formulas.append(entry)
            else:
                print(f"  WARNING: formula {fid} not found in catalog!")

        print(f"\n  Formulas ({len(formulas)}):")
        for f in formulas:
            print(f"    [{f['id']:>5}]  {f['name']}")

        # ── Collect actual usage from catalog ──
        used_fields: set[int] = set()
        used_k_from_code: set[int] = set()
        used_causali_slots: set[int] = set()
        all_calls_r: set[int] = set()
        all_calls_p: set[int] = set()

        for f in formulas:
            used_fields.update(f["numeric_refs"])
            used_k_from_code.update(extract_k_registers_from_code(f["code"]))
            all_calls_r.update(f.get("calls_r", []))
            all_calls_p.update(f.get("calls_p", []))
            # Causali slots: fields in 501-510 or 561-570 that appear in numeric_refs
            for ref in f["numeric_refs"]:
                if 501 <= ref <= 510 or 561 <= ref <= 570:
                    used_causali_slots.add(ref)

        # ── Used fields from numeric_refs ──
        print(f"\n  Fields used (from numeric_refs): {len(used_fields)} total")
        for rng in field_set_to_ranges(used_fields):
            if rng[0] == rng[1]:
                print(f"    {rng[0]}")
            else:
                print(f"    {rng[0]}-{rng[1]}")

        # ── K-registers from code ──
        print(f"\n  K-registers (from code K<N>A/K<N>S): {len(used_k_from_code)}")
        for k in sorted(used_k_from_code):
            print(f"    K{k}")

        # K-registers declared in flow definition but NOT found in code
        missing_k = fdef["managed_k_registers"] - used_k_from_code
        if missing_k:
            print(f"\n  K-registers declared in flow def but NOT found in code ({len(missing_k)}):")
            for k in sorted(missing_k):
                print(f"    K{k}")

        # K-registers found in code but NOT in flow definition
        extra_k = used_k_from_code - fdef["managed_k_registers"]
        if extra_k:
            print(f"\n  K-registers found in code but NOT in flow def ({len(extra_k)}):")
            for k in sorted(extra_k):
                print(f"    K{k}")

        # ── Causali slots written ──
        causali_501_510 = {s for s in used_causali_slots if 501 <= s <= 510}
        causali_561_570 = {s for s in used_causali_slots if 561 <= s <= 570}
        print(f"\n  Causali slots written (501-510): {sorted(causali_501_510) or 'none'}")
        print(f"  Causali slots written (561-570): {sorted(causali_561_570) or 'none'}")

        # ── Call chains ──
        print(f"\n  Call chains R (calls_r): {sorted(all_calls_r) or 'none'}")
        for cr in sorted(all_calls_r):
            target = cat_by_id.get(cr)
            label = target["name"] if target else "NOT IN CATALOG"
            marker = "" if cr in fdef["formula_ids"] else " [CROSS-FLOW]"
            print(f"    R{cr}  ->  {label}{marker}")

        print(f"\n  Call chains P (calls_p): {sorted(all_calls_p) or 'none'}")
        for cp in sorted(all_calls_p):
            target = cat_by_id.get(cp)
            label = target["name"] if target else "NOT IN CATALOG"
            marker = "" if cp in fdef["formula_ids"] else " [CROSS-FLOW]"
            print(f"    P{cp}  ->  {label}{marker}")

        # ── Free ranges ──
        print(f"\n  Free field ranges (declared): {ranges_to_str(fdef['free_field_ranges'])}")
        free_causali = fdef["free_causali_slots"]
        print(f"  Free causali slots: {sorted(free_causali)}")

        # ── Additional: check if any used fields fall in free ranges ──
        for rng in fdef["free_field_ranges"]:
            overlap = [v for v in range(rng[0], rng[1] + 1) if v in used_fields]
            if overlap:
                print(f"  !! Used fields in declared FREE range {rng[0]}-{rng[1]}: {overlap}")

        # ── Managed fields NOT referenced by any formula in this flow ──
        unreferenced_managed = fdef["managed_fields"] - used_fields
        if unreferenced_managed:
            print(f"\n  Managed fields declared but NOT in any formula's numeric_refs ({len(unreferenced_managed)}):")
            for rng in field_set_to_ranges(unreferenced_managed):
                if rng[0] == rng[1]:
                    print(f"    {rng[0]}")
                else:
                    print(f"    {rng[0]}-{rng[1]}")

        print()

    # ── Summary table ──
    print(sep)
    print("  SUMMARY")
    print(sep)
    print(f"  {'Flow':<16} {'Fmts':>5} {'Fields':>8} {'K-regs':>8} {'Causali':>8} {'Calls R':>8} {'Calls P':>8}")
    print(f"  {'-'*16} {'-'*5} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for flow_key, fdef in FLOW_DEFS.items():
        formulas = [cat_by_id[fid] for fid in fdef["formula_ids"] if fid in cat_by_id]
        uf = set()
        uk = set()
        uc = set()
        cr = set()
        cp = set()
        for f in formulas:
            uf.update(f["numeric_refs"])
            uk.update(extract_k_registers_from_code(f["code"]))
            cr.update(f.get("calls_r", []))
            cp.update(f.get("calls_p", []))
            for ref in f["numeric_refs"]:
                if 501 <= ref <= 510 or 561 <= ref <= 570:
                    uc.add(ref)
        print(f"  {flow_key:<16} {len(formulas):>5} {len(uf):>8} {len(uk):>8} {len(uc):>8} {len(cr):>8} {len(cp):>8}")

    print()
    print(f"  Total formulas in catalog: {len(catalog)}")
    catalog_ids = {f["id"] for f in catalog}
    assigned_ids = set()
    for fdef in FLOW_DEFS.values():
        assigned_ids.update(fdef["formula_ids"])
    unassigned = catalog_ids - assigned_ids
    if unassigned:
        print(f"  Formulas NOT assigned to any flow ({len(unassigned)}): {sorted(unassigned)}")
        for uid in sorted(unassigned):
            e = cat_by_id.get(uid)
            if e:
                print(f"    [{uid:>5}]  {e['name']}")
    else:
        print("  All formulas are assigned to a flow.")


if __name__ == "__main__":
    main()
