"""
block_intent_tagger.py
Classificatore deterministico di blocchi WinSarp basato su pattern strutturali.
Assegna a ogni blocco uno o piu' intenti (fascia_oraria, accumulo_k, reset, ...)
senza bisogno di LLM.

Usato dal BlockRecombiner per selezionare SOLO i blocchi rilevanti.
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field

from legacy_winsarp.core.winsarp.winsarp_parser import Block, Op, ParsedFormula

_logger = logging.getLogger(__name__)

# ─────── Intent categories ───────

INTENT_LABEL = "label"
INTENT_INIT = "inizializzazione"
INTENT_FASCIA_ORARIA = "fascia_oraria"
INTENT_CAUSALE_CHECK = "causale_check"
INTENT_FLAG_CHECK = "flag_check"
INTENT_ACCUMULO_K = "accumulo_k"
INTENT_CALCOLO_CAMPO = "calcolo_campo"
INTENT_CHIAMATA = "chiamata_formula"
INTENT_PAUSA = "calcolo_pausa"
INTENT_STRAORDINARIO = "calcolo_straordinario"
INTENT_ARROTONDAMENTO = "arrotondamento"
INTENT_CAMPO70 = "campo70"
INTENT_FINALE = "finale_giornata"
INTENT_CAUSALI_ESPLOSE = "causali_esplose"
INTENT_CALCOLO_PRESENZA = "calcolo_presenza"
INTENT_RITOCCO_SB_SA = "ritocco_sb_sa"
INTENT_AVISPA = "avispa"
INTENT_INDICATORI = "set_indicatori"
INTENT_CONDIZIONE = "condizione_semplice"
INTENT_UNKNOWN = "sconosciuto"

# ─────── Block intent classification ───────

def _has_any_field(blk: Block, fields: set[int]) -> bool:
    """Check if block reads or writes any of the given fields."""
    return bool(blk.fields_read & fields) or bool(blk.fields_written & fields)

def _condition_has(cond: str, *patterns: str) -> bool:
    """Check if condition matches any of the patterns."""
    if not cond:
        return False
    return any(p in cond for p in patterns)

def _ops_of_type(blk: Block, op_type: str) -> list[Op]:
    return [o for o in blk.actions if o.op_type == op_type]

def _has_k_op(blk: Block) -> bool:
    return any(isinstance(o.field, str) and o.field.startswith('K') for o in blk.actions)

def _has_k_op_with_range(blk: Block, prefix: str) -> bool:
    return any(
        isinstance(o.field, str) and o.field.startswith(prefix) and o.op_type in ('ADD', 'SUB')
        for o in blk.actions
    )

def _is_label_block(blk: Block) -> bool:
    cond = blk.condition.strip() if blk.condition else ""
    return bool(
        re.match(r'^V\d{2}$', cond) and not blk.actions and not blk.jump
    )

def _is_vf_label(blk: Block) -> bool:
    cond = blk.condition.strip() if blk.condition else ""
    return cond == 'VF' and not blk.actions and not blk.jump

def _is_formula_reference(cond: str) -> int | None:
    """Check if condition is a formula reference like 'formula 3014'."""
    m = re.match(r'^formula\s+(\d+)$', cond.strip().lower())
    return int(m.group(1)) if m else None

def classify_block(blk: Block) -> list[str]:
    """Assegna uno o piu' intenti a un blocco basandosi su pattern deterministici.
    Restituisce lista ordinata per specificità (primo = più specifico)."""
    cond = blk.condition.strip() if blk.condition else ""
    jump = blk.jump.strip() if blk.jump else ""
    n_ops = len(blk.actions)
    intents: list[str] = []

    # 1. Label pura (Vxx standalone)
    if _is_label_block(blk):
        return [INTENT_LABEL]
    if _is_vf_label(blk):
        return [INTENT_LABEL]
    ref = _is_formula_reference(cond)
    if ref:
        intents.append(f"riferimento_formula_{ref}")

    # 2. Chiamata formula (R NNN / P NNN)
    if jump and re.match(r'^[RP]\s+\d+$', jump):
        call_type = 'R' if jump.startswith('R') else 'P'
        call_num = jump.split()[1]
        intents.append(f"{INTENT_CHIAMATA}_{call_type}{call_num}")

    # 3. Reset-only (inizializzazione)
    if n_ops > 0 and all(o.op_type == 'RESET' for o in blk.actions) and not cond:
        intents.append(INTENT_INIT)
        return intents if intents else [INTENT_INIT]

    # 4. Reset with condition (reset condizionale)
    if n_ops > 0 and all(o.op_type == 'RESET' for o in blk.actions) and cond:
        intents.append(INTENT_INIT)
        intents.append(INTENT_CONDIZIONE)

    # 5. Flag check
    if cond and ('50 U' in cond or '55 U' in cond or '50 #' in cond):
        intents.append(INTENT_FLAG_CHECK)
        if '50 U I' in cond:
            intents.append(f"{INTENT_FLAG_CHECK}_festivo")
        if '55 U I' in cond:
            intents.append(f"{INTENT_FLAG_CHECK}_festivo")

    # 6. Causale check (58 in condizione)
    if cond and '58' in cond and (' U ' in cond or ' = ' in cond):
        causale_match = re.search(r"58\s+U\s+'([^']+)'", cond)
        if causale_match:
            intents.append(f"{INTENT_CAUSALE_CHECK}_{causale_match.group(1)}")
        else:
            intents.append(INTENT_CAUSALE_CHECK)

    # 7. Fascia oraria (time range on 801/84/73)
    is_time_range = False
    if cond and ('801' in cond or '84' in cond):
        if _has_any_field(blk, {58, 111, 112, 141, 142, 900}):
            intents.append(INTENT_FASCIA_ORARIA)
            is_time_range = True
            # Sub-classify by causale
            for act in blk.actions:
                if act.field == 58 and act.value and act.value.kind == 'literal':
                    intents.append(f"{INTENT_FASCIA_ORARIA}_{act.value.value}")

    # 8. Arrotondamento (campo 73 con soglie 15/30/45/59)
    if cond and '73' in cond and ('<' in cond or '<=' in cond):
        if "'15" in cond or "'30" in cond or "'45" in cond or "'59" in cond:
            intents.append(INTENT_ARROTONDAMENTO)
            # Also check if it has campo70 setup
            if _has_any_field(blk, {70, 71}):
                intents.append(INTENT_CAMPO70)

    # 9. CAMPO70 (SET 71, SET 70 pattern)
    if _has_any_field(blk, {70, 71}) and not is_time_range:
        if any(o.field == 70 for o in blk.actions) or any(o.field == 71 for o in blk.actions):
            intents.append(INTENT_CAMPO70)

    # 10. Straordinario (K900-K910 only; K800-K809 are normal accumulators)
    if _has_k_op_with_range(blk, 'K90'):
        intents.append(INTENT_STRAORDINARIO)
    if _has_any_field(blk, {887, 889, 1391}):
        if cond and ('887' in cond or '889' in cond or '1391' in cond):
            intents.append(INTENT_STRAORDINARIO)

    # 11. Calcolo pausa (fields 251,252,271,272, 390 check)
    if _has_any_field(blk, {251, 252, 271, 272}):
        intents.append(INTENT_PAUSA)

    # 12. Accumulo K (K-register ADD/SUB, esclusi K90x che sono straordinario)
    if _has_k_op(blk):
        has_straord = any(
            isinstance(o.field, str) and o.field.startswith('K90')
            for o in blk.actions
        )
        if not has_straord:
            # Check for hour accumulators (K601-K630) and other totals
            k_regs = [o.field for o in blk.actions if isinstance(o.field, str) and o.field.startswith('K')]
            for k in k_regs:
                intents.append(f"{INTENT_ACCUMULO_K}_{k}")
        # Also check for presence accumulation (K3, K4, K5)
        if any(o.field in ('K3', 'K4', 'K5') for o in blk.actions):
            intents.append(INTENT_CALCOLO_PRESENZA)

    # 13. Finale giornata (K770 pointer ops, 1801)
    if any(o.op_type in ('POINTER_INC', 'POINTER_DEC') for o in blk.actions):
        intents.append(INTENT_FINALE)
    if _has_any_field(blk, {1801}):
        intents.append(INTENT_FINALE)

    # 14. Ritocco SB/SA (fields 2114, 3014, 915, 907)
    if _has_any_field(blk, {2114, 3014, 915, 907}):
        intents.append(INTENT_RITOCCO_SB_SA)

    # 15. Causali esplose (501-510, 561-570)
    if _has_any_field(blk, {501, 502, 503, 504, 505, 506, 507, 508, 509, 510}):
        intents.append(INTENT_CAUSALI_ESPLOSE)
    if _has_any_field(blk, {561, 562, 563, 564, 565, 566, 567, 568, 569, 570}):
        intents.append(INTENT_CAUSALI_ESPLOSE)

    # 16. Calcolo campo composto (SUB/ADD with 2 values on same field)
    compound_ops = _ops_of_type(blk, 'SUB') + _ops_of_type(blk, 'ADD')
    if len(compound_ops) >= 2:
        same_fields = all(o.field == compound_ops[0].field for o in compound_ops)
        if same_fields and isinstance(compound_ops[0].field, int):
            intents.append(INTENT_CALCOLO_CAMPO)

    # 17. Set indicatori (111, 112, 141, 142, senza 801 time range)
    if _has_any_field(blk, {111, 112, 141, 142}) and INTENT_FASCIA_ORARIA not in intents:
        intents.append(INTENT_INDICATORI)

    # 18. Calcolo presenza (ADD on 3, 4, 5)
    if _has_any_field(blk, {3, 4, 5}):
        if any(o.op_type in ('ADD', 'SUB') for o in blk.actions):
            intents.append(INTENT_CALCOLO_PRESENZA)

    # 19. Avispa (field 2115 specific reference)
    if _has_any_field(blk, {2115, 3015}):
        intents.append(INTENT_AVISPA)

    # 20. Condizione con jump (es. "800 U 200 ( VF" — condizione passante)
    if cond and not blk.actions and jump:
        intents.append(f"cond_{jump}")

    # 21. Check passaggio (300, 301, 200 fields — primo/secondo giro)
    if cond and _has_any_field(blk, {200, 300, 301, 302, 311}):
        intents.append("check_passaggio")

    # 22. Check orario/pausa (390 # Z, 201, 221, 802, 803 time checks)
    if cond:
        if '390' in cond and '#' in cond:
            intents.append("check_pausa_390")
        if '201' in cond or '221' in cond:
            intents.append("check_fasce_orarie")
        if _has_any_field(blk, {802, 803}) and 'U Z' in cond:
            intents.append("check_presenza_timbratura")

    # 23. Condizione su campo specifico (senza altra classificazione, con jump)
    if cond and jump and not blk.actions:
        if intents == [f"cond_{jump}"]:  # only this intent
            pass  # keep it

    # 24. Set field generico (SET senza altra classificazione)
    if n_ops > 0:
        # Simple SET operations
        if all(o.op_type == 'SET' for o in blk.actions) and not intents:
            fields_str = '_'.join(str(o.field) for o in blk.actions[:3])
            intents.append(f"set_{fields_str}")

    # 25. Condizione semplice (condition only, no actions, no jump)
    if cond and not blk.actions and not jump and not _is_label_block(blk):
        intents.append(INTENT_CONDIZIONE)

    # 26. Condizione su presenza dati (802/803 con # Z)
    if cond and _has_any_field(blk, {802, 803, 804}):
        if '#' in cond or 'U Z' in cond:
            intents.append("check_timbratura")

    # 27. Riavvio catena (K770 ± I)
    if any(o.op_type in ('POINTER_INC', 'POINTER_DEC') for o in blk.actions):
        if any(isinstance(o.field, str) and o.field == 'K770' for o in blk.actions):
            intents.append("avanza_giro")

    # 28. Formula call without condition (bare R NNN / P NNN)
    if not cond and not n_ops and jump and re.match(r'^[RP]\s+\d+$', jump):
        intents.append(INTENT_CHIAMATA)

    # 29. UNKNOWN pattern specific: SET(71) + SET(70) was already handled;
    #     also cover RESET+SET combo (e.g., SET(902); RESET(800))
    if _has_any_field(blk, {902, 903, 904, 905, 906, 907, 908, 909, 910, 914}):
        if any(o.op_type == 'SET' for o in blk.actions):
            intents.append("set_campo_maggiorazione")

    if not intents:
        intents.append(INTENT_UNKNOWN)

    return intents


# ─────── Intent index ───────

@dataclass
class BlockEntry:
    formula_id: int
    block_index: int
    block: Block
    intents: list[str] = field(default_factory=list)
    cond_summary: str = ""

class BlockIntentIndex:
    """Index that maps intent categories to block entries."""

    def __init__(self):
        self.entries: list[BlockEntry] = []
        self.intent_map: dict[str, list[int]] = {}  # intent → indices into self.entries
        self._built = False

    def build(self, formulas: dict[int, ParsedFormula] | None = None):
        """Build index from all parsed formulas."""
        if formulas is None:
            from legacy_winsarp.core.winsarp.block_recombiner import _load_formulas
            formulas = _load_formulas()
        self.entries = []
        self.intent_map = {}

        for fid, pf in formulas.items():
            for bidx, blk in enumerate(pf.blocks):
                intents = classify_block(blk)
                entry = BlockEntry(
                    formula_id=fid,
                    block_index=bidx,
                    block=blk,
                    intents=intents,
                    cond_summary=blk.condition[:60] if blk.condition else "",
                )
                idx = len(self.entries)
                self.entries.append(entry)
                for intent in intents:
                    self.intent_map.setdefault(intent, []).append(idx)

        self._built = True
        _logger.info(
            "BlockIntentIndex built: %d entries, %d unique intents",
            len(self.entries), len(self.intent_map)
        )

    def get_blocks(self, intent: str) -> list[BlockEntry]:
        """Get all blocks that match a given intent."""
        if not self._built:
            self.build()
        indices = self.intent_map.get(intent, [])
        return [self.entries[i] for i in indices]

    def search(self, query: str, top_k: int = 5) -> list[BlockEntry]:
        """Find blocks by matching query keywords to intents."""
        if not self._built:
            self.build()
        query_lower = query.lower()
        words = set(query_lower.split())

        # Keyword → intent/field mappings for WinSarp concepts
        SEMANTIC_MAP = {
            'mattino': 'matt', 'matt': 'matt',
            'pomeriggio': 'pome', 'pome': 'pome',
            'notturno': 'nott', 'notte': 'nott', 'nott': 'nott',
            'straordinario': 'straordinario', 'straord': 'straordinario',
            'festivo': 'festivo', 'festa': 'festivo',
            'festiva': 'festivo', 'festive': 'festivo', 'festivi': 'festivo',
            'domenica': 'festivo', 'domenicale': 'festivo',
            'pausa': 'pausa', 'pranzo': 'pausa',
            'resetta': 'reset', 'azzera': 'reset',
            'causale': 'causale', 'causali': 'causale',
            'turno': 'turno', 'turni': 'turno',
            'presenza': 'presenza',
            'arrotonda': 'arrotondamento', 'arrotondamento': 'arrotondamento',
            'flag': 'flag',
            'inizializza': 'inizializzazione',
            'finale': 'finale',
            'maggiorazione': 'maggiorazione', 'maggiorazioni': 'maggiorazione',
            'maggiorata': 'maggiorazione',
            'chiamata': 'chiamata', 'chiamate': 'chiamata',
            'soglia': 'soglia',
            'autorizzazione': 'autorizzazione',
            'carenti': 'carenti',
            'annuali': 'annuali',
            'dichiarazione': 'presenza',
        }

        # Build a stem set: strip last 1-2 chars for Italian plural/gender matching
        def _stem(w: str) -> str:
            if len(w) <= 3:
                return w
            for suffix in ['e', 'i', 'a', 'o']:
                if w.endswith(suffix):
                    return w[:-1]
            return w

        # Expand query with semantic mappings + stems
        expanded = set(words)
        for word in words:
            if word in SEMANTIC_MAP:
                expanded.add(SEMANTIC_MAP[word])
        # Also add stems
        stems = {_stem(w) for w in words} | {_stem(w) for w in expanded}
        expanded.update(stems)
        # Add all stems from semantic map values too
        for val in SEMANTIC_MAP.values():
            if _stem(val) != val:
                expanded.add(_stem(val))

        # Score each entry
        scored: list[tuple[float, int]] = []
        for idx, entry in enumerate(self.entries):
            score = 0.0
            intent_text = ' '.join(entry.intents).lower()

            for word in expanded:
                if word in intent_text:
                    score += 2.0
                if word.isdigit() and word in intent_text:
                    score += 3.0

            cond_lower = entry.cond_summary.lower()
            for word in expanded:
                if word in cond_lower:
                    score += 1.0

            if score > 0:
                scored.append((score, idx))

        scored.sort(key=lambda x: -x[0])
        return [self.entries[i] for _, i in scored[:top_k]]

    def get_all_intents(self) -> list[str]:
        """List all available intent categories."""
        if not self._built:
            self.build()
        return sorted(self.intent_map.keys())

    def count_by_formula(self, fid: int) -> dict[str, int]:
        """Count intents per formula."""
        if not self._built:
            self.build()
        counts: dict[str, int] = {}
        for entry in self.entries:
            if entry.formula_id == fid:
                for intent in entry.intents:
                    counts[intent] = counts.get(intent, 0) + 1
        return counts


# ─────── Singleton ───────

_INDEX: BlockIntentIndex | None = None

def get_index() -> BlockIntentIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = BlockIntentIndex()
        _INDEX.build()
    return _INDEX

def reset_index():
    global _INDEX
    _INDEX = None
