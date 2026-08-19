"""Live test: generate formulas like in FormuleWinsarpInUso.txt"""
import sys
sys.path.insert(0, '.')
from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph
from legacy_winsarp.core.winsarp.few_shot_retriever import FewShotRetriever
from legacy_winsarp.core.winsarp.linter import WinSarpLinter
from legacy_winsarp.core.winsarp.validator import LarkFormulaValidator

kg = KnowledgeGraph()
fb = FormulaBuilder(kg)
linter = WinSarpLinter()
lark_v = LarkFormulaValidator()
fsr = FewShotRetriever()
fsr.load()

REQUESTS = [
    'riconoscimento turno: se timbratura presente tra le 6 e le 14 assegna MATT e flag 900=1, tra 14 e 22 POME e flag 900=2, tra 22 e 6 NOTT e flag 900=3. Inizializza anche gli indicatori 800-804 e imposta intervalli 111/141',
    'calcolo presenza: durata con azzeramento causali 561-570, richiama formula 110',
    'calcolo ore per assenze: sottrai ore assenza (608+609) dalle ore totali, gestisci primo e secondo intervallo, accumula K601 e K602',
    'straordinario notturno: rileva ore tra 22 e 6 nei giorni feriali, accumula in K614, imposta causale SN',
    'esplodi causali: se 918 valorizzato e 919=1, causale F in 561; se 919=2, FNG; se 902>0, causale N in 562',
    'maggiorazioni su ore ordinarie: se campo 902 > 0, calcola scaglioni 15min/30min/45min, accumula in K902',
    'warning ore carenti: se campo 5 > 0, stampa messaggio attenzione con codice azienda e dipendente',
    'primo giro: azzera indicatori 770-774, attiva flag K770, gestisci festivo P2109, accumula K771 da 3+4, calcola limite 40h, flag 900=1',
    'gestione festivita non goduta: se campo 684 valorizzato e diverso da 1, flag non goduta con K629, altrimenti normale con K630',
    'calcolo straordinario festivo diurno: ore lavoro in giorno festivo, accumula in K615, causale SF',
]

def validate(compact):
    lint_issues = linter.lint_compact(compact)
    lark_issues = lark_v.validate(compact)
    has_errors = any(i.severity == "error" for i in lint_issues) or any(i.severity == "error" for i in lark_issues)
    return not has_errors, lint_issues, lark_issues

for i, req in enumerate(REQUESTS):
    print(f'\n=== TEST {i+1}: {req[:60]}... ===')

    # Check few-shot retrieval
    entries = fsr.search(req, top_k=2)
    num_fs = [e.numero for e in entries]
    print(f'Few-shot candidates: {num_fs}')
    for e in entries:
        print(f'  #{e.numero}: {e.scopoSuggerito[:60]} ({e.lunghezza}c, {len(e.tags)} tags)')

    # Try direct generation (will use LLM)
    result = fb._try_direct_generation(
        user_request=req,
        model='tencent/hy3:free',
        timeout=45,
        few_shot_section=fsr.format_few_shot_section(req, top_k=2),
        template_section='',
    )
    if result and result.get('success'):
        formula = result['formula']
        valid, lint, lark = validate(formula)
        print(f'SUCCESS: {len(formula)} chars, valid={valid}')
        print(f'Formula:\n{formula[:400]}')
        if not valid:
            errors = [x for x in list(lint)+list(lark) if x.severity == 'error']
            print(f'  Errors: {[e.message[:60] for e in errors[:3]]}')
        print(f'Placement: {result.get("placement", {}).get("aggancio", "?")[:80]}...')
    else:
        err = result.get('error', '?') if result else 'None'
        print(f'FAILED: {err[:120]}')
