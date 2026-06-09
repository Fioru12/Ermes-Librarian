"""
core/knowledge_graph.py
Grafo della conoscenza delle formule WinSarp.

Costruisce una mappa navigabile di tutte le formule con:
  - Nodi: ogni formula con metadati (id, nome, tipo, campi, chiamate, ecc.)
  - Archi: relazioni tra formule (chiama R, chiama P, formula_called_by, ecc.)
  - Ricerca: per campo, per tipo, per formula, per relazione

Il grafo viene costruito una volta dal catalogo e persistito in JSON.
Nessuna dipendenza da modelli LLM -- solo parsing deterministico.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

CATALOGO_PATH = Path(__file__).parent.parent / "documenti" / "WinSarp" / "WinSarp_Formule.txt"
GRAPH_PATH = Path(__file__).parent.parent / "data" / "winsarp_graph.json"

RESET_FIELDS = re.compile(r'!(\d{1,4})')
FIELD_REFS = re.compile(r'(?<!\w)(\d{1,4})(?!\w)')
CALL_R = re.compile(r'R(\d{2,4});')
CALL_P = re.compile(r'P(\d{2,4})')
RETURN_CODES = re.compile(r'\b(V11|V04|V05|V06|V07|V10|VF|VU|V02)\b')
OPERATORS = re.compile(r'(UZ|U|Z|O|E)(?=[;(:])')
K_FIELDS = re.compile(r'K(\d{1,4})')
BRACED = re.compile(r'\{(\d{1,4})\}')

# Costrutti WinSarp reali
BRACKET_REF = re.compile(r'\[(\d{1,4})')            # [field
KEY_SUM = re.compile(r'K(\d{1,4})S(\d{1,4})')       # KfieldSfield
FIELD_CMP = re.compile(r'\((\d{1,4})\s*(=|#|>|<|>=|<=)\s*(\d{1,4}|"[^"]*")\)')  # (field=val)

TIPO_ORDER = {"Inizio Giornata": 1, "Fine Giornata": 2, "Di Giornata": 3, "Subroutine": 4, "Sotto Giornata": 3}
TIPO_CATEGORIES = {"Inizio Giornata": "inizio", "Fine Giornata": "fine", "Di Giornata": "giornata", "Subroutine": "sub", "Sotto Giornata": "giornata"}


def parse_catalog() -> list[dict[str, Any]]:
    """Estrae tutte le formule dal catalogo markdown."""
    text = CATALOGO_PATH.read_text(encoding="utf-8")
    formulas = []
    current = None

    for line in text.splitlines():
        m = re.match(r'^###\s+<a\s+name="(\d+)"\s*></a>\s*\d+\s*[—–\-]\s*(.+)$', line)
        if m:
            current = {"id": int(m.group(1)), "name": m.group(2).strip(), "tipo": None, "code": "", "scopo": ""}
            formulas.append(current)
            continue
        if current is None:
            continue

        m2 = re.match(r'\*\*Tipo:\*\*\s*(.+)$', line)
        if m2:
            current["tipo"] = m2.group(1).strip()
            continue

        m3 = re.match(r'\*\*Scopo:\*\*\s*(.*)$', line)
        if m3:
            scopo_text = m3.group(1).strip()
            if current["scopo"]:
                current["scopo"] += " " + scopo_text
            else:
                current["scopo"] = scopo_text
            continue

        if line.strip() == "```":
            current["in_code"] = not current.get("in_code", False)
            continue

        if current.get("in_code"):
            current["code"] += line.strip()

    for f in formulas:
        f.pop("in_code", None)

    return [f for f in formulas if f["code"]]


def extract_fields(code: str) -> dict[str, Any]:
    """Analizza il codice di una formula e ne estrae componenti."""
    numeric_refs_raw = [int(x) for x in FIELD_REFS.findall(code) if 1 <= int(x) <= 9999]
    numeric_refs = sorted(set(numeric_refs_raw))

    # Operazioni reali WinSarp
    bracket_refs = sorted(set(int(x) for x in BRACKET_REF.findall(code)))
    key_sum_pairs = KEY_SUM.findall(code)
    key_sum = []
    for k, s in key_sum_pairs:
        key_sum.append({"key": int(k), "sum": int(s)})

    comparisons = FIELD_CMP.findall(code)
    field_cmp = {}
    for f, op, val in comparisons:
        f = int(f)
        if f not in field_cmp:
            field_cmp[f] = []
        entry = {"op": op, "val": val.strip("'")}
        if entry not in field_cmp[f]:
            field_cmp[f].append(entry)

    return {
        "reset_fields": sorted(set(int(x) for x in RESET_FIELDS.findall(code))),
        "k_fields": sorted(set(int(x) for x in K_FIELDS.findall(code))),
        "braced_refs": sorted(set(int(x) for x in BRACED.findall(code))),
        "numeric_refs": numeric_refs,
        "bracket_refs": bracket_refs,
        "key_sum": key_sum,
        "calls_r": sorted(set(int(x) for x in CALL_R.findall(code))),
        "calls_p": sorted(set(int(x) for x in CALL_P.findall(code))),
        "return_codes": sorted(set(RETURN_CODES.findall(code))),
        "operators": sorted(set(OPERATORS.findall(code))),
        "comparisons": field_cmp,
    }


def build_graph() -> dict[str, Any]:
    """Costruisce il grafo completo delle formule."""
    formulas = parse_catalog()
    nodes = {}
    edges = []

    for f in formulas:
        info = extract_fields(f["code"])
        node = {
            "id": f["id"],
            "name": f["name"],
            "tipo": f["tipo"],
            "tipo_cat": TIPO_CATEGORIES.get(f["tipo"], "altro"),
            "tipo_order": TIPO_ORDER.get(f["tipo"], 99),
            "scopo": f["scopo"].strip(),
            "code": f["code"],
            "reset_fields": info["reset_fields"],
            "k_fields": info["k_fields"],
            "braced_refs": info["braced_refs"],
            "numeric_refs": info["numeric_refs"],
            "calls_r": info["calls_r"],
            "calls_p": info["calls_p"],
            "return_codes": info["return_codes"],
            "operators": info["operators"],
            "comparisons": info["comparisons"],
            "bracket_refs": info["bracket_refs"],
            "key_sum": info["key_sum"],
            "all_calls": sorted(set(info["calls_r"] + info["calls_p"])),
        }
        nodes[f["id"]] = node

        # Archi: chiamate R
        for target in info["calls_r"]:
            edges.append({"source": f["id"], "target": target, "type": "calls_r"})

        # Archi: chiamate P
        for target in info["calls_p"]:
            edges.append({"source": f["id"], "target": target, "type": "calls_p"})

    # Archi inversi: "called_by" per ogni arco diretto
    called_by: dict[int, list[int]] = {}
    for e in edges:
        t = e["target"]
        s = e["source"]
        if t not in called_by:
            called_by[t] = []
        if s not in called_by[t]:
            called_by[t].append(s)

    for fid, callers in called_by.items():
        if fid in nodes:
            nodes[fid]["called_by"] = sorted(callers)
    for fid in nodes:
        nodes[fid].setdefault("called_by", [])

    return {
        "nodes": nodes,
        "edges": edges,
        "formula_ids": sorted(nodes.keys()),
        "types": sorted(set(n["tipo"] for n in nodes.values() if n["tipo"])),
    }


def save_graph(graph: dict[str, Any]):
    """Salva il grafo su disco come JSON."""
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    _logger.info("Grafo salvato: %d nodi, %d archi", len(graph["nodes"]), len(graph["edges"]))


def load_graph() -> dict[str, Any]:
    """Carica il grafo da disco o lo costruisce se non esiste."""
    if GRAPH_PATH.exists():
        with open(GRAPH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    _logger.info("Grafo non trovato, lo costruisco...")
    graph = build_graph()
    save_graph(graph)
    return graph


class KnowledgeGraph:
    """Interfaccia per navigare il grafo delle formule."""

    def __init__(self):
        self.data = load_graph()
        self._nodes = self.data["nodes"]
        # Normalizza le chiavi dei nodi a int (JSON le salva come stringhe)
        if self._nodes:
            sample_key = next(iter(self._nodes))
            if isinstance(sample_key, str):
                self._nodes = {int(k): v for k, v in self._nodes.items()}
                self.data["nodes"] = self._nodes
        # Normalizza chiavi comparisons a string per lookup univoco
        for n in self._nodes.values():
            cmps = n.get("comparisons")
            if cmps and not all(isinstance(k, str) for k in cmps):
                n["comparisons"] = {str(k): v for k, v in cmps.items()}
        self._ids = self.data["formula_ids"]

    def get_formula(self, fid: int) -> dict | None:
        """Restituisce una formula con tutti i suoi metadati."""
        return self._nodes.get(fid)

    def search(self, query: str) -> list[dict]:
        """Cerca formule per nome, scopo o tipo."""
        q = query.lower().strip()
        tokens = [t for t in re.findall(r"[a-z0-9]+", q) if t]
        query_ids = [int(x) for x in re.findall(r"\b(\d{2,4})\b", q)]
        results = []
        for n in self._nodes.values():
            score = 0
            name_l = n["name"].lower()
            scopo_l = (n["scopo"] or "").lower()
            tipo_l = (n["tipo"] or "").lower()
            cat_l = (n["tipo_cat"] or "").lower()

            if query_ids and n["id"] in query_ids:
                score += 100

            if q and q == name_l:
                score += 30
            elif q and q in name_l:
                score += 15

            if q and q == scopo_l:
                score += 12
            elif q and q in scopo_l:
                score += 8

            if q and q == tipo_l:
                score += 6
            elif q and q in tipo_l:
                score += 3

            if q and q in cat_l:
                score += 2

            if tokens:
                name_hits = sum(1 for t in tokens if t in name_l)
                scopo_hits = sum(1 for t in tokens if t in scopo_l)
                tipo_hits = sum(1 for t in tokens if t in tipo_l)
                score += name_hits * 4 + scopo_hits * 2 + tipo_hits

            if score > 0:
                results.append((score, n))
        results.sort(key=lambda x: (-x[0], x[1]["id"]))
        return [r[1] for r in results]

    def find_by_field(self, field: int) -> list[dict]:
        """Trova tutte le formule che usano un dato campo."""
        results = []
        for n in self._nodes.values():
            if (field in n["numeric_refs"] or field in n["reset_fields"]
                    or field in n["k_fields"] or field in n["braced_refs"]):
                results.append(n)
        return results

    def find_by_type(self, tipo: str) -> list[dict]:
        """Trova tutte le formule di un dato tipo."""
        return [n for n in self._nodes.values() if n.get("tipo") == tipo]

    def find_by_operator(self, op: str) -> list[dict]:
        """Trova tutte le formule che usano un dato operatore."""
        return [n for n in self._nodes.values() if op in n["operators"]]

    def find_by_key_sum(self, key_field: int | None = None, sum_field: int | None = None) -> list[dict]:
        """Trova formule con pattern KfieldSfield (key-sum)."""
        results = []
        for n in self._nodes.values():
            for ks in n.get("key_sum", []):
                if key_field is not None and ks["key"] != key_field:
                    continue
                if sum_field is not None and ks["sum"] != sum_field:
                    continue
                results.append(n)
                break
        return results

    def find_by_comparison(self, field: int, operator: str | None = None, value: str | None = None) -> list[dict]:
        """Trova formule che confrontano un campo (es. (561=4))."""
        results = []
        for n in self._nodes.values():
            cmps = n.get("comparisons", {})
            fstr = str(field)
            if fstr not in cmps:
                continue
            for c in cmps[fstr]:
                if operator is not None and c["op"] != operator:
                    continue
                if value is not None and c["val"] != value:
                    continue
                results.append(n)
                break
        return results

    def compare_formulas(self, fid1: int, fid2: int) -> dict:
        """Confronta due formule e restituisce similarità e differenze."""
        n1 = self.get_formula(fid1)
        n2 = self.get_formula(fid2)
        if not n1 or not n2:
            return {"error": f"Formula {fid1 if not n1 else fid2} non trovata"}

        def _set(fields):
            return set(fields) if fields else set()

        reset1, reset2 = _set(n1["reset_fields"]), _set(n2["reset_fields"])
        refs1, refs2 = _set(n1["numeric_refs"]), _set(n2["numeric_refs"])
        k1, k2 = _set(n1["k_fields"]), _set(n2["k_fields"])
        calls1, calls2 = _set(n1["all_calls"]), _set(n2["all_calls"])
        braced1, braced2 = _set(n1["braced_refs"]), _set(n2["braced_refs"])

        return {
            "formula1": {"id": fid1, "name": n1["name"], "tipo": n1["tipo"], "scopo": n1["scopo"]},
            "formula2": {"id": fid2, "name": n2["name"], "tipo": n2["tipo"], "scopo": n2["scopo"]},
            "same_type": n1["tipo"] == n2["tipo"],
            "fields_common": sorted(refs1 & refs2),
            "fields_only_1": sorted(refs1 - refs2),
            "fields_only_2": sorted(refs2 - refs1),
            "reset_common": sorted(reset1 & reset2),
            "reset_only_1": sorted(reset1 - reset2),
            "reset_only_2": sorted(reset2 - reset1),
            "k_common": sorted(k1 & k2),
            "calls_common": sorted(calls1 & calls2),
            "calls_only_1": sorted(calls1 - calls2),
            "calls_only_2": sorted(calls2 - calls1),
            "braced_common": sorted(braced1 & braced2),
        }

    def follow_calls(self, fid: int) -> list[dict]:
        """Segue le chiamate di una formula e restituisce le formule chiamate."""
        node = self.get_formula(fid)
        if not node:
            return []
        targets = []
        for cid in node["all_calls"]:
            t = self.get_formula(cid)
            if t:
                targets.append(t)
        return targets

    def follow_callers(self, fid: int) -> list[dict]:
        """Trova quali formule chiamano la formula data."""
        node = self.get_formula(fid)
        if not node:
            return []
        return [self.get_formula(c) for c in node["called_by"] if self.get_formula(c)]

    def get_calls_graph(self, fid: int, depth: int = 1) -> dict:
        """Estrae il sottografo delle chiamate da/verso una formula."""
        visited = set()
        queue = [(fid, 0)]
        sub_nodes = {}
        sub_edges = []

        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)
            node = self.get_formula(current)
            if not node:
                continue
            sub_nodes[current] = node

            for c in node["all_calls"]:
                sub_edges.append({"source": current, "target": c, "type": "calls"})
                if c not in visited:
                    queue.append((c, d + 1))
            for c in node["called_by"]:
                sub_edges.append({"source": c, "target": current, "type": "called_by"})
                if c not in visited:
                    queue.append((c, d + 1))

        return {"nodes": sub_nodes, "edges": sub_edges}

    def validate_chain(self, start_id: int, max_depth: int = 10) -> dict:
        """
        Analizza una catena di formule partendo da start_id.
        Verifica la coerenza dei campi: ogni campo usato in una formula
        deve essere resettato prima nella catena.

        Ritorna:
          - chain: lista ordinata di id nella catena
          - steps: per ogni formula, campi resettati/usati/confrontati
          - issues: anomalie trovate
          - fields_state: stato finale dei campi nella catena
        """
        node = self.get_formula(start_id)
        if not node:
            return {"error": f"Formula {start_id} non trovata"}

        visited: set[int] = set()
        chain: list[int] = []
        fields_state: dict[int, str] = {}  # field -> "reset" | "used"
        steps: list[dict] = []
        issues: list[dict] = []

        def _walk(fid: int, depth: int):
            if fid in visited or depth > max_depth:
                return
            visited.add(fid)
            chain.append(fid)
            n = self.get_formula(fid)
            if not n:
                return

            reset = n.get("reset_fields", [])
            used = [f for f in n.get("numeric_refs", [])
                    if f not in reset and f not in n.get("k_fields", [])]
            compared = [int(k) for k in n.get("comparisons", {}).keys()]

            step = {
                "id": fid,
                "name": n["name"],
                "resets": reset,
                "uses": sorted(set(used + compared)),
                "compares": compared,
                "calls_r": n.get("calls_r", []),
                "calls_p": n.get("calls_p", []),
            }
            steps.append(step)

            # Verifica: campi usati che non sono ancora resettati
            for f in step["uses"]:
                if f not in fields_state:
                    fields_state[f] = "used"
                    issues.append({
                        "type": "unreset_field",
                        "formula": fid,
                        "formula_name": n["name"],
                        "field": f,
                        "detail": f"Campo {f} usato in #{fid} ma mai resettato prima nella catena",
                    })
                else:
                    fields_state[f] = "used"

            # Marca resettati
            for f in reset:
                fields_state[f] = "reset"

            # Ricorsione sulle chiamate
            for c in n.get("all_calls", []):
                _walk(c, depth + 1)

        _walk(start_id, 0)

        # Verifica finale: campi resettati ma mai usati downstream
        all_used_downstream = set()
        for s in steps:
            all_used_downstream.update(s["uses"])
        for s in steps:
            for f in s["resets"]:
                if f not in all_used_downstream:
                    issues.append({
                        "type": "unused_reset",
                        "formula": s["id"],
                        "formula_name": s["name"],
                        "field": f,
                        "detail": f"Campo {f} resettato in #{s['id']} ma mai usato nella catena",
                    })

        return {
            "start": start_id,
            "chain": chain,
            "steps": steps,
            "issues": issues,
            "fields_state": fields_state,
        }

    def stats(self) -> dict:
        return {
            "totale_formule": len(self._nodes),
            "tipi": self.data["types"],
            "archi": len(self.data["edges"]),
        }


def rebuild():
    """Forza la ricostruzione del grafo."""
    if GRAPH_PATH.exists():
        GRAPH_PATH.unlink()
    g = KnowledgeGraph()
    _logger.info("Grafo ricostruito: %s", g.stats())
    return g


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    g = KnowledgeGraph()
    print(f"Grafo: {g.stats()}")
    for n in g.data["nodes"].values():
        calls = n["all_calls"]
        callers = n["called_by"]
        if calls or callers:
            print(f"  #{n['id']:>4} {n['name'][:40]:40s} tipo={n['tipo_cat']:10s} calls={calls} called_by={callers}")
