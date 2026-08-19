import json
from pathlib import Path

from evaluation.run_library_eval import GOLD_SET_PATH, evaluate


def test_demo_gold_set_meets_retrieval_quality_bar():
    gold_set = json.loads(Path(GOLD_SET_PATH).read_text(encoding="utf-8"))

    report = evaluate(gold_set)

    assert len(gold_set) >= 16
    assert report["recall_at_3"] >= 0.9
    assert all(item["passed"] for item in report["details"])
