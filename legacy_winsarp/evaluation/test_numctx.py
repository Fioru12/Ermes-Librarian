"""Quick test of failing queries with increased num_ctx."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import cfg
from legacy_winsarp.core.rag_engine import (
    build_chat_engine,
    get_index,
    init_llama_settings,
)
from modules import discover_modules

init_llama_settings()
index = get_index("WinSarp", "qwen3.5:4b", cfg.DOCS_DIR, cfg.CHROMA_DIR, cfg.HASH_FILE)
modules = discover_modules()

queries = [
    ("G05", "Che cosa fa la formula 130?"),
    ("G02", "Mostrami la formula Principale"),
    ("G09", "Chi chiama la formula 200?"),
    ("G04", "Spiega la formula 200"),
]

for qid, query in queries:
    engine = build_chat_engine("WinSarp", "qwen3.5:4b", index, use_generation_prompt=False, modules=modules)
    response = engine.chat(query)
    answer = response.response or ""
    empty = not answer or answer.strip() == ""
    preview = answer[:300] if not empty else "EMPTY"
    print(f"\n=== {qid}: {query} ===")
    print(f"Response: {preview}")
    print(f"Empty: {empty}")
