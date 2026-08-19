"""Unit test per TableRegistry e FormulaPatternLibrary."""
import sys; sys.path.insert(0, ".")

from legacy_winsarp.core.winsarp.table_registry import TableRegistry, CAUSALE_ORIGINE_AUTOMATICA, CAUSALE_ORIGINE_TURNO
from legacy_winsarp.core.winsarp.patterns import FormulaPatternLibrary, FORMULA_TIPO_IG, FORMULA_TIPO_FG, FORMULA_TIPO_SUB


# ============================================================
# TableRegistry Tests
# ============================================================

class TestTableRegistryBasics:
    def setup_method(self):
        self.r = TableRegistry()

    def test_singleton(self):
        r2 = TableRegistry()
        assert self.r is r2

    def test_causali_counts(self):
        s = self.r.stats()
        assert s["total_causali"] >= 20
        assert s["slot_mappings"] == 10

    def test_contracts_counts(self):
        s = self.r.stats()
        assert s["contracts"] == 3

    def test_formula_relations(self):
        s = self.r.stats()
        assert s["formula_relations"] >= 20

    def test_formula_flows(self):
        s = self.r.stats()
        assert s["formula_flows"] >= 10


class TestTableRegistryCausali:
    def setup_method(self):
        self.r = TableRegistry()

    def test_get_causale_exists(self):
        c = self.r.get_causale("SFN")
        assert c is not None
        assert c.name == "Straordinario Festivo Notturno"
        assert c.category == "straordinario"

    def test_get_causale_not_exists(self):
        assert self.r.get_causale("NONEXISTENT") is None

    def test_get_causale_case_insensitive(self):
        c1 = self.r.get_causale("sfn")
        c2 = self.r.get_causale("SFN")
        assert c1 is c2

    def test_get_causale_none(self):
        assert self.r.get_causale(None) is None  # type: ignore

    def test_get_causali_by_category(self):
        straord = self.r.get_causali_by_category("straordinario")
        assert len(straord) >= 5
        assert all(c.category == "straordinario" for c in straord)

    def test_get_causali_by_origin(self):
        auto = self.r.get_causali_by_origin(CAUSALE_ORIGINE_AUTOMATICA)
        assert len(auto) >= 10
        assert all(c.origin == CAUSALE_ORIGINE_AUTOMATICA for c in auto)

        turno = self.r.get_causali_by_origin(CAUSALE_ORIGINE_TURNO)
        assert len(turno) >= 5
        assert all(c.origin == CAUSALE_ORIGINE_TURNO for c in turno)

    def test_search_causali(self):
        results = self.r.search_causali("straordinario")
        assert len(results) >= 5
        results = self.r.search_causali("festivo")
        assert len(results) >= 3
        results = self.r.search_causali("non_existent_12345")
        assert len(results) == 0

    def test_causale_straordinario_details(self):
        sa = self.r.get_causale("SA")
        assert sa is not None
        assert sa.category == "straordinario"
        assert sa.origin == CAUSALE_ORIGINE_AUTOMATICA

        sn = self.r.get_causale("SN")
        assert sn is not None
        assert "notturno" in sn.description.lower()

    def test_causale_festivita_details(self):
        f = self.r.get_causale("F")
        assert f is not None
        assert f.category == "festivita"

        fng = self.r.get_causale("FNG")
        assert fng is not None
        assert "non goduta" in fng.description.lower()

    def test_causale_turno_details(self):
        matt = self.r.get_causale("MATT")
        assert matt is not None
        assert matt.origin == CAUSALE_ORIGINE_TURNO
        assert matt.category == "turno"

        ripo = self.r.get_causale("RIPO")
        assert ripo is not None
        assert "riposo" in ripo.description.lower()


class TestTableRegistrySlotMappings:
    def setup_method(self):
        self.r = TableRegistry()

    def test_slot_mappings_all_present(self):
        for slot in range(501, 511):
            m = self.r.get_slot_mapping(slot)
            assert m is not None, f"Slot {slot} missing"
            assert m.slot == slot
            assert m.code
            assert m.description

    def test_slot_mapping_out_of_range(self):
        assert self.r.get_slot_mapping(999) is None

    def test_slot_for_causale(self):
        slots = self.r.get_slot_for_causale("SA")
        assert len(slots) >= 1
        assert all(isinstance(s, int) for s in slots)

    def test_slot_for_causale_not_found(self):
        slots = self.r.get_slot_for_causale("MATT")
        assert len(slots) == 0

    def test_slot_mapping_source_fields(self):
        m501 = self.r.get_slot_mapping(501)
        assert 918 in m501.source_fields  # festivita

        m502 = self.r.get_slot_mapping(502)
        assert 902 in m502.source_fields or 903 in m502.source_fields

    def test_get_causale_slot_info(self):
        info = self.r.get_causale_slot_info()
        assert len(info) == 10
        for slot, data in info.items():
            assert "slot" in data
            assert "code" in data
            assert "description" in data
            assert "source_fields" in data


