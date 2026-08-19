"""E2E batch test per FormulaBuilder."""
import sys; sys.path.insert(0, ".")
import logging

logging.basicConfig(level=logging.WARNING)

from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph
from legacy_winsarp.core.winsarp.workbook_retriever import WorkbookRetriever

TESTS = [
    ("1. IF semplice + RESET", "Se 55=I, azzera ore straordinario (RESET 4)"),
    ("2. IF + espressione", "Se 800=1, dividi importo per 2 (SET 900 = 801/2)"),
    ("3. OR cond (senza ELSE)", "Se 50=AUTS oppure 50=MALAT, paga indennita (R130)"),
    ("4. OR cond (con ELSE)", "Se 50=AUTS, R130; altrimenti R140; se 50=MALAT, R150"),
    ("5. AND + OR misto", "Se 800=1 e 55=Z oppure 55=I, calcola bonus"),
    ("6. ELSE IF catena", "Se 50=A, R1; se 50=B, R2; altrimenti R3"),
    ("7. OR in linea con ELSE", "Se 10=1 o 10=2, RESET 5; altrimenti RESET 6"),
]

def run():
    kg = KnowledgeGraph()
    retriever = WorkbookRetriever()
    fb = FormulaBuilder(kg, retriever)

    passed = 0
    failed = 0

    for name, req in TESTS:
        print(f"\n=== {name} ===")
        result = fb.generate(req)
        success = result.get("success", False)
        formula = result.get("formula", "N/A")
        error = result.get("error")
        validation = result.get("validation", [])

        if success:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

        print(f"{status}: {formula[:120] if formula else 'N/A'}")
        if error:
            print(f"  ERR: {error}")
        for v in validation:
            if "WARNING" in str(v):
                print(f"  {v}")

    print(f"\n{'='*40}")
    print(f"TOT: {passed+failed} | PASS: {passed} | FAIL: {failed}")
    return failed == 0

if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
