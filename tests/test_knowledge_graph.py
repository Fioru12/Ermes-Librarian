"""Test unitari per il modulo knowledge_graph."""
import sys
import os
import tempfile
from pathlib import Path

_test_dir = Path(tempfile.mkdtemp())
_test_catalog = _test_dir / "WinSarp_Formule.txt"

SAMPLE_CATALOG = """### <a name="100"></a>100 — F.G: PRIMA FORMULA
**Tipo:** Fine Giornata
**Scopo:** Prima formula di fine giornata

```
(500="DURATA")(!561!562!563);R110;
```

### <a name="110"></a>110 — F.G: INTERMEDIA
**Tipo:** Fine Giornata
**Scopo:** Formula intermedia

```
(4=800)(!561)(U:110;560=5);R120;
```

### <a name="120"></a>120 — F.G: FINALE
**Tipo:** Fine Giornata
**Scopo:** Formula finale

```
R130;R140;(V11);
```

### <a name="130"></a>130 — F.G: STRAORDINARIO
**Tipo:** Fine Giornata
**Scopo:** Gestione straordinario

```
21UZ(V04;(504="SFN");21>4((564=4)(K21S4)(!4)V05;(564=21)(K4S21)(!21);R200;
```

### <a name="200"></a>200 — F.G: FINALE TOTALE
**Tipo:** Fine Giornata
**Scopo:** Chiusura

```
(K601A3)(K602A3);900>Z(P210;
```

### <a name="9001"></a>9001 — I.G: ARROTONDAMENTO I
**Tipo:** Inizio Giornata
**Scopo:** Arrotondamento

```
(800='250')(801='270')(!802);200UZ(VF;([800[801);R9002;(71=802)(72='15');(70='21');
```
"""

_test_catalog.write_text(SAMPLE_CATALOG, encoding="utf-8")

import core.knowledge_graph as kg_mod
kg_mod.CATALOGO_PATH = _test_catalog
kg_mod.GRAPH_PATH = _test_dir / "test_graph.json"

from core.knowledge_graph import (
    KnowledgeGraph, parse_catalog, extract_fields,
    build_graph, save_graph, load_graph, rebuild,
)


class TestParseCatalog:
    def test_parses_all_formulas(self):
        formulas = parse_catalog()
        ids = sorted(f["id"] for f in formulas)
        assert ids == [100, 110, 120, 130, 200, 9001]

    def test_parses_name_and_type(self):
        formulas = {f["id"]: f for f in parse_catalog()}
        assert formulas[100]["name"] == "F.G: PRIMA FORMULA"
        assert formulas[100]["tipo"] == "Fine Giornata"
        assert formulas[100]["scopo"] == "Prima formula di fine giornata"

    def test_skips_formulas_without_code(self):
        text_with_empty = SAMPLE_CATALOG + """
### <a name="999"></a>999 — FORMULA VUOTA
**Tipo:** Test
**Scopo:** Vuota

Nessun codice.
"""
        path = _test_dir / "test_empty.txt"
        path.write_text(text_with_empty, encoding="utf-8")
        old = kg_mod.CATALOGO_PATH
        kg_mod.CATALOGO_PATH = path
        try:
            formulas = parse_catalog()
            ids = [f["id"] for f in formulas]
            assert 999 not in ids
        finally:
            kg_mod.CATALOGO_PATH = old


