"""
field_flow_checker.py
Ordina blocchi WinSarp per dipendenze di flusso campi:
garantisce che ogni campo sia scritto PRIMA di essere letto.

Integrato in block_recombiner.recombine() come fase di ordinamento pre-emissione.
"""
from __future__ import annotations
import logging
from collections import defaultdict, deque

from legacy_winsarp.core.winsarp.winsarp_parser import Block, Op

_logger = logging.getLogger(__name__)


def _k_regs_in_actions(actions: list[Op]) -> set[str]:
    """Extract K-register names referenced by a list of actions."""
    k_set: set[str] = set()
    for act in actions:
        for attr in ('field',):
            val = getattr(act, attr, None)
            if isinstance(val, str) and val.startswith('K'):
                k_set.add(val)
        if act.value and isinstance(act.value.value, str) and act.value.value.startswith('K'):
            k_set.add(act.value.value)
    return k_set


def _k_regs_written(actions: list[Op]) -> set[str]:
    """Extract K-registers that are WRITTEN (ADD/SUB/SET target)."""
    k_set: set[str] = set()
    for act in actions:
        if act.op_type in ('ADD', 'SUB', 'SET', 'RESET'):
            if isinstance(act.field, str) and act.field.startswith('K'):
                k_set.add(act.field)
    return k_set


def _k_regs_read(actions: list[Op]) -> set[str]:
    """Extract K-registers that are READ (value/operand side)."""
    k_set: set[str] = set()
    for act in actions:
        # K referred in value/deref — e.g., K4 S 21 (K4 being read)
        if act.value and isinstance(act.value.value, str) and act.value.value.startswith('K'):
            k_set.add(act.value.value)
        # ADD K800 A 608 A 609: K800 is both read and written
        if act.op_type in ('ADD', 'SUB') and isinstance(act.field, str) and act.field.startswith('K'):
            k_set.add(act.field)
    return k_set


class FieldFlowChecker:
    """Checks and enforces field write-before-read ordering among blocks.

    Usage:
        sorted_blocks, warnings = FieldFlowChecker.sort(blocks)
    """

    @staticmethod
    def find_dependencies(blocks: list[Block]) -> list[tuple[int, int, str]]:
        """Return list of (producer_idx, consumer_idx, field) tuples.

        producer_idx writes a field/register that consumer_idx reads.
        """
        n = len(blocks)
        deps: list[tuple[int, int, str]] = []

        for i in range(n):
            written = set(blocks[i].fields_written)
            written_k = _k_regs_written(blocks[i].actions)
            for j in range(n):
                if i == j:
                    continue
                read = set(blocks[j].fields_read)
                read_k = _k_regs_read(blocks[j].actions)

                # Regular field dependencies
                shared = written & read
                for f in shared:
                    deps.append((i, j, str(f)))

                # K-register dependencies
                shared_k = written_k & read_k
                for k in shared_k:
                    deps.append((i, j, k))

        return deps

    @staticmethod
    def _orphan_check(blocks: list[Block]) -> list[str]:
        """Check for fields read but never written by any block."""
        warnings: list[str] = []
        all_written: set[int | str] = set()
        all_read: set[int | str] = set()
        for blk in blocks:
            all_written.update(blk.fields_written)
            all_written.update(_k_regs_written(blk.actions))
            all_read.update(blk.fields_read)
            all_read.update(_k_regs_read(blk.actions))

        orphans = all_read - all_written
        if orphans:
            fields_str = ', '.join(str(f) for f in sorted(orphans, key=lambda x: str(x)))
            warnings.append(
                f"Campi letti ma mai scritti: {fields_str}. "
                "Verificare che siano inizializzati esternamente."
            )
        return warnings

    @staticmethod
    def topological_sort(
        blocks: list[Block],
    ) -> tuple[list[int], list[str]]:
        """Kahn topological sort based on field read/write dependencies.

        Returns (sorted_indices, warnings).
        Falls back to original order if cycles are detected, with warnings.
        """
        n = len(blocks)
        deps = FieldFlowChecker.find_dependencies(blocks)

        if n <= 1:
            # Still check for orphan fields even with single block
            warnings: list[str] = FieldFlowChecker._orphan_check(blocks)
            return list(range(n)), warnings



        # Build adjacency and in-degree
        adj: dict[int, list[int]] = defaultdict(list)
        in_degree: dict[int, int] = defaultdict(int)
        all_nodes = set(range(n))

        for i in all_nodes:
            in_degree[i]  # ensure all nodes have entry

        for src, tgt, _field in deps:
            adj[src].append(tgt)
            in_degree[tgt] += 1

        # Kahn
        queue = deque([i for i in all_nodes if in_degree[i] == 0])
        sorted_indices: list[int] = []
        warnings: list[str] = []

        while queue:
            node = queue.popleft()
            sorted_indices.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for cycles
        if len(sorted_indices) < n:
            remaining = all_nodes - set(sorted_indices)
            # Try heuristic: sort remaining by out-degree
            remaining_list = sorted(remaining, key=lambda x: -len(adj[x]))
            for r in remaining_list:
                sorted_indices.append(r)
            warnings.append(
                f"Ciclo rilevato tra {len(remaining)} blocchi "
                f"(indici: {sorted(remaining)}). Ordinamento euristico applicato."
            )
            _logger.warning(warnings[-1])

        # Check for orphan fields (read but never written)
        orphans_warnings = FieldFlowChecker._orphan_check(blocks)
        warnings.extend(orphans_warnings)

        # Analyze deps added vs satisfied
        field_flow_issues = []
        written_before: set[int | str] = set()
        for idx in sorted_indices:
            blk = blocks[idx]
            written_before.update(blk.fields_written)
            written_before.update(_k_regs_written(blk.actions))
        # Check each dep
        for _src, _tgt, _field in deps:
            pass  # already handled by topsort

        return sorted_indices, warnings

    @staticmethod
    def sort(blocks: list[Block]) -> tuple[list[Block], list[str]]:
        """Topologically sort blocks by field dependencies.

        Returns (sorted_blocks, warnings).
        """
        indices, warnings = FieldFlowChecker.topological_sort(blocks)
        sorted_b = [blocks[i] for i in indices]

        # Detect if order actually changed
        original_order = list(range(len(blocks)))
        if indices != original_order:
            changed = sum(1 for a, b in zip(indices, original_order) if a != b)
            warnings.append(
                f"Ordine modificato per {changed} blocchi "
                f"per rispettare dipendenze di campo."
            )

        return sorted_b, warnings