class TestTableRegistryContracts:
    def setup_method(self):
        self.r = TableRegistry()

    def test_get_contract_exists(self):
        c1 = self.r.get_contract(1)
        assert c1 is not None
        assert c1.name == "Standard"
        assert c1.timbra is True

        c2 = self.r.get_contract(2)
        assert c2 is not None
        assert c2.name == "Dirigenti/Quadri"
        assert c2.timbra is False

    def test_get_contract_not_exists(self):
        assert self.r.get_contract(999) is None

    def test_contract_formulas_ig(self):
        c1 = self.r.get_contract(1)
        assert 1 in c1.formulas_ig
        assert 5 in c1.formulas_ig

    def test_contract_formulas_fg(self):
        c1 = self.r.get_contract(1)
        assert 100 in c1.formulas_fg
        assert 200 in c1.formulas_fg

    def test_get_contract_formulas_filter(self):
        ig = self.r.get_contract_formulas(1, flusso="ig")
        assert len(ig) >= 3
        assert 1 in ig

        fg = self.r.get_contract_formulas(1, flusso="fg")
        assert len(fg) >= 5
        assert 100 in fg

    def test_contract_fascia_notturna(self):
        c = self.r.get_contract(1)
        assert c.fascia_notturna_start == "22:00"
        assert c.fascia_notturna_end == "06:00"


class TestTableRegistryRelations:
    def setup_method(self):
        self.r = TableRegistry()

    def test_relations_from(self):
        rels = self.r.get_relations_from(100)
        assert len(rels) >= 1
        assert any(r.to_code == 110 for r in rels)

    def test_relations_to(self):
        rels = self.r.get_relations_to(110)
        assert len(rels) >= 1
        assert any(r.from_code == 100 for r in rels)

    def test_relations_fg_flow(self):
        rels = self.r.get_relations_from(120)
        targets = {r.to_code for r in rels}
        assert 130 in targets or 140 in targets or 200 in targets

    def test_formula_flow(self):
        flow = self.r.get_formula_flow("fine_giornata_standard")
        assert len(flow) >= 5
        assert 100 in flow
        assert 200 in flow

        flow2 = self.r.get_formula_flow("inizio_giornata_standard")
        assert 1 in flow2
        assert 5 in flow2

    def test_formula_flow_not_found(self):
        assert self.r.get_formula_flow("nonexistent_flow") == []

    def test_get_all_flow_names(self):
        names = self.r.get_all_flow_names()
        assert len(names) >= 10
        assert "fine_giornata_standard" in names

    def test_causali_summary(self):
        s = self.r.get_causali_summary()
        assert "total_causali" in s
        assert "by_origin" in s
        assert "by_category" in s
        assert "slot_mappings" in s


# ============================================================
# FormulaPatternLibrary Tests
# ============================================================

class TestFormulaPatternLibraryBasics:
    def setup_method(self):
        self.lib = FormulaPatternLibrary()

    def test_singleton(self):
        lib2 = FormulaPatternLibrary()
        assert self.lib is lib2

    def test_stats(self):
        s = self.lib.stats()
        assert s["total_patterns"] >= 40
        assert s["with_compact"] >= 10
        assert s["with_calls"] >= 10


class TestFormulaPatternLibraryQuery:
    def setup_method(self):
        self.lib = FormulaPatternLibrary()

    def test_get_pattern_exists(self):
        p = self.lib.get_pattern(1)
        assert p is not None
        assert p.code == 1
        assert p.name == "Azzeramenti di inizio giornata"
        assert p.tipo == FORMULA_TIPO_IG

    def test_get_pattern_not_exists(self):
        assert self.lib.get_pattern(99999) is None

    def test_get_pattern_200(self):
        p = self.lib.get_pattern(200)
        assert p is not None
        assert p.tipo == FORMULA_TIPO_FG
        assert 601 in p.fields_involved
        assert 602 in p.fields_involved

    def test_get_pattern_2123(self):
        p = self.lib.get_pattern(2123)
        assert p is not None
        assert p.tipo == FORMULA_TIPO_SUB
        assert p.category == "Arrotondamento"
        assert p.compact
        assert "902" in p.compact
        assert "K800" in p.compact

    def test_get_patterns_by_tipo(self):
        ig = self.lib.get_patterns_by_tipo(FORMULA_TIPO_IG)
        assert len(ig) >= 8
        assert all(p.tipo == FORMULA_TIPO_IG for p in ig)

        fg = self.lib.get_patterns_by_tipo(FORMULA_TIPO_FG)
        assert len(fg) >= 10
        assert all(p.tipo == FORMULA_TIPO_FG for p in fg)

    def test_get_patterns_by_category(self):
        arrot = self.lib.get_patterns_by_category("Arrotondamento")
        assert len(arrot) >= 5
        assert all(p.category == "Arrotondamento" for p in arrot)

        straord = self.lib.get_patterns_by_category("Straordinario")
        assert len(straord) >= 5

    def test_search_patterns(self):
        results = self.lib.search_patterns("arrotondamento")
        assert len(results) >= 5

        results = self.lib.search_patterns("fine giornata")
        assert len(results) >= 1

        results = self.lib.search_patterns("999999")
        assert len(results) == 0

    def test_search_by_code_exact(self):
        results = self.lib.search_patterns("2123")
        assert len(results) >= 1
        assert results[0].code == 2123


