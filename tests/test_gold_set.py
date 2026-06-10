"""
Test that the gold evaluation set is internally consistent.
Validates all expected formula IDs exist in the knowledge graph.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

GOLD_SET_PATH = Path(__file__).parent.parent / "evaluation" / "gold_set.json"
GRAPH_PATH = Path(__file__).parent.parent / "data" / "winsarp_graph.json"


def _load_graph_ids() -> set[int]:
    """Load formula IDs directly from the JSON graph file."""
    if not GRAPH_PATH.exists():
        from core.knowledge_graph import build_graph, save_graph
        graph = build_graph()
        save_graph(graph)
    with open(GRAPH_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("nodes", {})
    # JSON keys are strings, normalize to int
    return {int(k) for k in nodes.keys()}


def test_gold_set_valid():
    """All expected formula IDs in gold set must exist in KG."""
    valid_ids = _load_graph_ids()

    with open(GOLD_SET_PATH, "r", encoding="utf-8") as f:
        gold = json.load(f)

    errors = []
    for entry in gold:
        qid = entry["id"]
        # Check single formula ID
        fid = entry.get("expected_formula_id")
        if fid and fid not in valid_ids:
            errors.append(f"{qid}: expected_formula_id {fid} not in KG (valid: {sorted(valid_ids)})")

        # Check multiple formula IDs
        fids = entry.get("expected_formula_ids", [])
        for fid in fids:
            if fid not in valid_ids:
                errors.append(f"{qid}: expected_formula_ids contains {fid} not in KG")

        # Check call IDs
        call_ids = entry.get("expected_call_ids", [])
        for cid in call_ids:
            if cid not in valid_ids:
                errors.append(f"{qid}: expected_call_ids contains {cid} not in KG")

        caller_ids = entry.get("expected_caller_ids", [])
        for cid in caller_ids:
            if cid not in valid_ids:
                errors.append(f"{qid}: expected_caller_ids contains {cid} not in KG")

    if errors:
        print("GOLD SET VALIDATION FAILED:")
        for e in errors:
            print(f"  {e}")
        assert False, f"{len(errors)} validation errors"
    else:
        print(f"GOLD SET OK: {len(gold)} queries, all IDs valid (KG has {len(valid_ids)} formulas)")


if __name__ == "__main__":
    test_gold_set_valid()
