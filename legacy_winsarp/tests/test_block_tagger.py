"""
Test per block_intent_tagger: classificazione blocchi, indice, ricerca.
"""
from legacy_winsarp.core.winsarp.block_intent_tagger import (
    classify_block, get_index, reset_index, BlockIntentIndex,
    INTENT_FASCIA_ORARIA, INTENT_INIT, INTENT_CAUSALE_CHECK, INTENT_STRAORDINARIO, INTENT_FINALE,
    INTENT_FLAG_CHECK, INTENT_LABEL,
)
from legacy_winsarp.core.winsarp.winsarp_parser import Block, Op, Value
from legacy_winsarp.core.winsarp.block_recombiner import _load_formulas


def test_classify_label():
    """Vxx standalone deve essere classificato come label."""
    blk = Block(condition='V05')
    assert INTENT_LABEL in classify_block(blk)


def test_classify_init():
    """Reset-only senza condizione deve essere inizializzazione."""
    blk = Block(actions=[Op('RESET', 900), Op('RESET', 801)])
    assert INTENT_INIT in classify_block(blk)


def test_classify_fascia_oraria():
    """Blocco con condizione 801 e set 58/111/141 deve essere fascia_oraria."""
    blk = Block(
        condition="{ 801 } > U '04.00' E { 801 } < U '09.00'",
        actions=[
            Op('SET', 58, Value('literal', 'MATT')),
            Op('SET', 111, Value('literal', '06')),
            Op('SET', 141, Value('literal', '14')),
        ],
        fields_read={801},
        fields_written={58, 111, 141},
    )
    assert INTENT_FASCIA_ORARIA in classify_block(blk)


def test_classify_accumulo_k():
    """Blocco con operazione ADD su K-register (non-K90x) deve essere accumulo_k."""
    blk = Block(
        actions=[Op('ADD', 'K803', Value('literal', '24'))],
    )
    intents = classify_block(blk)
    assert any(i.startswith('accumulo_k') for i in intents), f"Got {intents}"


def test_classify_accumulo_k_not_straordinario():
    """K803 non deve essere straordinario (solo K90x lo è)."""
    blk = Block(
        actions=[Op('ADD', 'K803', Value('literal', '24'))],
    )
    intents = classify_block(blk)
    assert 'calcolo_straordinario' not in intents, f"Got {intents}"


def test_classify_straordinario_k90():
    """K903 deve essere straordinario."""
    blk = Block(
        actions=[Op('ADD', 'K903', Value('literal', '24'))],
    )
    intents = classify_block(blk)
    assert 'calcolo_straordinario' in intents, f"Got {intents}"


def test_classify_chiamata():
    """Blocco con jump R NNN deve essere chiamata_formula."""
    blk = Block(jump='R 110')
    intents = classify_block(blk)
    assert any(i.startswith('chiamata_formula') for i in intents)


def test_classify_chiamata_p():
    """Blocco con jump P NNN deve essere chiamata_formula."""
    blk = Block(jump='P 2122')
    intents = classify_block(blk)
    assert any(i.startswith('chiamata_formula') for i in intents)


def test_classify_flag_check():
    """Blocco con condizione 50 U deve essere flag_check."""
    blk = Block(condition='50 U I')
    assert INTENT_FLAG_CHECK in classify_block(blk)


def test_classify_causale_check():
    """Blocco con condizione su 58 deve essere causale_check."""
    blk = Block(condition='58 U "RIPO"', jump='VF')
    assert INTENT_CAUSALE_CHECK in classify_block(blk)


def test_classify_straordinario():
    """Blocco con K90x deve essere calcolo_straordinario."""
    blk = Block(
        condition="782 <= 887 E 811 <= '06.00'",
        actions=[Op('ADD', 'K903')],
    )
    assert INTENT_STRAORDINARIO in classify_block(blk)


def test_classify_finale():
    """Blocco con POINTER_DEC deve essere finale_giornata."""
    blk = Block(
        actions=[Op('POINTER_DEC', 'K770', Value('indefinito', 'I'))],
    )
    assert INTENT_FINALE in classify_block(blk)


def test_index_build():
    """L'indice deve coprire almeno il 90% dei blocchi."""
    reset_index()
    index = BlockIntentIndex()
    formulas = _load_formulas()
    index.build(formulas)
    total = len(index.entries)
    known = sum(1 for e in index.entries if e.intents != ['sconosciuto'])
    assert known / total >= 0.90, f"Solo {known}/{total} blocchi classificati ({known/total*100:.1f}%)"


def test_index_search():
    """Ricerca per intento deve restituire blocchi pertinenti."""
    reset_index()
    index = get_index()
    results = index.search("fascia oraria mattino", top_k=5)
    assert len(results) > 0
    assert any(INTENT_FASCIA_ORARIA in e.intents for e in results)


def test_index_search_straordinario():
    """Ricerca 'straordinario' deve trovare blocchi K90x."""
    reset_index()
    index = get_index()
    results = index.search("straordinario", top_k=5)
    assert len(results) > 0
    assert any(INTENT_STRAORDINARIO in e.intents for e in results)


def test_index_get_blocks_by_intent():
    """get_blocks deve restituire tutti i blocchi per un intento."""
    reset_index()
    index = get_index()
    fascia_blocks = index.get_blocks(INTENT_FASCIA_ORARIA)
    assert len(fascia_blocks) >= 3, f"Solo {len(fascia_blocks)} blocchi fascia_oraria trovati"


def test_index_unique_intents():
    """L'indice deve avere almeno 20 intenti unici."""
    reset_index()
    index = get_index()
    intents = index.get_all_intents()
    assert len(intents) >= 20, f"Solo {len(intents)} intenti"


def test_classify_coverage_all_formulas():
    """Verifica coverage su TUTTE le formule."""
    reset_index()
    index = BlockIntentIndex()
    formulas = _load_formulas()
    index.build(formulas)
    unknown = [e for e in index.entries if e.intents == ['sconosciuto']]
    coverage = 1 - len(unknown) / len(index.entries)
    # Print unknown blocks for debugging
    if unknown:
        print(f"\n{len(unknown)} unknown blocks:")
        for e in unknown[:10]:
            print(f"  F{e.formula_id}[{e.block_index}]: cond=[{e.cond_summary[:60]}]")
    assert coverage >= 0.95, f"Coverage too low: {coverage*100:.1f}%"
