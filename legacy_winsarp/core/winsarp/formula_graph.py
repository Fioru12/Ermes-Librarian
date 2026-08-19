"""
core/formula_graph.py
Grafo delle dipendenze tra formule WinSarp.

Costruito sopra core/knowledge_graph.py, aggiunge:
  - Field read/write analysis (quali campi ogni formula legge/scrive)
  - Vxx label definitions vs. external references
  - Mermaid visualization (diagramma flow)
  - Insertion point suggestion (dove agganciare una nuova formula)
  - Call chain analysis con profondità
  - Field flow tracking (chi produce, chi consuma un campo)
"""

import json
import logging
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from legacy_winsarp.core.winsarp.knowledge_graph import load_graph
from legacy_winsarp.core.winsarp.parser_rules import (
    VXX_REF, FIELD_SET, K_FIELD, COND_FIELD,
)

_logger = logging.getLogger(__name__)

GRAPH_ENRICHED_PATH = Path(__file__).parent.parent.parent / "data" / "winsarp_graph_enriched.json"

# Pattern per reset: ( !N )
RESET_FIELD = re.compile(r'!(\d{1,4})')

# Pattern per {N} (dereference pointer) con spazi opzionali
BRACED_FIELD = re.compile(r'\{\s*(\d{1,4})\s*\}')

# Pattern per [N / ]N (pointer avanza/retrocede)
BRACKET_FIELD = re.compile(r'[\[\]](\d{1,4})')


def _is_quoted(code: str, pos: int) -> bool:
    """True se pos e' dentro una stringa tra virgolette singole o doppie."""
    before = code[:pos]
    in_dq = False
    in_sq = False
    i = 0
    while i < len(before):
        if before[i] == '"' and not in_sq:
            in_dq = not in_dq
        elif before[i] == "'" and not in_dq:
            in_sq = not in_sq
        i += 1
    return in_dq or in_sq


def _extract_read_write(code: str) -> tuple[set[int], set[int]]:
    """Analizza codice compatto e ritorna (written_fields, read_fields)."""
    written: set[int] = set()
    read: set[int] = set()

    # RESET: !N → write N
    for m in RESET_FIELD.finditer(code):
        if not _is_quoted(code, m.start()):
            written.add(int(m.group(1)))

    # SET: ( N = val ) → write N, read fields in val
    for m in FIELD_SET.finditer(code):
        if not _is_quoted(code, m.start()):
            fid = int(m.group(1))
            written.add(fid)

    # K: K N A/S val → write N, read fields in val
    for m in K_FIELD.finditer(code):
        if not _is_quoted(code, m.start()):
            written.add(int(m.group(1)))

    # Pointer operators: [N / ]N → write N (pointer chain)
    for m in BRACKET_FIELD.finditer(code):
        if not _is_quoted(code, m.start()):
            written.add(int(m.group(1)))

    # Braced derefs: {N} → read N
    for m in BRACED_FIELD.finditer(code):
        if not _is_quoted(code, m.start()):
            read.add(int(m.group(1)))

    # Conditions: N U / N > / N < val → read N
    for m in COND_FIELD.finditer(code):
        if not _is_quoted(code, m.start()):
            fid = int(m.group(1))
            if fid not in written:
                read.add(fid)

    # Numeric refs in values (after =): ( N = val ) → read fields in val
    for m in re.finditer(r'=\s*([^)]+)', code):
        val = m.group(1)
        for fm in re.finditer(r'(?<!\w)(\d{1,4})(?!\w)', val):
            actual_pos = m.start(1) + fm.start()
            if _is_quoted(code, actual_pos):
                continue
            fv = int(fm.group(1))
            if fv not in written:
                read.add(fv)

    # CMP patterns: N > M / N < M inside conditions
    for m in re.finditer(r'(\d{1,4})\s*(?:>|<|=|#|>=|<=)\s*(\d{1,4})', code):
        if _is_quoted(code, m.start()):
            continue
        f1 = int(m.group(1))
        f2p = m.start(2)
        f2 = int(m.group(2))
        if not _is_quoted(code, f2p):
            if f1 not in written:
                read.add(f1)
            if f2 not in written:
                read.add(f2)

    return written, read


