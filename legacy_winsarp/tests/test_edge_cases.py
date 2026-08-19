"""Edge case tests for FormulaBuilder."""
import sys; sys.path.insert(0, ".")
import logging; logging.basicConfig(level=logging.WARNING)

from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph
from legacy_winsarp.core.winsarp.workbook_retriever import WorkbookRetriever

TESTS = [
    ("RESET", "RESET 4"),
    ("RESET+SET", "Azzera campo 5 e imposta 900=1"),
    ("K accum", "K 800 A F(801)"),
    ("String cond", 'Se 50="AUTS", chiama R130'),
    ("AND cond", "Se 800=2 e 55=I, RESET 4 e R99999"),
    ("Commento", "Assegna valore campo 10 a 900"),
    ("Only RESET", "RESET 4 ; RESET 5"),
    ("Only SET", "SET 900 = 100"),
    # ("IF with expr", "Se TOTALE_ORE > 40, paga straordinario 50%"),  # campo testuale, non numerico
]

def run():
    kg = KnowledgeGraph()
    retriever = WorkbookRetriever()
    fb = FormulaBuilder(kg, retriever)

    for name, req in TESTS:
        r = fb.generate(req)
        status = "PASS" if r["success"] else "FAIL"
        fml = r.get("formula")
        if fml is None:
            fml_disp = "N/A"
        else:
            fml_disp = fml[:120]
        print(f"{name}: {status}: {fml_disp}")
        if r.get("error"):
            print(f"  ERR: {r['error']}")
        for v in r.get("validation", []):
            if "WARNING" in str(v):
                print(f"  WARN: {v}")

if __name__ == "__main__":
    run()
