"""Test remaining 4 failing queries with qwen3.5:9b."""
import json
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import cfg
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph
from legacy_winsarp.core.rag_engine import (
    build_chat_engine,
    get_index,
    init_llama_settings,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_logger = logging.getLogger(__name__)

GOLD_SET_PATH = Path(__file__).parent / "gold_set.json"


def keyword_match(answer, keywords):
    if not keywords:
        return 1.0
    answer_lower = answer.lower()
    return sum(1 for kw in keywords if kw.lower() in answer_lower) / len(keywords)


def formula_id_mentioned(answer, formula_id):
    patterns = [
        rf"#[{formula_id}]",
        rf"formula\s+{formula_id}",
        rf"formul[ae]\s+{formula_id}",
        rf"\b{formula_id}\b",
    ]
    return any(re.search(p, answer, re.IGNORECASE) for p in patterns)


def main():
    with open(GOLD_SET_PATH, "r", encoding="utf-8") as f:
        gold_list = json.load(f)

    failed_ids = ["G02", "G04", "G05", "G09"]
    failed_queries = [q for q in gold_list if q["id"] in failed_ids]

    init_llama_settings()
    kg = KnowledgeGraph()
    index = get_index("WinSarp", "qwen3.5:9b", cfg.DOCS_DIR, cfg.CHROMA_DIR, cfg.HASH_FILE)
    if index is None:
        sys.exit(1)

    from modules import discover_modules
    modules = discover_modules()

    model_id = "qwen3.5:9b"
    results = []
    for q in failed_queries:
        qid = q["id"]
        query = q["query"]
        _logger.info(f"Testing {qid}: {query}")
        start = time.time()
        try:
            chat_engine = build_chat_engine("WinSarp", model_id, index, use_generation_prompt=False, modules=modules)
            response = chat_engine.chat(query)
            answer = response.response or ""
            elapsed = time.time() - start
            preview = answer[:300] if answer else "EMPTY"
            _logger.info(f"  -> {preview} ({elapsed:.1f}s)")
            kw = keyword_match(answer, q.get("expected_keywords", []))
            fid = q.get("expected_formula_id")
            fid_found = formula_id_mentioned(answer, fid) if fid else None
            results.append({"id": qid, "query": query, "response": answer[:500], "elapsed": round(elapsed, 1), "kw": round(kw, 3), "fid": fid_found, "empty": not answer or answer.strip() == ""})
        except Exception as e:
            elapsed = time.time() - start
            _logger.info(f"  -> ERROR: {e}")
            results.append({"id": qid, "query": query, "response": f"ERROR: {e}", "elapsed": round(elapsed, 1), "kw": 0, "fid": False, "empty": True})

    for r in results:
        status = "PASS" if r["kw"] >= 0.5 and r["fid"] is not False and not r["empty"] else "FAIL"
        _logger.info(f"  {r['id']}: {status} | kw={r['kw']} | fid={r['fid']} | {r['elapsed']}s")

    non_empty = [r for r in results if not r["empty"]]
    _logger.info(f"\nTotal: {len(results)}, Non-empty: {len(non_empty)}, Empty: {len(results) - len(non_empty)}")


if __name__ == "__main__":
    main()
