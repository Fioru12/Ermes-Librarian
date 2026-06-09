import logging
from pathlib import Path

_logger = logging.getLogger(__name__)

class BusinessAssistant:
    def __init__(self):
        self.doc_path = Path(__file__).parent.parent / "documenti" / "WinSarp"
        try:
            self.clarificazioni = (self.doc_path / "Clarificazioni.txt").read_text(encoding="utf-8")
        except FileNotFoundError:
            self.clarificazioni = ""
        
        # Mappa semplificata intent -> parametri necessari
        self.requirements = {
            "straordinario": ["percentuale", "fascia_oraria"],
            "premio": ["base_calcolo", "periodo"],
            "ferie": ["tipo_ferie"],
        }

    def check_needs_clarification(self, user_request: str) -> str | None:
        """
        Controlla se la richiesta è vaga e restituisce una domanda di chiarimento,
        altrimenti None.
        """
        request_l = user_request.lower()
        
        for intent, reqs in self.requirements.items():
            if intent in request_l:
                missing = [r for r in reqs if r not in request_l]
                if missing:
                    return f"Per generare correttamente la formula '{intent}', mi servono alcune info: {', '.join(missing)}. Puoi specificarle?"
        return None
