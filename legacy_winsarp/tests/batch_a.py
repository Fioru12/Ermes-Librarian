import sys; sys.path.insert(0, ".")
import logging; logging.basicConfig(level=logging.WARNING)
from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.workbook_retriever import WorkbookRetriever
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph(); retriever = WorkbookRetriever(); fb = FormulaBuilder(kg, retriever)

for name, req in [
    ("AND triplo", "Se 800=1 e 55=I e 50=AUTS, paga straordinario"),
    ("OR triplo no ELSE", "Se 50=AUTS o 50=MALAT o 50=FEST, chiama R130"),
]:
    r = fb.generate(req)
    ok = r["success"] and not r.get("error")
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
    print(f"  {r.get('formula','N/A')[:130]}")
    if not ok and r.get("error"): print(f"  ERR: {r['error']}")
