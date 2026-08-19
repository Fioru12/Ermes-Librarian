"""Rebuild catalog JSON and KG"""
import os, sys; sys.path.insert(0, os.getcwd())
from pathlib import Path
from config import cfg

ws_path = Path(cfg.DOCS_DIR) / "WinSarp" / "WinSarp_Formule.txt"

from legacy_winsarp.core.winsarp.catalog import save_catalog_json, parse_catalog_text, load_catalog

# Rebuild catalog from updated WinSarp_Formule.txt
text = ws_path.read_text(encoding="utf-8")
catalog = parse_catalog_text(text)
print(f"Catalogo: {len(catalog)} formule")
ids = sorted(c["id"] for c in catalog)
print(f"IDs: {ids}")

# Save catalog JSON
from legacy_winsarp.core.winsarp.catalog import CATALOGO_JSON_PATH
CATALOGO_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
import json
with open(CATALOGO_JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)
print(f"Catalogo salvato: {CATALOGO_JSON_PATH} ({len(catalog)} formule)")

# Rebuild KG
from legacy_winsarp.core.winsarp.knowledge_graph import build_graph, save_graph
graph = build_graph()
save_graph(graph)
print(f"KG ricostruito: {len(graph['nodes'])} nodi, {len(graph['edges'])} archi")
