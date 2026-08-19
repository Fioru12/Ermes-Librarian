"""Seconda batteria di test E2E — scenari reali WinSarp."""
import sys; sys.path.insert(0, ".")
import logging; logging.basicConfig(level=logging.WARNING)

from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.workbook_retriever import WorkbookRetriever
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph

TESTS = [
    # Condizioni composte
    ("AND+OR nidificato", "Se SESSO=2 e (RET1>0 oppure RET2>0), calcola indennita"),
    ("AND triplo", "Se 800=1 e 55=I e 50=AUTS, paga straordinario"),
    ("OR triplo (senza ELSE)", "Se 50=AUTS o 50=MALAT o 50= FEST, chiama R130"),
    ("OR triplo (con ELSE)", "Se 50=A, R1; se 50=B, R2; se 50=C, R3; altrimenti R4"),

    # Operazioni aritmetiche
    ("Expression SET", "Imposta 900 = 800*2 + 300"),
    ("Expression con F()", "SET 900 = F(900) + F(801) * 2"),
    ("AVERAGE in SET", "SET 900 = AVERAGE(801, 802, 803)"),
    ("MIN in SET", "SET 900 = MIN(801, 500)"),
    ("MAX in SET", "SET 900 = MAX(802, 1000)"),

    # K accumulatore
    ("K accumula A", "K 800 A '0.15'"),
    ("K accumula + K accumula", "K 800 A F(801); K 800 S F(802)"),

    # Assegnazioni varie
    ("SET + VF", "Imposta 4=Z e VF"),
    ("SET stringa", 'SET 900 = "FESTIVO"'),

    # RESET in condizione
    ("IF annidato RESET", "Se 55=I, se 50=AUTS, RESET 4; altrimenti RESET 5"),
    ("IF con SET e RESET", "Se MONTELIBERO=1, RESET 900 e SET 901=100"),
]

def run():
    kg = KnowledgeGraph()
    retriever = WorkbookRetriever()
    fb = FormulaBuilder(kg, retriever)

    passed = 0; failed = []
    for name, req in TESTS:
        r = fb.generate(req)
        ok = r["success"] and not r.get("error")
        fml = r.get("formula")
        raw = r.get("raw", "")

        # Verifica sintattica: parentesi bilanciate nel risultato
        parens_ok = True
        if fml:
            depth = 0
            for ch in fml:
                if ch == "(": depth += 1
                elif ch == ")": depth -= 1
                if depth < 0: parens_ok = False; break
            if depth != 0: parens_ok = False

        label = "PASS" if ok and parens_ok else "FAIL"
        if ok and not parens_ok:
            label = "WARN (parens)"

        print(f"{label}: {name}")
        if fml:
            print(f"  {fml[:130]}")
        if not ok and r.get("error"):
            print(f"  ERR: {r['error']}")
        if not parens_ok and fml:
            print(f"  PARENS UNBALANCED (depth={depth})")
        if ok and parens_ok:
            passed += 1
        else:
            failed.append((name, r.get("error", "parens")))

    total = len(TESTS)
    print(f"\n{'='*40}")
    print(f"TOT: {total} | PASS: {passed} | FAIL: {total - passed}")
    if failed:
        print("FAILED:")
        for n, e in failed:
            print(f"  - {n}: {e}")
    return passed == total

if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
