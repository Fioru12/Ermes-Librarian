import sys; sys.path.insert(0, ".")
import logging; logging.basicConfig(level=logging.WARNING, stream=sys.stdout)
from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.workbook_retriever import WorkbookRetriever
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph(); retriever = WorkbookRetriever(); fb = FormulaBuilder(kg, retriever)

tests = [
    ("AVERAGE", 'SET 900 = AVERAGE(801, 802, 803)'),
    ("MIN/MAX", 'SET 900 = MIN(801, 500); SET 901 = MAX(802, 1000)'),
    ("K accum A+S", 'K 800 A F(801); K 800 S F(802)'),
    ("SET + VF", 'Imposta 4=Z e VF'),
    ("SET string", 'SET 900 = "FESTIVO"'),
]
for name, req in tests:
    r = fb.generate(req)
    ok = r["success"] and not r.get("error")
    print(f"{'PASS' if ok else 'FAIL'}: {name}", flush=True)
    print(f"  {r.get('formula','N/A')[:130]}", flush=True)
    if not ok and r.get("error"): print(f"  ERR: {r['error']}", flush=True)
print("DONE", flush=True)
