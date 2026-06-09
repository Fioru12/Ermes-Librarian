"""
modules/generic.py
Modulo generico per Ermes.
Usato come fallback per moduli non specifici.
"""
from typing import Any

from .base import BaseModule


class GenericModule(BaseModule):
    """
    Modulo generico per Ermes.
    Gestisce domande generiche senza regole specifiche.
    """

    def __init__(self):
        super().__init__("Generic")

    def get_system_prompt(self) -> str:
        return (
            "Sei un assistente AI aziendale per Ermes. "
            "Aiuta gli utenti a trovare informazioni nei documenti aziendali. "
            "Rispondi in modo chiaro e professionale. "
            "Se l'informazione non è nei documenti, dillo chiaramente senza inventare. "
            "Rispondi sempre in italiano."
        )

    def parse_response(self, response: str) -> dict[str, Any]:
        return {
            "content": response,
            "code": "",
            "exp": "",
            "errors": [],
            "has_split": False,
        }

    def validate_content(self, content: str) -> list:
        return []

    def is_applicable(self, module_name: str) -> bool:
        return True

    def get_chat_placeholder(self, mode: str = "retrieval") -> str:
        return "Fai una domanda sui documenti..."
