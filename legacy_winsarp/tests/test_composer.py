"""Test pattern composer - deterministic and LLM-based."""
import sys
sys.path.insert(0, '.')
from legacy_winsarp.core.winsarp.pattern_composer import find_best_pattern, compose_formula, _load_patterns

patterns = _load_patterns()
print(f'Loaded {len(patterns)} patterns\n')

# Test 1: find_best_pattern
tests = [
    'riconoscimento turno automatico per la giornata',
    'calcolo presenza con durata e causali',
    'gestione assenze su intervalli orari',
    'straordinario festivo',
    'esplodi causali automatiche',
    'primo giro con elaborazione completa',
    'secondo giro con accumuli e chiamate',
    'festivita non goduta',
    'maggiorazioni',
    'warning ore carenti',
]
for q in tests:
    result = find_best_pattern(q)
    if result:
        num, pt = result
        print(f'{q[:40]:40s} -> #{num:4d} ({pt.scopo[:35]}) tags={list(pt.tags)[:3]}')
    else:
        print(f'{q[:40]:40s} -> NONE')

# Test 2: compose_formula with params
print('\n=== Compose with params (turn detection) ===')
pattern5 = patterns[5]
params = {
    'turni': [
        {'nome': 'MATT', 'ora_inizio': "'07.00'", 'ora_fine': "'15.00'", 'flag': '1'},
        {'nome': 'POME', 'ora_inizio': "'15.00'", 'ora_fine': "'22.00'", 'flag': '2'},
    ]
}
adapted = compose_formula(pattern5, params)
print(f'Original: {len(pattern5.body)} chars')
print(f'Adapted:  {len(adapted)} chars')
print(f'Same? {pattern5.body == adapted}')
# Show first different line
orig_lines = pattern5.body.split('\n')
adapt_lines = adapted.split('\n')
for i, (o, a) in enumerate(zip(orig_lines, adapt_lines)):
    if o != a:
        print(f'  Diff line {i}:')
        print(f'    O: {o.strip()[:80]}')
        print(f'    A: {a.strip()[:80]}')

# Test 3: LLM parameter extraction
print('\n=== LLM parameter extraction ===')
from legacy_winsarp.core.winsarp.pattern_composer import extract_parameters_via_llm
params = extract_parameters_via_llm(
    'riconoscimento turno: se timbratura tra 7 e 14 assegna MATTINO con flag 1, tra 14 e 22 POMERIGGIO con flag 2',
    pattern5,
    timeout=30,
)
if params:
    print(f'Params found: {list(params.keys())}')
    for k, v in params.items():
        print(f'  {k}: {v}')
else:
    print('No params extracted (LLM failed)')

# Test 4: Full composition with params
print('\n=== Full composition ===')
if params:
    full = compose_formula(pattern5, params)
    print(f'Composed formula: {len(full)} chars')
    print(full[:400])
