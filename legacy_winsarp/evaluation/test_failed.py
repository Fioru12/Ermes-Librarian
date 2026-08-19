"""Test failed queries with qwen3.5:9b to confirm model size issue."""
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
    get_source_nodes,
    init_llama_settings,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_logger = logging.getLogger(__name__)

GOLD_SET_PATH = Path(__file__).parent / "gold_set.json"


def keyword_match(answer, keywords):
    if not keywords:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return hits / len(keywords)


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

    failed_ids = ["G02", "G04", "G05", "G08", "G09", "G10"]
    failed_queries = [q for q in gold_list if q["id"] in failed_ids]

    _logger.info("Initializing LlamaIndex settings...")
    init_llama_settings()

    _logger.info("Loading knowledge graph...")
    kg = KnowledgeGraph()

    _logger.info("Building index for module 'WinSarp'...")
    index = get_index(
        "WinSarp", "qwen3.5:9b", cfg.DOCS_DIR, cfg.CHROMA_DIR, cfg.HASH_FILE,
    )
    if index is None:
        _logger.error("Failed to build index. Aborting.")
        sys.exit(1)

    from modules import discover_modules
    modules = discover_modules()

    model_id = "qwen3.5:9b"
    _logger.info(f"Using model: {model_id}")

    results = []
    for q in failed_queries:
        qid = q["id"]
        query = q["query"]
        _logger.info(f"Testing {qid}: {query}")

        start = time.time()
        try:
            chat_engine = build_chat_engine(
                "WinSarp", model_id, index,
                use_generation_prompt=False,
                modules=modules,
            )
            response = chat_engine.chat(query)
            answer = response.response or ""
            elapsed = time.time() - start

            preview = answer[:200] if answer else "EMPTY"
            _logger.info(f"  -> {preview} ({elapsed:.1f}s)")

            kw_score = keyword_match(answer, q.get("expected_keywords", []))
            expected_fid = q.get("expected_formula_id")
            fid_found = formula_id_mentioned(answer, expected_fid) if expected_fid else None

            results.append({
                "id": qid,
                "query": query,
                "response": answer[:500],
                "elapsed": round(elapsed, 1),
                "keyword_score": round(kw_score, 3),
                "formula_id_found": fid_found,
                "empty": not answer or answer.strip() == "",
            })
        except Exception as e:
            elapsed = time.time() - start
            _logger.info(f"  -> ERROR: {e} ({elapsed:.1f}s)")
            results.append({
                "id": qid,
                "query": query,
                "response": f"ERROR: {e}",
                "elapsed": round(elapsed, 1),
                "keyword_score": 0,
                "formula_id_found": False,
                "empty": True,
            })

    out_path = Path(__file__).parent / "results_qwen9b.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    _logger.info(f"Salvato {out_path}")

    # Summary
    non_empty = [r for r in results if not r["empty"]]
    _logger.info(f"\n=== SUMMARY (qwen3.5:9b) ===")
    _logger.info(f"Total: {len(results)}, Non-empty: {len(non_empty)}, Empty: {len(results) - len(non_empty)}")
    for r in results:
        status = "OK" if not r["empty"] else "EMPTY"
        _logger.info(f"  {r['id']}: {status} | kw={r['keyword_score']} | fid={r['formula_id_found']} | {r['elapsed']}s")


if __name__ == "__main__":
    main()