class TestExtractFields:
    def test_detects_reset_fields(self):
        info = extract_fields("(!561)(!562)(!563);")
        assert info["reset_fields"] == [561, 562, 563]

    def test_detects_calls_r(self):
        info = extract_fields("R110;R120;")
        assert info["calls_r"] == [110, 120]

    def test_detects_calls_p(self):
        info = extract_fields("P210;P220;")
        assert info["calls_p"] == [210, 220]

    def test_detects_k_fields(self):
        info = extract_fields("(K21S4)(K601A563)")
        assert info["k_fields"] == [21, 601]

    def test_detects_braced_refs(self):
        info = extract_fields("({801}S{800})")
        assert info["braced_refs"] == [800, 801]

    def test_detects_comparisons(self):
        info = extract_fields('(504="SFN")(564=4)(561=21)')
        cmps = info["comparisons"]
        assert 504 in cmps
        assert any(c["op"] == "=" and c["val"] == '"SFN"' for c in cmps[504])
        assert 564 in cmps
        assert any(c["op"] == "=" and c["val"] == "4" for c in cmps[564])

    def test_detects_bracket_refs(self):
        info = extract_fields("([800[801)")
        assert info["bracket_refs"] == [800, 801]

    def test_detects_key_sum(self):
        info = extract_fields("(K21S4)(K4S21)")
        assert {"key": 21, "sum": 4} in info["key_sum"]
        assert {"key": 4, "sum": 21} in info["key_sum"]

    def test_detects_return_codes(self):
        info = extract_fields("(V11);(V04);")
        assert "V11" in info["return_codes"]
        assert "V04" in info["return_codes"]

    def test_detects_operators(self):
        info = extract_fields("UZ(U(Z(O(E(")
        assert "UZ" in info["operators"]

    def test_mixed_formula(self):
        info = extract_fields('21UZ(V04;(504="SFN");21>4((564=4)(K21S4)(!4)V05;(564=21)(K4S21)(!21);R200;')
        assert 21 in info["k_fields"]
        assert 4 in info["k_fields"]
        assert 564 in info["numeric_refs"]
        assert 200 in info["calls_r"]
        assert "UZ" in info["operators"]
        assert "V04" in info["return_codes"]
        assert "V05" in info["return_codes"]


class TestKnowledgeGraph:
    def setup_method(self):
        gpath = _test_dir / "test_graph.json"
        if gpath.exists():
            gpath.unlink()
        self.kg = KnowledgeGraph()

    def test_stats(self):
        s = self.kg.stats()
        assert s["totale_formule"] == 6

    def test_get_formula(self):
        f = self.kg.get_formula(100)
        assert f is not None
        assert f["name"] == "F.G: PRIMA FORMULA"

    def test_get_formula_missing(self):
        assert self.kg.get_formula(99999) is None

    def test_search_by_name(self):
        results = self.kg.search("PRIMA")
        ids = [r["id"] for r in results]
        assert 100 in ids

    def test_search_by_formula_number_prioritizes_exact_match(self):
        results = self.kg.search("formula 130")
        assert results
        assert results[0]["id"] == 130

    def test_search_by_scopo(self):
        results = self.kg.search("fine giornata")
        assert len(results) > 0

    def test_find_by_field(self):
        results = self.kg.find_by_field(561)
        ids = [r["id"] for r in results]
        assert 100 in ids
        assert 110 in ids

    def test_follow_calls(self):
        targets = self.kg.follow_calls(100)
        ids = [t["id"] for t in targets]
        assert 110 in ids

    def test_follow_callers(self):
        callers = self.kg.follow_callers(110)
        ids = [c["id"] for c in callers]
        assert 100 in ids

    def test_find_by_type(self):
        results = self.kg.find_by_type("Fine Giornata")
        assert len(results) >= 5

    def test_find_by_operator(self):
        results = self.kg.find_by_operator("UZ")
        assert len(results) > 0

    def test_find_by_comparison(self):
        results = self.kg.find_by_comparison(564)
        assert len(results) > 0

    def test_find_by_comparison_with_value(self):
        results = self.kg.find_by_comparison(504, "=", '"SFN"')
        ids = [r["id"] for r in results]
        assert 130 in ids

    def test_find_by_key_sum(self):
        results = self.kg.find_by_key_sum(21, 4)
        ids = [r["id"] for r in results]
        assert 130 in ids

    def test_validate_chain(self):
        result = self.kg.validate_chain(100)
        assert result["start"] == 100
        assert len(result["chain"]) >= 3
        assert "issues" in result
        assert "steps" in result

    def test_validate_chain_missing(self):
        result = self.kg.validate_chain(99999)
        assert "error" in result

    def test_compare_formulas(self):
        result = self.kg.compare_formulas(130, 200)
        assert "formula1" in result
        assert "formula2" in result
        assert result["formula1"]["id"] == 130
        assert result["formula2"]["id"] == 200

    def test_compare_formulas_missing(self):
        result = self.kg.compare_formulas(100, 99999)
        assert "error" in result

    def test_get_calls_graph(self):
        g = self.kg.get_calls_graph(100, depth=1)
        assert "nodes" in g
        assert "edges" in g
        assert 100 in g["nodes"]

    def test_save_and_load_graph(self):
        g2 = load_graph()
        assert len(g2["nodes"]) == 6
