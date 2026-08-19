"""
modules/base.py
Classe base per i moduli Ermes.
Ogni modulo deve ereditare da questa classe e implementare i metodi richiesti.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseModule(ABC):
    """
    Classe base astratta per i moduli Ermes.

    Ogni modulo rappresenta un dominio specifico (es. WinSarp, HR, Finance)
    con le sue regole di parsing, validazione e prompt.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_system_prompt(self) -> str:
        pass

    @abstractmethod
    def parse_response(self, response: str) -> dict[str, Any]:
        pass

    @abstractmethod
    def validate_content(self, content: str) -> list:
        pass

    def is_applicable(self, module_name: str) -> bool:
        return self.name.lower() == module_name.lower()

    # ── Capacità del modulo ──────────────────────────────

    def supports_generation(self) -> bool:
        """Il modulo supporta una modalità generazione separata dal retrieval."""
        return False

    def has_formula_only(self) -> bool:
        """Il modulo può rispondere con solo codice formula (senza spiegazioni)."""
        return False

    def get_generation_prompt(self, user_request: str = "") -> str:
        """Prompt specifico per la modalità generazione (se supportata)."""
        return self.get_system_prompt()

    def get_formula_only_instruction(self) -> str:
        """Istruzioni aggiuntive per rispondere con sola formula (se supportato)."""
        return ""

    def get_retrieval_suggestions(self) -> list[str]:
        """Suggerimenti per la modalità retrieval."""
        return []

    def get_generation_suggestions(self) -> list[str]:
        """Suggerimenti per la modalità generazione."""
        return []

    def get_chat_placeholder(self, mode: str = "retrieval") -> str:
        """Testo placeholder per l'input chat."""
        if mode == "generazione" and self.supports_generation():
            return "Descrivi cosa vuoi generare..."
        return "Fai una domanda sui documenti..."
