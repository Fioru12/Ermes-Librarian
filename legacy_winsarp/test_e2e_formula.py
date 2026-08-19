"""
End-to-end test: NL richiesta -> formula WinSarp -> round-trip check.
"""
import sys
sys.path.insert(0, '.')
from legacy_winsarp.core.winsarp.block_recombiner import generate_recombined
from legacy_winsarp.core.winsarp.winsarp_parser import parse_formula, emit_formula

TEST_CASES = [
    "calcola straordinario per turno notturno",
    "fascia oraria mattino con pausa pranzo",
    "calcolo ore festive con maggiorazioni",
    "inizializzazione giornata e riconoscimento turno",
    "calcolo presenza con arrotondamento",
]

print("=" * 70)
print("END-TO-END TEST: NL -> FORMULA -> ROUND-TRIP")
print("=" * 70)

all_ok = True
for req in TEST_CASES:
    print(f"\n--- Richiesta: '{req}' ---")
    
    # Step 1: Generate
    result = generate_recombined(req)
    formula = result.get('formula')
    success = result.get('success', False)
    source = result.get('source', '?')
    explanation = result.get('explanation', '')
    
    print(f"  Source: {source}")
    
    if not formula:
        print(f"  ERROR: {result.get('error', 'Unknown error')}")
        all_ok = False
        continue
    
    print(f"  Formula ({len(formula)} chars):")
    for line in formula.split('\n')[:8]:
        print(f"    > {line[:100]}")
    
    # Step 2: Re-parse the formula (round-trip)
    try:
        pf = parse_formula(formula, 0)
        n_blocks = len(pf.blocks)
        n_actions = sum(len(b.actions) for b in pf.blocks)
        
        # Step 3: Re-emit
        re_emitted = emit_formula(pf.blocks)
        
        if not re_emitted:
            print(f"  FAIL: Re-emission returned None")
            all_ok = False
            continue
        
        # Compare normalized forms
        norm_orig = ' '.join(formula.split())
        norm_reemit = ' '.join(re_emitted.split())
        
        match = norm_orig == norm_reemit
        status = "OK" if match else "MISMATCH"
        
        print(f"  Round-trip: {n_blocks} blocks, {n_actions} actions -> {status}")
        
        if not match:
            print(f"  ORIG: {norm_orig[:120]}")
            print(f"  REEM: {norm_reemit[:120]}")
            all_ok = False
        
    except Exception as e:
        print(f"  FAIL: Parse error - {e}")
        all_ok = False

print("\n" + "=" * 70)
print(f"RESULT: {'ALL OK' if all_ok else 'SOME FAILURES'}")
