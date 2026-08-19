"""Unit tests for the new agent capabilities: dialogue context, semantic retriever, prompt extensions, and self-correction."""
import sys
sys.path.insert(0, ".")

import unittest
import json
from unittest.mock import MagicMock, patch
from legacy_winsarp.core.formula_builder import FormulaBuilder, DialogueContext
from legacy_winsarp.core.winsarp.few_shot_retriever import FewShotRetriever
from legacy_winsarp.core.winsarp.workbook_retriever import WorkbookRetriever


class TestDialogueContext(unittest.TestCase):
    def test_dialogue_flow(self):
        # Create context from clarification questions
        original = "voglio fare un calcolo"
        questions = [
            {"domanda": "Quali campi vuoi usare?", "tipo": "campi"},
            {"domanda": "Quale operazione?", "tipo": "operazione"}
        ]
        ctx = DialogueContext.from_clarification(original, questions)

        self.assertEqual(ctx.original_request, original)
        self.assertEqual(ctx.questions_asked, ["Quali campi vuoi usare?", "Quale operazione?"])
        self.assertFalse(ctx.all_answered())
        self.assertEqual(ctx.current_question_index, 0)

        # Answer first question
        ctx.add_answer("campi 800 e 801")
        self.assertFalse(ctx.all_answered())
        self.assertEqual(ctx.current_question_index, 1)
        self.assertEqual(ctx.answers_given, ["campi 800 e 801"])

        # Answer second question
        ctx.add_answer("somma")
        self.assertTrue(ctx.all_answered())
        self.assertEqual(ctx.current_question_index, 2)

        # Check enriched request string
        enriched = ctx.build_enriched_request()
        self.assertIn("Richiesta originale: voglio fare un calcolo", enriched)
        self.assertIn("Quali campi vuoi usare?", enriched)
        self.assertIn("campi 800 e 801", enriched)
        self.assertIn("Quale operazione?", enriched)
        self.assertIn("somma", enriched)

        # Test to/from dict serialization
        d = ctx.to_dict()
        self.assertEqual(d["original_request"], original)
        self.assertEqual(len(d["turns"]), 3)  # system initiation + 2 user turns

        ctx2 = DialogueContext.from_dict(d)
        self.assertEqual(ctx2.original_request, original)
        self.assertEqual(ctx2.questions_asked, ctx.questions_asked)
        self.assertEqual(ctx2.answers_given, ctx.answers_given)
        self.assertTrue(ctx2.all_answered())


class TestSemanticRetrieval(unittest.TestCase):
    @patch("legacy_winsarp.core.winsarp.few_shot_retriever.FewShotRetriever._get_embedder")
    def test_semantic_fallback_when_no_embedder(self, mock_get_embedder):
        mock_get_embedder.return_value = None
        retriever = FewShotRetriever()
        retriever.load()

        # search_semantic should fall back to standard keyword search
        results = retriever.search_semantic("turno mattino", top_k=2)
        self.assertGreater(len(results), 0)

    def test_semantic_search_with_embedder(self):
        retriever = FewShotRetriever()
        retriever.load()

        # Test semantic search with sentence-transformers if available
        # It's already loaded in memory
        results = retriever.search_semantic("straordinario festivo", top_k=2)
        self.assertGreater(len(results), 0)


class TestWorkbookPromptExtensions(unittest.TestCase):
    def test_enriched_prompt_has_sections(self):
        retriever = WorkbookRetriever()
        prompt = retriever.build_enriched_prompt("calcola straordinario")

        # Ensure our rapid reference and structural sections are in the prompt
        self.assertIn("--- RIFERIMENTO RAPIDO SINTASSI WinSarp ---", prompt)
        self.assertIn("--- MAPPA STRUTTURALE DEI CAMPI ---", prompt)
        self.assertIn("CAMPI DI APPOGGIO COMUNI:", prompt)


class TestSelfCorrectionLoop(unittest.TestCase):
    @patch("legacy_winsarp.core.formula_builder.FormulaBuilder._call_llm_safe")
    def test_generate_via_llm_success(self, mock_call_llm):
        mock_call_llm.return_value = "( 800 = 15 )\nVF"

        builder = FormulaBuilder(MagicMock())
        result = builder._generate_via_llm("test request")

        self.assertTrue(result["success"])
        self.assertEqual(result["formula"], "(800=15)VF")
        self.assertEqual(result["source"], "generated")
        self.assertEqual(mock_call_llm.call_count, 1)

    @patch("legacy_winsarp.core.formula_builder.FormulaBuilder._call_llm_safe")
    def test_generate_via_llm_failure_returns_error(self, mock_call_llm):
        mock_call_llm.return_value = ""

        builder = FormulaBuilder(MagicMock())
        result = builder._generate_via_llm("test request")

        self.assertFalse(result["success"])
        self.assertEqual(result["formula"], "")
        self.assertIn("error", result)





if __name__ == "__main__":
    unittest.main()
