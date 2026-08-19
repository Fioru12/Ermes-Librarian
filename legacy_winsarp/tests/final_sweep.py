"""Final comprehensive test sweep."""
import sys; sys.path.insert(0, ".")
import logging; logging.basicConfig(level=logging.WARNING)

from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.workbook_retriever import WorkbookRetriever
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph

TESTS = [
    ("IF+RESET", "Se 55=I, RESET 4"),
    ("IF+expr", "Se 800=1, dividi importo per 2 (SET 900 = 801/2)"),
    ("OR no ELSE", "Se 50=AUTS oppure 50=MALAT, R130"),
    ("OR con ELSE", "Se 50=AUTS, R130; altrimenti R140; se 50=MALAT, R150"),
    ("AND+OR misto", "Se 800=1 e 55=Z oppure 55=I, calcola bonus"),
    ("Catena ELSE IF", "Se 50=A, R1; se 50=B, R2; altrimenti R3"),
    ("OR ELSE RESET", "Se 10=1 o 10=2, RESET 5; altrimenti RESET 6"),
    ("RESET", "RESET 4"),
    ("K accum", "K 800 A F(801)"),
    ("AND inline", "Se 800=2 e 55=I, RESET 4 e R99999"),
    ("String cond", "Se 50=AUTS, chiama R130"),
]

def run():
    kg = KnowledgeGraph()
    retriever = WorkbookRetriever()
    fb = FormulaBuilder(kg, retriever)

    passed = 0
    for name, req in TESTS:
        r = fb.generate(req)
        ok = r["success"] and not r.get("error")
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        fml = r.get("formula")
        if fml:
            print(f"  {fml[:120]}")
        if r.get("error"):
            print(f"  ERR: {r['error']}")
        if ok:
            passed += 1

    total = len(TESTS)
    print(f"\nTOT: {total} | PASS: {passed} | FAIL: {total - passed}")
    return passed == total

if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
