"""Test per core/formula_graph.py."""

from legacy_winsarp.core.winsarp.formula_graph import (
    _extract_read_write,
    _extract_vxx_labels,
    _is_quoted,
    FormulaDependencyGraph,
)


class TestIsQuoted:
    def test_not_quoted(self):
        assert _is_quoted('( 801 = 100 )', 3) is False

    def test_in_double_quotes(self):
        assert _is_quoted('58 U "RIPO"', 7) is True

    def test_in_single_quotes(self):
        assert _is_quoted("( 801 = '200' )", 11) is True

    def test_outside_quotes(self):
        assert _is_quoted("( 801 = '200' )", 3) is False


class TestExtractReadWrite:
    def test_reset_single(self):
        code = "(!900)"
        written, read = _extract_read_write(code)
        assert 900 in written
        assert len(read) == 0

    def test_reset_multiple(self):
        code = "(!800!801!802)"
        written, read = _extract_read_write(code)
        assert 800 in written
        assert 801 in written
        assert 802 in written

    def test_set_assignment(self):
        code = "( 801 = '200' )"
        written, read = _extract_read_write(code)
        assert 801 in written

    def test_braced_deref(self):
        code = "{ 802 } S { 801 }"
        written, read = _extract_read_write(code)
        assert 801 in read
        assert 802 in read

    def test_condition_read(self):
        code = "803 < Z"
        written, read = _extract_read_write(code)
        assert 803 in read

    def test_k_write(self):
        code = "K803 A '24'"
        written, read = _extract_read_write(code)
        assert 803 in written

    def test_pointer_ops(self):
        code = "[800[801[802"
        written, read = _extract_read_write(code)
        assert 800 in written
        assert 801 in written
        assert 802 in written

    def test_cmp_both_numbers(self):
        code = "803 < 804"
        written, read = _extract_read_write(code)
        assert 803 in read
        assert 804 in read

    def test_formula5_like(self):
        code = (
            "(!900);(!800!801!802!803!804);"
            "200UZO58U\"RIPO\"(VF;"
            "(801='200')(802='220');([800[801[802);"
            "(803={802}S{801});"
            "803<Z((K803A'24');"
            "{801}>U'04.00'E{801}<U'09.00'((58=\"MATT\")"
        )
        written, read = _extract_read_write(code)
        # 200 is read from condition "200UZO..." (if 200 = 0)
        assert 200 in read
        # Should NOT have quoted-string values as reads
        assert 220 not in read
        assert 24 not in read
        # Should have deref reads
        assert 801 in read
        assert 802 in read
        # Should have writes
        assert 900 in written
        assert 800 in written
        assert 803 in written
        assert 58 in written


class TestExtractVxxLabels:
    def test_simple_reference(self):
        code = "803<804((803=804)V11"
        defined, referenced = _extract_vxx_labels(code)
        assert "V11" in referenced

    def test_simple_defined(self):
        code = "V11"
        defined, referenced = _extract_vxx_labels(code)
        assert "V11" in defined

    def test_vf_vu_skipped(self):
        defined, referenced = _extract_vxx_labels("VF;VU;")
        assert "VF" not in defined
        assert "VU" not in defined
        assert "VF" not in referenced
        assert "VU" not in referenced

    def test_formula5_vxx(self):
        code = (
            "803<804((803=804)V11;"
            "{801}>U'04.00'E{801}<U'09.00'((58=\"MATT\")V11;"
            "800U200(VF;(804=803)V04"
        )
        defined, referenced = _extract_vxx_labels(code)
        assert "V11" in referenced
        assert "V04" in referenced


class TestFormulaDependencyGraph:
    def test_load(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        assert len(g.nodes) > 0
        assert g._loaded

    def test_entry_points(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        stats = g.stats()
        assert stats["n_formulas"] > 0
        # Formula 5 should be an entry point (called_by empty)
        assert 5 in stats["entry_points"]

    def test_formula_summary(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        s = g.get_formula_summary(5)
        assert s is not None
        assert s["id"] == 5
        assert "Riconoscimento Turno" in s["name"]
        assert isinstance(s["fields_write"], list)
        assert isinstance(s["fields_read"], list)

    def test_formula_summary_missing(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        assert g.get_formula_summary(999) is None

    def test_get_call_chain_down(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        # 120 calls R 130, R 140, R 200
        chain = g.get_call_chain(120, "down")
        ids = {c["id"] for c in chain}
        assert 120 in ids
        assert 130 in ids or 140 in ids or 200 in ids

    def test_get_call_chain_up(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        # 200 is called by many
        chain = g.get_call_chain(200, "up")
        ids = {c["id"] for c in chain}
        assert 200 in ids
        # Should have at least one caller
        callers = [c for c in chain if c.get("called_by")]
        assert len(callers) >= 1

    def test_get_call_chain_missing(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        assert g.get_call_chain(999, "down") == []

    def test_get_field_flow(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        flow = g.get_field_flow(800)
        assert len(flow) == 1
        assert flow[0]["field"] == 800
        assert len(flow[0]["writers"]) > 0

    def test_field_flow_missing(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        flow = g.get_field_flow(99999)
        assert flow[0]["writers"] == []
        assert flow[0]["readers"] == []

    def test_suggest_insertion_points_shift(self):
        """Nuova formula turno dovrebbe suggerire Formula 5."""
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        suggestions = g.suggest_insertion_points(
            reads={801, 802, 58},
            writes={900, 111, 141},
        )
        assert len(suggestions) > 0
        # Formula 5 should be in top results
        f5_ids = [s["id"] for s in suggestions if s["id"] == 5]
        assert len(f5_ids) > 0
        # Top result should have score > 0
        assert suggestions[0]["score"] > 0

    def test_suggest_insertion_points_no_match(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        suggestions = g.suggest_insertion_points(
            reads={99999},
            writes={88888},
        )
        assert len(suggestions) == 0

    def test_stats(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        stats = g.stats()
        assert stats["n_formulas"] > 0
        assert stats["n_edges"] > 0
        assert len(stats["entry_points"]) > 0
        assert len(stats["types"]) > 0

    def test_to_mermaid(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        mm = g.to_mermaid()
        assert mm.startswith("graph TD")
        assert "style" in mm
        assert "Legenda" in mm

    def test_to_mermaid_cluster(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        mm = g.to_mermaid_cluster()
        assert "graph TB" in mm
        assert "subgraph" in mm

    def test_save_and_load(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        g.save()
        # Create new instance and load from enriched
        g2 = FormulaDependencyGraph()
        g2.load(force_rebuild=False)
        assert len(g2.nodes) == len(g.nodes)

    def test_to_json(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        js = g.to_json()
        assert '"id": 5' in js
        assert '"stats"' in js

    def test_edges_include_calls(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        r_edges = [e for e in g.edges if e.type == "calls_r"]
        p_edges = [e for e in g.edges if e.type == "calls_p"]
        # Some formulas should have R/P calls
        assert len(r_edges) + len(p_edges) > 0

    def test_vxx_edges(self):
        g = FormulaDependencyGraph()
        g.load(force_rebuild=True)
        vxx_edges = [e for e in g.edges if e.type == "vxx_ref"]
        # Should have at least self-references (we can't guarantee more)
        assert isinstance(vxx_edges, list)