def _extract_vxx_labels(code: str) -> tuple[set[str], set[str]]:
    """Estrae label Vxx definite e referenziate in una formula.

    In WinSarp, Vxx puo' essere:
      - Label definita: appena dopo (( ... ) come target di salto
      - Label referenziata: Vxx alla fine di un blocco condizionale
      - Return code: VF, VU

    Ritorna (defined, referenced).
    """
    defined: set[str] = set()
    referenced: set[str] = set()

    for m in VXX_REF.finditer(code):
        vxx = f"V{m.group(1)}"
        pos = m.start()

        # Salta VF e VU
        if vxx in ("VF", "VU"):
            continue

        # Contesto: guarda i 20 caratteri prima
        ctx_before = code[max(0, pos - 20):pos].strip()

        # Se dopo )) → referenced (target di salto)
        if ctx_before.endswith("))"):
            referenced.add(vxx)
        # Se dopo parentesi chiusa singola ) → referenced
        elif ctx_before.endswith(")"):
            referenced.add(vxx)
        # Se su linea propria o dopo E/O → defined
        elif not ctx_before or ctx_before.endswith(("E", "O", "(")):
            defined.add(vxx)
        else:
            # Default: referenced
            referenced.add(vxx)

    return defined, referenced


@dataclass
class FormulaNode:
    id: int
    name: str
    tipo: str
    tipo_cat: str
    scopo: str
    code: str
    calls_r: list[int] = field(default_factory=list)
    calls_p: list[int] = field(default_factory=list)
    called_by: list[int] = field(default_factory=list)
    fields_write: set[int] = field(default_factory=set)
    fields_read: set[int] = field(default_factory=set)
    vxx_defined: set[str] = field(default_factory=set)
    vxx_referenced: set[str] = field(default_factory=set)
    return_codes: list[str] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)
    depth: int = -1  # profondita' massima nella call chain


@dataclass
class FormulaEdge:
    source: int
    target: int
    type: str  # "calls_r" | "calls_p" | "vxx_ref" | "field_share"


