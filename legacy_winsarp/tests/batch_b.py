import sys; sys.path.insert(0, ".")
import logging; logging.basicConfig(level=logging.WARNING, stream=sys.stdout)
from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.workbook_retriever import WorkbookRetriever
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph(); retriever = WorkbookRetriever(); fb = FormulaBuilder(kg, retriever)

tests = [
    ("OR triplo ELSE", "Se 50=A, R1; se 50=B, R2; se 50=C, R3; altrimenti R4"),
    ("Expression SET", "Imposta 900 = 800*2 + 300"),
    ("Expression F()", "SET 900 = F(900) + F(801) * 2"),
]
for name, req in tests:
    r = fb.generate(req)
    ok = r["success"] and not r.get("error")
    print(f"{'PASS' if ok else 'FAIL'}: {name}", flush=True)
    print(f"  {r.get('formula','N/A')[:130]}", flush=True)
    if not ok and r.get("error"): print(f"  ERR: {r['error']}", flush=True)
print("DONE", flush=True)
