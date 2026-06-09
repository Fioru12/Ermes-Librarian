import logging
from core.knowledge_graph import KnowledgeGraph
from pathlib import Path

_logger = logging.getLogger(__name__)

class FormulaBuilder:
    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self.doc_path = Path(__file__).parent.parent / "documenti" / "WinSarp"
        try:
            self.grammar = (self.doc_path / "WinsarpGrammatica.txt").read_text(encoding="utf-8")
            self.few_shot = (self.doc_path / "istruzionedocumenti.txt").read_text(encoding="utf-8")
        except FileNotFoundError as e:
            _logger.error("File documentazione non trovati: %s", e)
            self.grammar = ""
            self.few_shot = ""

    def get_contextual_prompt(self, user_request: str) -> str:
        # Cerca nel grafo formule simili alla richiesta
        similari = self.kg.search(user_request)[:3]
        
        examples = "\n\n### ESEMPI REALI DAL TUO CATALOGO (IMPARA QUESTA STRUTTURA):\n"
        for f in similari:
            examples += f"\n---\nFormula #{f['id']} - {f['name']}\nCodice: {f['code']}\n---\n"
        
        system_prompt = (
            "Sei un compilatore WinSarp esperto. Il tuo compito è generare formule basate ESCLUSIVAMENTE "
            "sulla sintassi e sugli esempi forniti.\n\n"
            f"{self.grammar}\n\n"
            f"{self.few_shot}\n"
            f"{examples}\n\n"
            "LINGUA: Rispondi SEMPRE in italiano.\n"
            "FORMATO: [formula] ... [/formula] [spiegazione] ... [/spiegazione]\n"
        )
        
        return f"{system_prompt}\nDOMANDA UTENTE: {user_request}"