class FormulaDependencyGraph:
    """Grafo avanzato delle dipendenze tra formule WinSarp.

    Usage:
        g = FormulaDependencyGraph()
        g.load()  # carica da grafo base e arricchisce

        # Visualizzazione
        print(g.to_mermaid())

        # Analisi
        chain = g.get_call_chain(5, "down")
        suggestions = g.suggest_insertion_points(reads={801, 802}, writes={900})
        field_flow = g.get_field_flow(800)
    """

    def __init__(self) -> None:
        self.nodes: dict[int, FormulaNode] = {}
        self.edges: list[FormulaEdge] = []
        self._graph_data: dict[str, Any] = {}
        self._loaded = False

    # ---- Caricamento ----

    def load(self, force_rebuild: bool = False) -> None:
        """Carica il grafo base e lo arricchisce."""
        if not force_rebuild and GRAPH_ENRICHED_PATH.exists():
            self._load_enriched()
            return

        self._graph_data = load_graph()
        self._build_nodes()
        self._analyze_vxx()
        self._compute_depths()
        self._build_field_edges()
        self._loaded = True

    def _build_nodes(self) -> None:
        """Costruisce nodi arricchiti dal grafo base."""
        base_nodes = self._graph_data["nodes"]
        base_edges = self._graph_data.get("edges", [])

        for fid_str, base in base_nodes.items():
            fid = int(fid_str)
            write_f, read_f = _extract_read_write(base.get("code", ""))
            vxx_def, vxx_ref = _extract_vxx_labels(base.get("code", ""))

            node = FormulaNode(
                id=fid,
                name=base.get("name", ""),
                tipo=base.get("tipo", ""),
                tipo_cat=base.get("tipo_cat", ""),
                scopo=base.get("scopo", ""),
                code=base.get("code", ""),
                calls_r=list(base.get("calls_r", [])),
                calls_p=list(base.get("calls_p", [])),
                called_by=list(base.get("called_by", [])),
                fields_write=write_f,
                fields_read=read_f,
                vxx_defined=vxx_def,
                vxx_referenced=vxx_ref,
                return_codes=list(base.get("return_codes", [])),
                operators=list(base.get("operators", [])),
            )
            self.nodes[fid] = node

        # Copia archi base
        for e in base_edges:
            self.edges.append(FormulaEdge(
                source=e["source"],
                target=e["target"],
                type=e["type"],
            ))

    def _analyze_vxx(self) -> None:
        """Collega Vxx referenced a potenziali formulazioni che li definiscono."""
        vxx_to_formulas: dict[str, list[int]] = defaultdict(list)
        for fid, node in self.nodes.items():
            for vxx in node.vxx_defined:
                vxx_to_formulas[vxx].append(fid)

        for fid, node in self.nodes.items():
            for vxx in node.vxx_referenced:
                if vxx in vxx_to_formulas:
                    for target_fid in vxx_to_formulas[vxx]:
                        if target_fid != fid:
                            self.edges.append(FormulaEdge(
                                source=fid,
                                target=target_fid,
                                type="vxx_ref",
                            ))

    def _compute_depths(self) -> None:
        """Calcola profondita' massima di ogni nodo nella call chain."""
        # Trova entry points (nodi mai chiamati)
        all_called = set()
        for e in self.edges:
            if e.type in ("calls_r", "calls_p"):
                all_called.add(e.target)

        # BFS da ogni entry point
        for fid in self.nodes:
            if fid in all_called:
                continue
            self._bfs_depth(fid, 0, set())

    def _bfs_depth(self, fid: int, depth: int, visited: set[int]) -> None:
        if fid in visited or fid not in self.nodes:
            return
        visited.add(fid)
        node = self.nodes[fid]
        if depth > node.depth:
            node.depth = depth
        for e in self.edges:
            if e.source == fid and e.type in ("calls_r", "calls_p"):
                self._bfs_depth(e.target, depth + 1, visited)

    def _build_field_edges(self) -> None:
        """Crea archi field_share tra formule che condividono campi."""
        fields_to_nodes: dict[int, set[int]] = defaultdict(set)
        for fid, node in self.nodes.items():
            for f in node.fields_write | node.fields_read:
                fields_to_nodes[f].add(fid)

        for f, fids in fields_to_nodes.items():
            fids_list = sorted(fids)
            for i in range(len(fids_list)):
                for j in range(i + 1, len(fids_list)):
                    # Evita duplicati
                    if not any(
                        e.source == fids_list[i] and e.target == fids_list[j]
                        and e.type == "field_share"
                        for e in self.edges
                    ):
                        self.edges.append(FormulaEdge(
                            source=fids_list[i],
                            target=fids_list[j],
                            type="field_share",
                        ))

    def _load_enriched(self) -> None:
        """Carica da JSON arricchito."""
        data = json.loads(GRAPH_ENRICHED_PATH.read_text(encoding="utf-8"))
        for n_data in data["nodes"]:
            n_data["fields_write"] = set(n_data.get("fields_write", []))
            n_data["fields_read"] = set(n_data.get("fields_read", []))
            n_data["vxx_defined"] = set(n_data.get("vxx_defined", []))
            n_data["vxx_referenced"] = set(n_data.get("vxx_referenced", []))
            self.nodes[n_data["id"]] = FormulaNode(**n_data)
        for e_data in data["edges"]:
            self.edges.append(FormulaEdge(**e_data))
        self._loaded = True

    def save(self) -> None:
        """Salva il grafo arricchito su disco."""
        data = {
            "nodes": [
                {
                    **asdict(n),
                    "fields_write": sorted(n.fields_write),
                    "fields_read": sorted(n.fields_read),
                    "vxx_defined": sorted(n.vxx_defined),
                    "vxx_referenced": sorted(n.vxx_referenced),
                }
                for n in self.nodes.values()
            ],
            "edges": [asdict(e) for e in self.edges],
        }
        GRAPH_ENRICHED_PATH.parent.mkdir(parents=True, exist_ok=True)
        GRAPH_ENRICHED_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _logger.info(
            "Grafo arricchito salvato: %d nodi, %d archi",
            len(data["nodes"]),
            len(data["edges"]),
        )

    # ---- Query ----

    def get_call_chain(
        self, start_id: int, direction: str = "down", max_depth: int = 10
    ) -> list[dict[str, Any]]:
        """Ritorna la catena di chiamate a partire da una formula.

        Args:
            start_id: ID formula di partenza.
            direction: "down" (chiama), "up" (chiamato da).
            max_depth: profondita' massima.
        """
        if start_id not in self.nodes:
            return []
        result = []
        visited: set[int] = set()

        def _walk(fid: int, depth: int) -> None:
            if fid in visited or depth > max_depth:
                return
            visited.add(fid)
            node = self.nodes[fid]
            entry = {
                "id": fid,
                "name": node.name,
                "tipo": node.tipo,
                "depth": depth,
            }
            if direction == "down":
                calls = []
                for e in self.edges:
                    if e.source == fid and e.type in ("calls_r", "calls_p"):
                        calls.append({"target": e.target, "type": e.type})
                        _walk(e.target, depth + 1)
                entry["calls"] = calls
            else:
                callers = []
                for e in self.edges:
                    if e.target == fid and e.type in ("calls_r", "calls_p"):
                        callers.append({"source": e.source, "type": e.type})
                        _walk(e.source, depth + 1)
                entry["called_by"] = callers
            result.append(entry)

        _walk(start_id, 0)
        return result

    def get_field_flow(self, field: int) -> list[dict[str, Any]]:
        """Ritorna quali formule leggono/scrivono un campo."""
        writers = []
        readers = []
        for fid, node in self.nodes.items():
            if field in node.fields_write:
                writers.append({
                    "id": fid,
                    "name": node.name,
                    "tipo": node.tipo,
                })
            if field in node.fields_read:
                readers.append({
                    "id": fid,
                    "name": node.name,
                    "tipo": node.tipo,
                })
        return [{"field": field, "writers": writers, "readers": readers}]

    def get_formula_summary(self, fid: int) -> dict[str, Any] | None:
        """Ritorna un sommario compatto di una formula."""
        if fid not in self.nodes:
            return None
        n = self.nodes[fid]
        return {
            "id": n.id,
            "name": n.name,
            "tipo": n.tipo,
            "depth": n.depth,
            "n_calls_out": len(n.calls_r) + len(n.calls_p),
            "n_called_by": len(n.called_by),
            "n_fields_write": len(n.fields_write),
            "n_fields_read": len(n.fields_read),
            "fields_write": sorted(n.fields_write),
            "fields_read": sorted(n.fields_read),
            "calls_r": n.calls_r,
            "calls_p": n.calls_p,
            "called_by": n.called_by,
        }

    # ---- Suggerimenti ----

    def suggest_insertion_points(
        self,
        reads: set[int],
        writes: set[int],
        max_suggestions: int = 5,
    ) -> list[dict[str, Any]]:
        """Suggerisce dove agganciare una nuova formula basandosi sui campi.

        Criteri:
          1. Formule che scrivono campi che la nuova formula legge (produttori)
          2. Formule che leggono campi che la nuova formula scrive (consumatori)
          3. Formule dello stesso tipo
          4. Formule con chiamate R/P simili

        Args:
            reads: campi che la nuova formula legge.
            writes: campi che la nuova formula scrive.
            max_suggestions: max risultati.
        """
        scores: dict[int, float] = defaultdict(float)

        for fid, node in self.nodes.items():
            # Punteggio per produttori (scrivono ciò che leggiamo)
            shared_read = reads & node.fields_write
            if shared_read:
                scores[fid] += len(shared_read) * 2.0

            # Punteggio per consumatori (leggono ciò che scriviamo)
            shared_write = writes & node.fields_read
            if shared_write:
                scores[fid] += len(shared_write) * 2.0

            # Campi condivisi in generale
            all_shared = (reads | writes) & (node.fields_read | node.fields_write)
            if all_shared:
                scores[fid] += len(all_shared) * 0.5

        # Ordina per punteggio
        ranked = sorted(scores.items(), key=lambda x: -x[1])

        suggestions = []
        for fid, score in ranked[:max_suggestions]:
            n = self.nodes[fid]
            reason_parts = []
            shared_r = reads & n.fields_write
            if shared_r:
                reason_parts.append(f"scrive campi che leggi: {sorted(shared_r)}")
            shared_w = writes & n.fields_read
            if shared_w:
                reason_parts.append(f"legge campi che scrivi: {sorted(shared_w)}")
            all_s = (reads | writes) & (n.fields_read | n.fields_write)
            if all_s and not (shared_r or shared_w):
                reason_parts.append(f"condivide campi: {sorted(all_s)}")
            suggestions.append({
                "id": fid,
                "name": n.name,
                "tipo": n.tipo,
                "score": round(score, 1),
                "reason": "; ".join(reason_parts),
                "fields_write": sorted(n.fields_write),
                "fields_read": sorted(n.fields_read),
            })

        return suggestions

    # ---- Statistiche ----

    def stats(self) -> dict[str, Any]:
        """Ritorna statistiche del grafo."""
        n_formulas = len(self.nodes)
        n_edges = len(self.edges)
        calls_out = sum(len(n.calls_r) + len(n.calls_p) for n in self.nodes.values())
        orphans = [fid for fid, n in self.nodes.items() if not n.called_by and n.depth == 0]
        depths: dict[int, int] = defaultdict(int)
        for n in self.nodes.values():
            depths[n.depth] += 1

        return {
            "n_formulas": n_formulas,
            "n_edges": n_edges,
            "total_calls": calls_out,
            "entry_points": sorted(orphans),
            "depths": dict(sorted(depths.items())),
            "types": sorted(set(n.tipo for n in self.nodes.values())),
        }

    # ---- Visualizzazione ----

    def to_mermaid(self) -> str:
        """Genera diagramma Mermaid del grafo delle chiamate."""
        lines = ["graph TD"]
        added_nodes: set[int] = set()
        added_edges: set[str] = set()

        # Aggiungi nodi con stile per tipo
        tipo_styles = {
            "Inizio Giornata": "fill:#4CAF50,color:#fff",
            "Fine Giornata": "fill:#2196F3,color:#fff",
            "Subroutine": "fill:#FF9800,color:#fff",
            "Di Giornata": "fill:#9C27B0,color:#fff",
        }

        for fid in sorted(self.nodes):
            n = self.nodes[fid]
            style = tipo_styles.get(n.tipo, "fill:#607D8B,color:#fff")
            label = f"{fid}: {n.name[:40]}"
            lines.append(f'    {fid}["{label}"]')
            lines.append(f"    style {fid} {style}")
            added_nodes.add(fid)

        # Archi R/P
        for e in self.edges:
            if e.type == "calls_r":
                edge_key = f"{e.source}-R-{e.target}"
                if edge_key not in added_edges:
                    lines.append(f"    {e.source} -->|R| {e.target}")
                    added_edges.add(edge_key)
            elif e.type == "calls_p":
                edge_key = f"{e.source}-P-{e.target}"
                if edge_key not in added_edges:
                    lines.append(f"    {e.source} -.->|P| {e.target}")
                    added_edges.add(edge_key)

        # Legenda
        lines.append("")
        lines.append("    %% Legenda")
        lines.append("    subgraph Legenda")
        lines.append('        L_R["R = chiama subroutine"]')
        lines.append('        L_P["P = chiama procedura"]')
        lines.append("    end")
        lines.append("    style L_R fill:#eee,stroke:#333")
        lines.append("    style L_P fill:#eee,stroke:#333")

        return "\n".join(lines)

    def to_mermaid_cluster(self) -> str:
        """Diagramma Mermaid raggruppato per tipo."""
        lines = ["graph TB"]
        tipo_groups: dict[str, list[int]] = defaultdict(list)
        for fid, n in self.nodes.items():
            tipo_groups[n.tipo].append(fid)

        colors = [
            "#4CAF50", "#2196F3", "#FF9800", "#9C27B0",
            "#607D8B", "#F44336", "#00BCD4", "#FFC107",
        ]
        for color_idx, (tipo, fids) in enumerate(sorted(tipo_groups.items())):
            color = colors[color_idx % len(colors)]
            sub_name = tipo.replace(" ", "_").replace("/", "_")
            escaped_tipo = tipo.replace('"', "'")
            lines.append(f"    subgraph {sub_name}[\"{escaped_tipo}\"]")
            for fid in sorted(fids):
                n = self.nodes[fid]
                label = f"{fid}: {n.name[:40]}"
                lines.append(f"        {fid}[\"{label}\"]")
                lines.append(f"        style {fid} fill:{color},color:#fff")
            lines.append("    end")

        added_edges: set[str] = set()
        for e in self.edges:
            if e.type in ("calls_r", "calls_p"):
                edge_key = f"{e.source}-{e.type}-{e.target}"
                if edge_key not in added_edges:
                    arrow = "-->|R|" if e.type == "calls_r" else "-.->|P|"
                    lines.append(f"    {e.source} {arrow} {e.target}")
                    added_edges.add(edge_key)

        return "\n".join(lines)

    def to_json(self) -> str:
        """Esporta il grafo come JSON."""
        return json.dumps({
            "nodes": [
                {
                    **asdict(n),
                    "fields_write": sorted(n.fields_write),
                    "fields_read": sorted(n.fields_read),
                    "vxx_defined": sorted(n.vxx_defined),
                    "vxx_referenced": sorted(n.vxx_referenced),
                }
                for n in self.nodes.values()
            ],
            "edges": [asdict(e) for e in self.edges],
            "stats": self.stats(),
        }, ensure_ascii=False, indent=2)
