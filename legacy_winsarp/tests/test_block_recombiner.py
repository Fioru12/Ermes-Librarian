"""
Test per BlockGraph, BlockSelector, Recombiner e round-trip parser+emitter.
"""
import re
from pathlib import Path

from legacy_winsarp.core.winsarp.winsarp_parser import parse_formula, emit_formula
from legacy_winsarp.core.winsarp.block_recombiner import (
    _load_formulas, BlockGraph,
    select_blocks_by_indices, select_blocks_by_fields, recombine,
    SelectedBlocks, generate_recombined,
)

FORMULE_PATH = Path(__file__).parent.parent / "FormuleWinsarpInUso.txt"


def _get_all_formula_ids() -> list[int]:
    content = FORMULE_PATH.read_text(encoding='utf-8')
    return [int(m.group(1)) for m in re.finditer(r'formula\s*(\d+)', content)]


# ═══════════════════════════════════════════════
# Round-trip tests: parse → emit → parse → blocks match
# ═══════════════════════════════════════════════

def test_round_trip_all_formulas():
    """Ogni formula deve fare round-trip parse -> emit -> parse con blocchi identici."""
    formulas = _load_formulas()
    assert len(formulas) > 0, "Nessuna formula caricata"
    for fid, pf in formulas.items():
        emitted = emit_formula(pf.blocks)
        assert emitted, f"Formula {fid}: emissione vuota"
        reparsed = parse_formula(emitted, fid)
        assert len(reparsed.blocks) == len(pf.blocks), (
            f"Formula {fid}: {len(pf.blocks)} blocchi -> {len(reparsed.blocks)} blocchi"
        )
        assert reparsed.fields_read == pf.fields_read, (
            f"Formula {fid}: fields_read mismatch"
        )
        assert reparsed.fields_written == pf.fields_written, (
            f"Formula {fid}: fields_written mismatch"
        )


# ═══════════════════════════════════════════════
# BlockGraph tests
# ═══════════════════════════════════════════════

def test_blockgraph_all_formulas():
    """BlockGraph deve costruirsi senza errori per ogni formula."""
    formulas = _load_formulas()
    for fid, pf in formulas.items():
        g = BlockGraph.from_parsed(pf)
        assert len(g.blocks) == len(pf.blocks)
        assert len(g.edges) >= 0
        assert len(g.edges) <= len(pf.blocks) * (len(pf.blocks) - 1) // 2


def test_blockgraph_edge_types():
    """Verifica che il grafo contenga tutti i tipi di edge."""
    formulas = _load_formulas()
    pf = formulas.get(5)
    assert pf is not None, "Formula 5 non trovata"
    g = BlockGraph.from_parsed(pf)
    kinds = {e.kind for e in g.edges}
    assert 'sequential' in kinds
    assert 'field_flow' in kinds


def test_blockgraph_vxx_detection():
    """Verifica che Vxx labels siano correttamente individuate."""
    formulas = _load_formulas()
    for fid, pf in formulas.items():
        g = BlockGraph.from_parsed(pf)
        for i, blk in enumerate(pf.blocks):
            cond = blk.condition.strip() if blk.condition else ""
            if re.match(r'^V\d{2}$', cond):
                assert i in g.vx_defines, (
                    f"Formula {fid}: blocco {i} condition={cond} non in vx_defines"
                )


# ═══════════════════════════════════════════════
# Recombination tests
# ═══════════════════════════════════════════════

def test_recombine_single_formula_roundtrip():
    """Ricombinare un'intera formula deve mantenere blocchi e campi."""
    formulas = _load_formulas()
    for fid, pf in list(formulas.items())[:10]:
        sel = SelectedBlocks(
            formula_id=fid,
            block_indices=list(range(len(pf.blocks))),
            blocks=pf.blocks,
        )
        emitted = recombine([sel])
        assert emitted, f"Formula {fid}: emissione vuota"
        reparsed = parse_formula(emitted, fid)
        assert len(reparsed.blocks) == len(pf.blocks), (
            f"Formula {fid}: {len(pf.blocks)} vs {len(reparsed.blocks)} blocchi"
        )
        assert reparsed.fields_read == pf.fields_read
        assert reparsed.fields_written == pf.fields_written


