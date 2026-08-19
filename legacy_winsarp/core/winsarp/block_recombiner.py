"""
block_recombiner.py
Ricombinazione blocchi WinSarp: BlockGraph, BlockSelector, Recombiner.
Prende blocchi da formule diverse, risolve conflitti Vxx, emette formula compatta.
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from legacy_winsarp.core.winsarp.winsarp_parser import (
    parse_formula, Block, ParsedFormula, emit_formula, _is_vxx,
)
from legacy_winsarp.core.winsarp.field_flow_checker import FieldFlowChecker

_logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
# BlockGraph — per-formula block dependency graph
# ═══════════════════════════════════════════════

@dataclass
class Edge:
    source: int
    target: int
    kind: str  # 'field_flow', 'jump', 'sequential'

@dataclass
class BlockGraph:
    formula_id: int
    blocks: list[Block]
    edges: list[Edge] = field(default_factory=list)
    # Block index → set of Vxx labels it DEFINES
    vx_defines: dict[int, set[str]] = field(default_factory=dict)
    # Block index → Vxx label it JUMPS to
    vx_jumps: dict[int, str | None] = field(default_factory=dict)

    @staticmethod
    def from_parsed(pf: ParsedFormula) -> BlockGraph:
        g = BlockGraph(formula_id=pf.id, blocks=pf.blocks)
        n = len(pf.blocks)

        for i, blk in enumerate(pf.blocks):
            # Vxx defines
            if blk.condition and _is_vxx(blk.condition.strip()):
                g.vx_defines.setdefault(i, set()).add(blk.condition.strip())
            # Vxx jump targets
            if blk.jump and _is_vxx(blk.jump):
                g.vx_jumps[i] = blk.jump

        # Sequential edges (block[i] → block[i+1])
        for i in range(n - 1):
            # Break sequential if block i has a jump (no fall-through)
            if pf.blocks[i].jump and not _is_vxx(pf.blocks[i].jump):
                continue  # jump is R/P — no sequential fallthrough
            g.edges.append(Edge(i, i + 1, 'sequential'))

        # Field flow edges (producer → consumer)
        for i in range(n):
            for j in range(i + 1, n):
                written = pf.blocks[i].fields_written
                read = pf.blocks[j].fields_read
                shared = written & read
                if shared:
                    g.edges.append(Edge(i, j, 'field_flow'))

        # Jump target edges (jumper → label definer)
        for jumper_idx, target_label in g.vx_jumps.items():
            if not target_label:
                continue
            for definer_idx, label_set in g.vx_defines.items():
                if target_label in label_set:
                    g.edges.append(Edge(jumper_idx, definer_idx, 'jump'))
                    break
            # Also check all blocks that might be reachable after the label

        return g

    def get_field_chain(self, field: int) -> list[int]:
        """Return block indices that read/write a field, in execution order."""
        result = []
        for i, blk in enumerate(self.blocks):
            if field in blk.fields_read or field in blk.fields_written:
                result.append(i)
        return result

    def get_subgraph(self, block_indices: set[int]) -> BlockGraph:
        """Extract subgraph containing only the given block indices."""
        filtered = [b for i, b in enumerate(self.blocks) if i in block_indices]
        new_g = BlockGraph(formula_id=self.formula_id, blocks=filtered)
        # Re-index edges
        old_to_new = {old: new for new, old in enumerate(sorted(block_indices))}
        for e in self.edges:
            if e.source in old_to_new and e.target in old_to_new:
                new_g.edges.append(Edge(old_to_new[e.source], old_to_new[e.target], e.kind))
        for old_i, labels in self.vx_defines.items():
            if old_i in old_to_new:
                new_g.vx_defines[old_to_new[old_i]] = labels
        for old_i, target in self.vx_jumps.items():
            if old_i in old_to_new:
                new_g.vx_jumps[old_to_new[old_i]] = target
        return new_g


# ═══════════════════════════════════════════════
# FormulaCache — parse all formulas once
# ═══════════════════════════════════════════════

_formula_cache: dict[int, ParsedFormula] = {}
_graph_cache: dict[int, BlockGraph] = {}

def _load_formulas() -> dict[int, ParsedFormula]:
    if _formula_cache:
        return _formula_cache
    from pathlib import Path
    p = Path("FormuleWinsarpInUso.txt")
    if not p.exists():
        _logger.warning("FormuleWinsarpInUso.txt not found")
        return {}
    content = p.read_text(encoding='utf-8')
    for m in re.finditer(r'formula\s*(\d+)\s*\n(.*?)(?=\nformula\s|\Z)', content, re.DOTALL):
        fid = int(m.group(1))
        body = m.group(2).strip()
        try:
            pf = parse_formula(body, fid)
            _formula_cache[fid] = pf
            _graph_cache[fid] = BlockGraph.from_parsed(pf)
        except Exception as e:
            _logger.warning("Parse error formula %d: %s", fid, e)
    _logger.info("Loaded %d formulas into cache", len(_formula_cache))
    return _formula_cache


# ═══════════════════════════════════════════════
# BlockSelector — extract relevant blocks
# ═══════════════════════════════════════════════

@dataclass
class SelectedBlocks:
    formula_id: int
    block_indices: list[int]
    blocks: list[Block]
    scope: str = ""

def select_blocks_by_indices(formula_id: int, indices: list[int]) -> SelectedBlocks | None:
    """Select specific blocks by their indices."""
    formulas = _load_formulas()
    pf = formulas.get(formula_id)
    if not pf:
        return None
    blocks = [pf.blocks[i] for i in indices if i < len(pf.blocks)]
    if not blocks:
        return None
    return SelectedBlocks(formula_id=formula_id, block_indices=indices, blocks=blocks)

def select_blocks_by_scope(formula_id: int, scope: str) -> SelectedBlocks | None:
    """Select blocks by semantic scope tag from few-shot entries."""
    from legacy_winsarp.core.winsarp.few_shot_retriever import FewShotRetriever
    fsr = FewShotRetriever()
    entry = fsr.entries.get(formula_id)
    if not entry or not entry.tags:
        return None
    # Check if the entry has relevant tags
    if scope not in entry.tags and scope not in str(entry.tags):
        return None
    formulas = _load_formulas()
    pf = formulas.get(formula_id)
    if not pf:
        return None
    return SelectedBlocks(
        formula_id=formula_id,
        block_indices=list(range(len(pf.blocks))),
        blocks=pf.blocks,
        scope=scope,
    )

def select_blocks_by_fields(formula_id: int, reads: set[int] | None = None,
                             writes: set[int] | None = None) -> SelectedBlocks | None:
    """Select blocks that read or write specific fields."""
    formulas = _load_formulas()
    pf = formulas.get(formula_id)
    if not pf:
        return None
    indices = []
    for i, blk in enumerate(pf.blocks):
        if reads and (blk.fields_read & reads):
            indices.append(i)
        elif writes and (blk.fields_written & writes):
            indices.append(i)
    if not indices:
        return None
    return SelectedBlocks(
        formula_id=formula_id,
        block_indices=list(sorted(set(indices))),
        blocks=[pf.blocks[i] for i in sorted(set(indices))],
        scope=f"fields_r{reads}_w{writes}",
    )


# ═══════════════════════════════════════════════
# Recombiner — merge blocks with Vxx renaming
# ═══════════════════════════════════════════════

def _find_vxx_labels(blocks: list[Block]) -> tuple[set[str], set[str]]:
    """Return (used_labels, defined_labels) in a list of blocks."""
    used = set()
    defined = set()
    for blk in blocks:
        if blk.jump and _is_vxx(blk.jump):
            used.add(blk.jump)
        if blk.condition and _is_vxx(blk.condition.strip()):
            defined.add(blk.condition.strip())
        # Handle Vxx in actions (unlikely but possible)
    return used, defined

def _find_vf_vu(blocks: list[Block]) -> list[str]:
    """Return VF/VU jumps found in blocks."""
    result = []
    for blk in blocks:
        if blk.jump in ('VF', 'VU'):
            result.append(blk.jump)
    return result

def _rename_vxx(blocks: list[Block], source_prefix: str, target_prefix: str) -> list[Block]:
    """Rename Vxx labels in a list of blocks."""
    result = []
    for blk in blocks:
        new_cond = blk.condition
        new_jump = blk.jump
        if new_cond and _is_vxx(new_cond.strip()):
            new_cond = new_cond.replace(source_prefix, target_prefix)
        if new_jump and _is_vxx(new_jump):
            new_jump = new_jump.replace(source_prefix, target_prefix)
        result.append(Block(
            condition=new_cond or "",
            actions=list(blk.actions),
            jump=new_jump,
            fields_read=set(blk.fields_read),
            fields_written=set(blk.fields_written),
        ))
    return result

def recombine(
    selections: list[SelectedBlocks],
    base_formula_id: int | None = None,
) -> str | None:
    """Merge blocks from multiple formula selections into one formula.

    1. Deduplicate blocks across selections (by condition+actions+jump)
    2. Rename Vxx to avoid conflicts between source formulas
    3. Preserve VF/VU as terminal jumps
    4. Field flow check only CROSS-formula (intra-formula order preserved)
    5. Emit as compact WinSarp
    """
    if not selections:
        return None

    # Deduplicate across selections by (cond, jump, actions_hash)
    seen: set[tuple] = set()
    deduped_selections: list[SelectedBlocks] = []
    for sel in selections:
        unique_indices: list[int] = []
        unique_blocks: list[Block] = []
        for idx, blk in zip(sel.block_indices, sel.blocks):
            key = (blk.condition or '', blk.jump or '',
                   tuple((a.op_type, str(a.field), str(a.value)) for a in blk.actions))
            if key not in seen:
                seen.add(key)
                unique_indices.append(idx)
                unique_blocks.append(blk)
        if unique_blocks:
            deduped_selections.append(SelectedBlocks(
                formula_id=sel.formula_id,
                block_indices=unique_indices,
                blocks=unique_blocks,
                scope=sel.scope,
            ))

    # Assign a unique Vxx range prefix per source formula
    combined_blocks: list[Block] = []
    vxx_counter = 1
    seen_jumps: set[str] = set()

    for sel in deduped_selections:
        blocks = sel.blocks
        used, defined = _find_vxx_labels(blocks)

        if not used and not defined:
            combined_blocks.extend(blocks)
            continue

        all_vxx = used | defined
        existing_numbers = sorted(
            int(v[1:]) for v in all_vxx if v.startswith('V') and v[1:].isdigit()
        )
        if not existing_numbers:
            combined_blocks.extend(blocks)
            continue

        rename_map: dict[str, str] = {}
        for old_num in existing_numbers:
            old_label = f"V{old_num:02d}"
            new_label = f"V{vxx_counter:02d}"
            vxx_counter += 1
            rename_map[old_label] = new_label

        for blk in blocks:
            new_cond = blk.condition
            new_jump = blk.jump
            for old_lbl, new_lbl in rename_map.items():
                if new_cond and old_lbl in new_cond:
                    new_cond = new_cond.replace(old_lbl, new_lbl)
                if new_jump and old_lbl in new_jump:
                    new_jump = new_jump.replace(old_lbl, new_lbl)
            combined_blocks.append(Block(
                condition=new_cond or "",
                actions=list(blk.actions),
                jump=new_jump,
                fields_read=set(blk.fields_read),
                fields_written=set(blk.fields_written),
            ))

    # Field flow check: only CROSS-formula dependencies
    if len(deduped_selections) > 1:
        sorted_blocks, flow_warnings = _cross_formula_sort(
            combined_blocks, deduped_selections
        )
    else:
        sorted_blocks = combined_blocks
        flow_warnings = FieldFlowChecker._orphan_check(combined_blocks)

    if flow_warnings:
        for w in flow_warnings:
            _logger.info("Field flow: %s", w)

    # Emit
    try:
        emitted = emit_formula(sorted_blocks)
        if not emitted:
            return None
        return emitted
    except Exception as e:
        _logger.error("Emission error: %s", e)
        return None


def _cross_formula_sort(
    combined_blocks: list[Block],
    selections: list[SelectedBlocks],
) -> tuple[list[Block], list[str]]:
    """Sort blocks across formulas respecting field dependencies.

    Preserves intra-formula block order; only reorders across formulas.
    """
    from collections import defaultdict, deque

    # Build per-selection field read/write summaries
    sel_written: list[set[int | str]] = [set() for _ in selections]
    sel_read: list[set[int | str]] = [set() for _ in selections]
    from legacy_winsarp.core.winsarp.field_flow_checker import _k_regs_written, _k_regs_read

    offset = 0
    for sel_idx, sel in enumerate(selections):
        for blk in sel.blocks:
            sel_written[sel_idx].update(blk.fields_written)
            sel_written[sel_idx].update(_k_regs_written(blk.actions))
            sel_read[sel_idx].update(blk.fields_read)
            sel_read[sel_idx].update(_k_regs_read(blk.actions))
            offset += 1

    # Build cross-formula dependency edges
    from collections import defaultdict, deque
    n_sel = len(selections)
    adj: dict[int, list[int]] = defaultdict(list)
    in_degree: dict[int, int] = defaultdict(int)
    for i in range(n_sel):
        in_degree[i]

    for i in range(n_sel):
        for j in range(n_sel):
            if i == j:
                continue
            shared = sel_written[i] & sel_read[j]
            if shared:
                adj[i].append(j)
                in_degree[j] += 1

    # Kahn sort on selections
    queue = deque([i for i in range(n_sel) if in_degree[i] == 0])
    sorted_sel_indices: list[int] = []
    warnings: list[str] = []

    while queue:
        node = queue.popleft()
        sorted_sel_indices.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_sel_indices) < n_sel:
        remaining = set(range(n_sel)) - set(sorted_sel_indices)
        sorted_sel_indices.extend(sorted(remaining))
        warnings.append(
            f"Ciclo tra {len(remaining)} gruppi di formule. "
            f"Ordinamento euristico applicato."
        )

    if sorted_sel_indices != list(range(n_sel)):
        warnings.append(
            f"Ordine modificato tra {n_sel} gruppi di formule "
            f"per rispettare dipendenze di campo cross-formula."
        )

    # Concatenate blocks in sorted selection order
    sorted_blocks: list[Block] = []
    offset = 0
    sel_block_ranges: list[tuple[int, int]] = []
    for sel in selections:
        sel_block_ranges.append((offset, offset + len(sel.blocks)))
        offset += len(sel.blocks)

    # Track which blocks we've added
    used = set()
    for sel_idx in sorted_sel_indices:
        start, end = sel_block_ranges[sel_idx]
        for i in range(start, end):
            sorted_blocks.append(combined_blocks[i])
            used.add(i)

    # Check for orphans
    orphan_warnings = FieldFlowChecker._orphan_check(sorted_blocks)
    warnings.extend(orphan_warnings)

    return sorted_blocks, warnings


# ═══════════════════════════════════════════════
# Main generation entry point
# ═══════════════════════════════════════════════

def _fsr_search_selections(
    user_request: str, top_k: int = 2
) -> list[SelectedBlocks]:
    """Helper: search via FewShotRetriever and return full-formula selections."""
    from legacy_winsarp.core.winsarp.few_shot_retriever import FewShotRetriever
    fsr = FewShotRetriever()
    results = fsr.search(user_request, top_k=top_k)
    selections = []
    for entry in results:
        formulas = _load_formulas()
        pf = formulas.get(entry.numero)
        if pf:
            selections.append(SelectedBlocks(
                formula_id=entry.numero,
                block_indices=list(range(len(pf.blocks))),
                blocks=pf.blocks,
                scope=next(iter(entry.tags), ""),
            ))
    return selections


def _tagger_search_selections(
    user_request: str, top_k_formulas: int = 3, top_k_blocks: int = 10
) -> list[SelectedBlocks]:
    """Helper: search via BlockIntentIndex and return per-formula block selections."""
    from legacy_winsarp.core.winsarp.block_intent_tagger import get_index
    index = get_index()
    entries = index.search(user_request, top_k=top_k_blocks)

    # Group by formula
    by_formula: dict[int, list] = {}
    for e in entries:
        by_formula.setdefault(e.formula_id, []).append(e)

    selections = []
    for fid in sorted(by_formula.keys())[:top_k_formulas]:
        block_entries = by_formula[fid]
        # Deduplicate by block_index
        seen = set()
        unique = []
        for be in block_entries:
            if be.block_index not in seen:
                seen.add(be.block_index)
                unique.append(be)
        blocks = [be.block for be in unique]
        indices = [be.block_index for be in unique]
        if blocks:
            scope = ';'.join(be.intents[0] for be in unique[:3]) if unique else ''
            selections.append(SelectedBlocks(
                formula_id=fid,
                block_indices=indices,
                blocks=blocks,
                scope=scope,
            ))
    return selections


def generate_recombined(
    user_request: str,
    template_ids: list[int] | None = None,
    block_indices_per_template: dict[int, list[int]] | None = None,
) -> dict[str, Any]:
    """Generate a formula by recombining blocks from template formulas.

    Selection modes (tried in order):
    1. Explicit block_indices_per_template
    2. Explicit template_ids (whole formulas)
    3. BlockIntentIndex search (selects only relevant blocks per formula)
    4. FewShotRetriever (whole formulas, fallback)
    """
    _load_formulas()

    # 1. Explicit block indices
    if block_indices_per_template:
        selections: list[SelectedBlocks] = []
        for fid, indices in block_indices_per_template.items():
            sel = select_blocks_by_indices(fid, indices)
            if sel:
                selections.append(sel)
        if selections:
            formula = recombine(selections)
            if formula:
                return _result(formula, selections, "Explicit block indices")

    # 2. Explicit template IDs (whole formulas)
    if template_ids:
        selections = []
        formulas = _load_formulas()
        for fid in template_ids:
            pf = formulas.get(fid)
            if pf:
                selections.append(SelectedBlocks(
                    formula_id=fid,
                    block_indices=list(range(len(pf.blocks))),
                    blocks=pf.blocks,
                    scope=f"full_template_{fid}",
                ))
        if selections:
            formula = recombine(selections)
            if formula:
                return _result(formula, selections, f"Templates {template_ids}")

    # 3. BlockIntentIndex: selects only relevant blocks per formula
    intents_selections = _tagger_search_selections(user_request)
    if intents_selections:
        formula = recombine(intents_selections)
        if formula:
            return _result(formula, intents_selections,
                           f"Intent blocks from {[s.formula_id for s in intents_selections]}")

    # 4. FewShotRetriever: whole formula fallback
    fsr_selections = _fsr_search_selections(user_request)
    if fsr_selections:
        formula = recombine(fsr_selections)
        if formula:
            return _result(formula, fsr_selections,
                           f"FewShot templates {[s.formula_id for s in fsr_selections]}")

    return {
        "formula": None,
        "source": "block_recombination",
        "success": False,
        "error": "Nessun template trovato per ricombinazione",
        "raw": user_request,
        "chain": "",
        "explanation": "Non sono state trovate formule nel catalogo per creare la richiesta.",
    }


def _result(formula: str, selections: list[SelectedBlocks], source_detail: str) -> dict[str, Any]:
    """Build standard success result dict."""
    sources = [s.formula_id for s in selections]
    return {
        "formula": formula,
        "source": "block_recombination",
        "success": True,
        "error": None,
        "raw": f"Recombined from {len(selections)} formula(s): {source_detail}",
        "chain": "",
        "explanation": (
            f"Formula ricombinata da {len(selections)} template "
            f"({', '.join(str(s) for s in sources)}). "
            f"Blocchi selezionati per intento dalla richiesta."
        ),
    }
