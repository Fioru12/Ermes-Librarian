import sys; sys.path.insert(0, ".")
import logging; logging.basicConfig(level=logging.WARNING)
from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.workbook_retriever import WorkbookRetriever
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph

REQS = [
    ("AND triplo", "Se 800=1 e 55=I e 50=AUTS, paga straordinario"),
    ("OR triplo no ELSE", "Se 50=AUTS o 50=MALAT o 50=FEST, chiama R130"),
    ("OR triplo con ELSE", "Se 50=A, R1; se 50=B, R2; se 50=C, R3; altrimenti R4"),
    ("Expression SET", "Imposta 900 = 800*2 + 300"),
    ("Expression F()", "SET 900 = F(900) + F(801) * 2"),
    ("AVERAGE", "SET 900 = AVERAGE(801, 802, 803)"),
    ("MIN MAX", "SET 900 = MIN(801, 500); SET 901 = MAX(802, 1000)"),
    ("K accumula", "K 800 A F(801); K 800 S F(802)"),
    ("SET + VF", "Imposta 4=Z e VF"),
    ("SET string", 'SET 900 = "FESTIVO"'),
]

kg = KnowledgeGraph(); retriever = WorkbookRetriever(); fb = FormulaBuilder(kg, retriever)
passed = 0
for name, req in REQS:
    r = fb.generate(req)
    ok = r["success"] and not r.get("error")
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
    print(f"  {r.get('formula','N/A')[:130]}")
    if not ok and r.get("error"): print(f"  ERR: {r['error']}")
    if ok: passed += 1
print(f"\nTOT: {len(REQS)} | PASS: {passed} | FAIL: {len(REQS)-passed}")
