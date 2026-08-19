"""
evaluation/run_eval.py
Automated evaluation of Ermes RAG system against gold set.

Measures:
  - Recall: Whether expected formulas/chunks are retrieved
  - Precision: Whether retrieved items are relevant
  - Keyword match: Whether answer contains expected keywords
  - Latency: Time per query
  - Pass rate: Percentage of queries meeting quality bar

Usage:
    python evaluation/run_eval.py                     # Run all queries
    python evaluation/run_eval.py --category retrieval_by_id  # Filter by category
    python evaluation/run_eval.py --limit 10          # Run first 10 only
    python evaluation/run_eval.py --model qwen2.5:3b  # Override model
"""
import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import cfg
from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph
from legacy_winsarp.core.rag_engine import (
    build_chat_engine,
    get_index,
    get_source_nodes,
    init_llama_settings,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_logger = logging.getLogger(__name__)

GOLD_SET_PATH = Path(__file__).parent / "gold_set.json"
RESULTS_DIR = Path(__file__).parent / "results"


def load_gold_set() -> list[dict]:
    with open(GOLD_SET_PATH, encoding="utf-8") as f:
        return json.load(f)


def keyword_match(answer: str, keywords: list[str]) -> float:
    """Fraction of expected keywords found in answer."""
    if not keywords:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return hits / len(keywords)


def formula_id_mentioned(answer: str, formula_id: int) -> bool:
    """Check if a formula ID is mentioned in the answer."""
    patterns = [
        rf"#[{formula_id}]",
        rf"formula\s+{formula_id}",
        rf"formul[ae]\s+{formula_id}",
        rf"\b{formula_id}\b",
    ]
    return any(re.search(p, answer, re.IGNORECASE) for p in patterns)


def recall_at_k(retrieved_ids: list[int], expected_ids: list[int], k: int = 4) -> float:
    """Recall@K: fraction of expected items found in top-K retrieved."""
    if not expected_ids:
        return 1.0
    top_k = set(retrieved_ids[:k])
    expected = set(expected_ids)
    hits = len(top_k & expected)
    return hits / len(expected) if expected else 0.0


def precision_at_k(retrieved_ids: list[int], expected_ids: list[int], k: int = 4) -> float:
    """Precision@K: fraction of top-K retrieved items that are expected."""
    if not retrieved_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    expected = set(expected_ids)
    hits = len(top_k & expected)
    return hits / k if k > 0 else 0.0


def run_single_query(
    query: str,
    modulo: str,
    model_id: str,
    index,
    modules: dict,
    kg: KnowledgeGraph,
) -> dict:
    """Run a single query and return answer + metadata."""
    start = time.time()

    chat_engine = build_chat_engine(
        modulo, model_id, index,
        use_generation_prompt=False,
        modules=modules,
    )
    response = chat_engine.chat(query)
    answer = response.response or ""

    # Get source nodes for retrieval analysis
    sources = get_source_nodes(modulo, model_id, index, query)
    source_ids = []
    for s in sources:
        text = s.get("text", "")
        # Try to extract formula ID from source text
        # Format 1: ### <a name="120">...
        m = re.search(r"###\s*<a\s+name=\"(\d+)\"", text)
        if m:
            source_ids.append(int(m.group(1)))
            continue
        # Format 2: ### Formula 120 - ... (KG node from HybridRetriever)
        m = re.search(r"###\s*Formula\s+(\d+)", text)
        if m:
            source_ids.append(int(m.group(1)))

    elapsed = time.time() - start
    return {
        "answer": answer,
        "sources": sources,
        "source_ids": source_ids,
        "elapsed": elapsed,
    }


def evaluate_query(gold: dict, result: dict, kg: KnowledgeGraph) -> dict:
    """Score a single query against gold expectations."""
    answer = result["answer"]
    source_ids = result["source_ids"]

    # Keyword match
    kw = gold.get("expected_keywords", [])
    kw_score = keyword_match(answer, kw)

    # Formula ID mention
    expected_fid = gold.get("expected_formula_id")
    fid_found = formula_id_mentioned(answer, expected_fid) if expected_fid else None

    # Recall/Precision on source IDs
    expected_fids = gold.get("expected_formula_ids", [])
    if expected_fid and expected_fid not in expected_fids:
        expected_fids = [expected_fid] + expected_fids

    rec = recall_at_k(source_ids, expected_fids) if expected_fids else None
    prec = precision_at_k(source_ids, expected_fids) if expected_fids else None

    # Pass criteria:
    # - keyword match >= 0.5
    # - formula ID found if expected (when expected_formula_id is set)
    # - recall >= 0.3 if expected_formula_ids are set
    pass_kw = kw_score >= 0.5
    pass_fid = fid_found is not False  # True or None (not expected)
    pass_recall = rec is None or rec >= 0.3
    passed = pass_kw and pass_fid and pass_recall

    return {
        "keyword_score": round(kw_score, 3),
        "formula_id_found": fid_found,
        "recall": round(rec, 3) if rec is not None else None,
        "precision": round(prec, 3) if prec is not None else None,
        "passed": passed,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate Ermes RAG")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--limit", type=int, help="Max queries to run")
    parser.add_argument("--start-from", type=int, default=1, help="Start from query N (1-indexed)")
    parser.add_argument("--model", default=None, help="Override model ID")
    parser.add_argument("--modulo", default="WinSarp", help="Module to test")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    model_id = args.model or cfg.DEFAULT_MODEL_ID
    modulo = args.modulo

    _logger.info("Initializing LlamaIndex settings...")
    init_llama_settings()

    _logger.info("Loading knowledge graph...")
    kg = KnowledgeGraph()

    _logger.info("Loading gold set...")
    gold_set = load_gold_set()
    if args.category:
        gold_set = [g for g in gold_set if g["category"] == args.category]
    if args.start_from > 1:
        gold_set = gold_set[args.start_from - 1:]
        _logger.info("Starting from query #%d (%d remaining)", args.start_from, len(gold_set))
    if args.limit:
        gold_set = gold_set[:args.limit]

    _logger.info("Building index for module '%s'...", modulo)
    index = get_index(
        modulo, model_id, cfg.DOCS_DIR, cfg.CHROMA_DIR, cfg.HASH_FILE,
    )
    if index is None:
        _logger.error("Failed to build index. Aborting.")
        sys.exit(1)

    _logger.info("Discovering modules...")
    from modules import discover_modules
    modules = discover_modules()

    results = []
    total = len(gold_set)
    passed = 0

    for i, gold in enumerate(gold_set, 1):
        qid = gold["id"]
        query = gold["query"]
        _logger.info("[%d/%d] %s: %s", i, total, qid, query)

        try:
            result = run_single_query(query, modulo, model_id, index, modules, kg)
        except Exception as ex:
            _logger.warning("[%d/%d] %s: ERRORE - %s", i, total, qid, ex)
            result = {
                "answer": "",
                "sources": [],
                "source_ids": [],
                "elapsed": 0,
            }

        evaluation = evaluate_query(gold, result, kg)

        entry = {
            "gold": gold,
            "result": {
                "answer_preview": result["answer"][:200],
                "source_ids": result["source_ids"],
                "elapsed_sec": round(result["elapsed"], 2),
            },
            "evaluation": evaluation,
        }
        results.append(entry)

        if evaluation["passed"]:
            passed += 1
            status = "PASS"
        else:
            status = "FAIL"

        _logger.info(
            "  %s | kw=%.2f fid=%s rec=%s elapsed=%.1fs",
            status,
            evaluation["keyword_score"],
            evaluation["formula_id_found"],
            evaluation["recall"],
            result["elapsed"],
        )

    # Summary
    pass_rate = passed / total * 100 if total > 0 else 0
    avg_latency = sum(r["result"]["elapsed_sec"] for r in results) / total if total else 0
    avg_kw = sum(r["evaluation"]["keyword_score"] for r in results) / total if total else 0

    # Category breakdown
    categories = {}
    for r in results:
        cat = r["gold"]["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r["evaluation"]["passed"]:
            categories[cat]["passed"] += 1

    summary = {
        "total_queries": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate_pct": round(pass_rate, 1),
        "avg_keyword_score": round(avg_kw, 3),
        "avg_latency_sec": round(avg_latency, 2),
        "model": model_id,
        "module": modulo,
        "categories": {
            cat: {
                "total": v["total"],
                "passed": v["passed"],
                "pass_rate_pct": round(v["passed"] / v["total"] * 100, 1),
            }
            for cat, v in sorted(categories.items())
        },
    }

    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"Total queries:  {total}")
    print(f"Passed:         {passed}")
    print(f"Failed:         {total - passed}")
    print(f"Pass rate:      {pass_rate:.1f}%")
    print(f"Avg keyword:    {avg_kw:.3f}")
    print(f"Avg latency:    {avg_latency:.1f}s")
    print(f"Model:          {model_id}")
    print()
    print("Category breakdown:")
    for cat, v in sorted(categories.items()):
        rate = v["passed"] / v["total"] * 100 if v["total"] else 0
        print(f"  {cat:<25} {v['passed']}/{v['total']} ({rate:.0f}%)")
    print("=" * 60)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = args.output or str(RESULTS_DIR / f"eval_{model_id.replace(':', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.json")
    full_output = {"summary": summary, "results": results}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_output, f, ensure_ascii=False, indent=2)
    _logger.info("Results saved to %s", output_path)

    return 0 if pass_rate >= 60 else 1


if __name__ == "__main__":
    sys.exit(main())