class TestFormulaPatternLibraryContent:
    def setup_method(self):
        self.lib = FormulaPatternLibrary()

    def test_pattern_5_riconoscimento_turno(self):
        p = self.lib.get_pattern(5)
        assert p is not None
        assert "Riconoscimento" in p.name
        assert 58 in p.fields_involved
        assert 900 in p.fields_involved
        assert len(p.steps) >= 5

    def test_pattern_100_azzeramenti(self):
        p = self.lib.get_pattern(100)
        assert p is not None
        assert '500="DURATA"' in p.compact
        assert "R110" in p.compact
        assert any(c["target"] == 110 for c in p.calls)

    def test_pattern_110_riproporziono(self):
        p = self.lib.get_pattern(110)
        assert p is not None
        assert any(c["target"] == 120 for c in p.calls)
        assert 608 in p.fields_involved
        assert 609 in p.fields_involved

    def test_pattern_120_smistatore(self):
        p = self.lib.get_pattern(120)
        assert p is not None
        targets = {c["target"] for c in p.calls}
        assert 130 in targets
        assert 140 in targets

    def test_pattern_200_finale(self):
        p = self.lib.get_pattern(200)
        assert p is not None
        assert "K601" in p.compact
        assert "K602" in p.compact
        assert any(c["type"] == "P" and c["target"] == 210 for c in p.calls)

    def test_pattern_1100_dirigenti(self):
        p = self.lib.get_pattern(1100)
        assert p is not None
        assert p.tipo == FORMULA_TIPO_FG
        assert p.category == "Dirigenti"

    def test_pattern_9001_arrotondamento(self):
        p = self.lib.get_pattern(9001)
        assert p is not None
        assert p.tipo == FORMULA_TIPO_IG
        assert any(c["target"] == 9002 for c in p.calls)


class TestFormulaPatternLibraryRelations:
    def setup_method(self):
        self.lib = FormulaPatternLibrary()

    def test_get_compact(self):
        assert self.lib.get_compact(99999) == ""
        assert self.lib.get_compact(200).startswith("(K601")

    def test_get_template(self):
        tmpl = self.lib.get_template(200)
        assert tmpl is not None
        assert "K601" in tmpl

        tmpl_none = self.lib.get_template(99999)
        assert tmpl_none is None

    def test_find_by_field(self):
        patterns = self.lib.find_by_field(900)
        assert len(patterns) >= 3

        patterns = self.lib.find_by_field(601)
        assert len(patterns) >= 3

        patterns = self.lib.find_by_field(99999)
        assert len(patterns) == 0

    def test_get_all_codes(self):
        codes = self.lib.get_all_codes()
        assert len(codes) >= 40
        assert 1 in codes
        assert 200 in codes
        assert 2123 in codes

    def test_get_patterns_that_call(self):
        callers = self.lib.get_patterns_that_call(200)
        assert len(callers) >= 3  # 120, 130, 140 all call 200

    def test_get_patterns_called_by(self):
        callees = self.lib.get_patterns_called_by(2100)
        assert len(callees) >= 1

        callees_none = self.lib.get_patterns_called_by(99999)
        assert len(callees_none) == 0

    def test_pattern_2123_has_proper_steps(self):
        p = self.lib.get_pattern(2123)
        assert p is not None
        assert len(p.steps) >= 5
        step_descriptions = [s["descrizione"] for s in p.steps]
        assert any("15" in d for d in step_descriptions)
        assert any("30" in d for d in step_descriptions)
        assert any("45" in d for d in step_descriptions)


class TestFormulaPatternLibraryEdgeCases:
    def setup_method(self):
        self.lib = FormulaPatternLibrary()

    def test_pattern_2125_placeholder(self):
        p = self.lib.get_pattern(2125)
        assert p is not None
        assert p.name == "GUGEST 22 – placeholder vuoto"
        assert p.compact == ""

    def test_pattern_2140_minimal(self):
        p = self.lib.get_pattern(2140)
        assert p is not None
        assert p.compact == "(71=3A4)"
        assert p.fields_involved == [3, 4, 71]

    def test_pattern_3003_compact(self):
        p = self.lib.get_pattern(3003)
        assert p is not None
        assert "71=3" in p.compact
        assert "K800" in p.compact
        assert "0.30" in p.compact