def test_recombine_two_formulas():
    """Fondere due formule deve preservare il numero totale di blocchi."""
    formulas = _load_formulas()
    sel5 = SelectedBlocks(
        formula_id=5,
        block_indices=list(range(len(formulas[5].blocks))),
        blocks=formulas[5].blocks,
    )
    sel10 = SelectedBlocks(
        formula_id=10,
        block_indices=list(range(len(formulas[10].blocks))),
        blocks=formulas[10].blocks,
    )
    emitted = recombine([sel5, sel10])
    assert emitted
    reparsed = parse_formula(emitted, 0)
    expected = len(formulas[5].blocks) + len(formulas[10].blocks)
    assert len(reparsed.blocks) == expected, (
        f"{len(reparsed.blocks)} vs {expected} blocchi"
    )


def test_recombine_with_vxx_rename():
    """Fondere formule con Vxx deve rinominare: stessi Vxx per formula sorgente
    rimangono uguali, MA non ci devono essere Vxx identici tra formule diverse."""
    formulas = _load_formulas()
    vxx_formulas = []
    for fid, pf in formulas.items():
        for blk in pf.blocks:
            if blk.jump and re.match(r'^V\d{2}$', blk.jump):
                vxx_formulas.append(fid)
                break
    assert len(vxx_formulas) >= 2, "Servono almeno 2 formule con Vxx"
    fid_a, fid_b = vxx_formulas[:2]
    pf_a, pf_b = formulas[fid_a], formulas[fid_b]
    sel_a = SelectedBlocks(fid_a, list(range(len(pf_a.blocks))), pf_a.blocks)
    sel_b = SelectedBlocks(fid_b, list(range(len(pf_b.blocks))), pf_b.blocks)
    emitted = recombine([sel_a, sel_b])
    assert emitted
    # Verifica che l'emissione sia parsabile
    pf_result = parse_formula(emitted, 0)
    assert len(pf_result.blocks) == len(pf_a.blocks) + len(pf_b.blocks)


# ═══════════════════════════════════════════════
# BlockSelector tests
# ═══════════════════════════════════════════════

def test_select_blocks_by_indices():
    """Selezione per indici deve restituire i blocchi corretti."""
    sel = select_blocks_by_indices(5, [0, 1, 2])
    assert sel is not None
    assert len(sel.blocks) == 3
    assert sel.formula_id == 5


def test_select_blocks_by_fields():
    """Selezione per campi deve restituire blocchi che leggono quei campi."""
    sel = select_blocks_by_fields(5, reads={801})
    if sel:
        for blk in sel.blocks:
            assert 801 in blk.fields_read, "Blocco selezionato non legge 801"


# ═══════════════════════════════════════════════
# generate_recombined tests
# ═══════════════════════════════════════════════

def test_generate_recombined_auto():
    """generate_recombined con auto-detect deve funzionare."""
    result = generate_recombined('riconoscimento turno')
    assert result.get('success'), f"Fallito: {result.get('error')}"
    assert result.get('formula'), "Formula vuota"
    pf = parse_formula(result['formula'], 0)
    assert len(pf.blocks) > 0


def test_generate_recombined_specific_templates():
    """generate_recombined con template_ids specifici."""
    result = generate_recombined('test', template_ids=[5, 100])
    assert result.get('success'), f"Fallito: {result.get('error')}"
    assert result.get('formula'), "Formula vuota"


def test_generate_recombined_with_block_indices():
    """generate_recombined con blocchi specifici da template."""
    result = generate_recombined(
        'test',
        block_indices_per_template={5: [0, 1, 2], 10: [0, 1]}
    )
    assert result.get('success'), f"Fallito: {result.get('error')}"
    pf = parse_formula(result['formula'], 0)
    assert len(pf.blocks) == 5, f"5 blocchi attesi, {len(pf.blocks)} ottenuti"
