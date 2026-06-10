"""Test unitari per il modulo agent_runner."""
import sys
import os
import tempfile
from pathlib import Path
import pytest

# Usa lo stesso catalogo di test_knowledge_graph.py per evitare conflitti
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

# Patch percorso catalogo prima di import
_test_dir = Path(tempfile.mkdtemp())
_test_catalog = _test_dir / "WinSarp_Formule.txt"
_test_catalog.write_text(SAMPLE_CATALOG, encoding="utf-8")

import core.knowledge_graph as kg_mod
kg_mod.CATALOGO_PATH = _test_catalog
kg_mod.GRAPH_PATH = _test_dir / "test_agent_graph.json"

from core.agent_runner import AgentRunner, TOOL_DESCRIPTIONS, run
from core.knowledge_graph import KnowledgeGraph


class TestAgentRunnerInit:
    def test_init_creates_kg(self):
        runner = AgentRunner()
        assert runner.kg is not None
        assert runner.kg.stats()["totale_formule"] == 6

    def test_init_with_existing_kg(self):
        kg = KnowledgeGraph()
        runner = AgentRunner(kg)
        assert runner.kg is kg


class TestParseAndExecutePlan:
    def setup_method(self):
        self.runner = AgentRunner()

    def test_parse_simple_command(self):
        steps = self.runner._parse_and_execute_plan("follow_calls(100)")
        assert len(steps) == 1
        assert steps[0]["tool"] == "follow_calls"
        assert steps[0]["input"] == "100"

    def test_parse_multiple_commands(self):
        steps = self.runner._parse_and_execute_plan(
            "follow_calls(100)\nread_formula(110)"
        )
        assert len(steps) == 2
        tools = [s["tool"] for s in steps]
        assert "follow_calls" in tools
        assert "read_formula" in tools

    def test_parse_ignores_duplicates(self):
        steps = self.runner._parse_and_execute_plan(
            "follow_calls(100)\nfollow_calls(100)"
        )
        assert len(steps) == 1

    def test_parse_with_backticks(self):
        steps = self.runner._parse_and_execute_plan(
            "`follow_calls(100)`"
        )
        assert len(steps) == 1

    def test_parse_empty_plan(self):
        steps = self.runner._parse_and_execute_plan("")
        assert steps == []

    def test_parse_unknown_tool(self):
        steps = self.runner._parse_and_execute_plan("unknown_tool(100)")
        assert steps == []


class TestExecuteTool:
    def setup_method(self):
        self.runner = AgentRunner()

    def test_search_formulae(self):
        result = self.runner._execute_tool("search_formulae", "PRIMA")
        assert len(result) >= 1
        assert any(r["id"] == 100 for r in result)

    def test_read_formula(self):
        result = self.runner._execute_tool("read_formula", "100")
        assert result is not None
        assert result["id"] == 100
        assert result["name"] == "F.G: PRIMA FORMULA"

    def test_read_formula_missing(self):
        result = self.runner._execute_tool("read_formula", "99999")
        assert result is None

    def test_find_by_field(self):
        result = self.runner._execute_tool("find_by_field", "561")
        assert len(result) >= 1

    def test_follow_calls(self):
        result = self.runner._execute_tool("follow_calls", "100")
        assert len(result) >= 1
        assert any(r["id"] == 110 for r in result)

    def test_follow_callers(self):
        result = self.runner._execute_tool("follow_callers", "110")
        assert len(result) >= 1
        assert any(r["id"] == 100 for r in result)

    def test_validate_chain(self):
        result = self.runner._execute_tool("validate_chain", "100")
        assert isinstance(result, dict)
        assert "chain" in result

    def test_compare_formulas(self):
        result = self.runner._execute_tool("compare_formulas", "100,110")
        assert "formula1" in result
        assert "formula2" in result

    def test_unknown_tool(self):
        result = self.runner._execute_tool("nonexistent", "100")
        assert "sconosciuto" in str(result)


class TestBuildPrompt:
    def setup_method(self):
        self.runner = AgentRunner()

    def test_build_prompt_includes_catalog(self):
        prompt = self.runner._build_prompt("test query")
        assert "CATALOGO FORMULE" in prompt
        assert "100 - F.G: PRIMA FORMULA" in prompt
        assert "test query" in prompt


class TestRunEntryPoint:
    @pytest.mark.skipif(True, reason="Requires Ollama running (integration test)")
    def test_direct_query(self):
        result = run("test", use_agent=False)
        assert "response" in result
        assert "time" in result
        assert result["steps"] == []

    @pytest.mark.skipif(True, reason="Requires Ollama running (integration test)")
    def test_agent_no_tools(self):
        result = run("Ciao", use_agent=True)
        assert "response" in result
        assert "time" in result
