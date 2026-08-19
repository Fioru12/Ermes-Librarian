import pytest
from legacy_winsarp.core.formula_builder import FormulaBuilder
from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph

@pytest.fixture
def builder():
    kg = KnowledgeGraph()
    return FormulaBuilder(kg=kg)

def test_formula_1_azzeramento(builder):
    """Test coerenza Manuale pag. 17 / Formula 1"""
    # Richiesta che deve triggerare l'azzeramento
    res = builder.generate("Azzera campo 900")
    assert res["success"] is True
    # La formula 1 deve contenere (!900)
    assert "(!900)" in res["formula"]

def test_formula_2050_arrotondamento_conad(builder):
    """Test coerenza Manuale pag. 21 / Formula 2050 (Arrotondamento)"""
    # La 2050 deve gestire l'arrotondamento entrata
    # Il sistema deve riconoscerlo tramite intento
    res = builder.generate("Arrotondamento entrata Conad")
    assert res["success"] is True
    # L'intent builder genera un formula di arrotondamento con i campi 71/72/70
    assert "71=" in res["formula"]  # Campo riferimento
    assert "72=" in res["formula"]  # Approssimazione
    assert "70=" in res["formula"]  # Modalita arrotondamento

def test_formula_110_riproporzionamento(builder):
    """Test coerenza Manuale pag. 33 / Formula 110 (Riproporzionamento assenze)"""
    # La 110 riproporziona assenze se ore lavorate + assenze != previsionale
    res = builder.generate("Riproporziona ordinario e straordinario")
    assert res["success"] is True
    # Verifica presenza operatori di calcolo assenza/straordinario
    assert "S" in res["formula"] # Sottrazione
    assert "A" in res["formula"] # Addizione
