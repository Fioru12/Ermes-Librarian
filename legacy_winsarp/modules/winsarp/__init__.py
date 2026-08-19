"""

modules/winsarp/__init__.py

Package del modulo WinSarp.

Espone tutte le funzioni e costanti per retrocompatibilità con from legacy_winsarp.modules.winsarp import ...

Contiene la classe WinSarpModule (eredita da BaseModule).

"""

from typing import Any



from ..base import BaseModule

from .parser import clean_code, parse_response

from .prompts import (

    FALLBACK_PHRASES,

    PROMPT_GENERALE,

    PROMPT_WINSARP,

    PROMPT_WINSARP_GENERAZIONE,

    PROMPTS,

    PROMPTS_GENERAZIONE,

    is_fallback,

)

from .validator import auto_fix_formula, validate_winsarp



__all__ = [

    # prompts

    "PROMPT_WINSARP", "PROMPT_GENERALE", "PROMPTS",

    "PROMPT_WINSARP_GENERAZIONE", "PROMPTS_GENERAZIONE",

    "FALLBACK_PHRASES", "is_fallback",

    # validator

    "validate_winsarp", "auto_fix_formula",

    # parser

    "parse_response", "clean_code",

    # module class

    "WinSarpModule",

]





class WinSarpModule(BaseModule):

    """

    Modulo WinSarp per Ermes.

    Gestisce prompt, parsing e validazione specifici per WinSarp.

    """



    def __init__(self):

        super().__init__("WinSarp")



    def get_system_prompt(self) -> str:

        return PROMPT_WINSARP



    def parse_response(self, response: str) -> dict[str, Any]:

        return parse_response(response, "WinSarp")



    def validate_content(self, content: str) -> list:

        return validate_winsarp(content)



    def is_applicable(self, module_name: str) -> bool:

        return module_name.lower() == "winsarp"



    def supports_generation(self) -> bool:

        return True



    def has_formula_only(self) -> bool:

        return True



    def get_generation_prompt(self, user_request: str = "") -> str:

        from legacy_winsarp.core.formula_builder import FormulaBuilder

        from legacy_winsarp.core.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph()

        builder = FormulaBuilder(kg)

        return builder.get_contextual_prompt(user_request)



    def get_formula_only_instruction(self) -> str:

        return (

            "\n\nRISPOSTA SOLO FORMULA: L'utente ha richiesto 'formula_only'. "

            "Rispondi ESCLUSIVAMENTE con il codice della formula, senza header, "

            "senza spiegazioni e senza testo aggiuntivo. Ritorna solo il codice compresso "

            "dentro un blocco di codice o come singola riga. "

            "Se non trovi una formula, rispondi esattamente: Nel catalogo non e' presente una formula per questo caso."

        )



    def get_retrieval_suggestions(self) -> list[str]:

        return [

            "Dammi la formula per straordinario oltre 8 ore con causale ST",

            "Qual \u00e8 la formula per la gestione del turno notturno a mezzanotte?",

            "Mostrami la formula per arrotondare entrata e uscita a quarti d'ora",

            "Qual \u00e8 la formula per verificare se il giorno \u00e8 festivo o weekend?",

        ]



    def get_generation_suggestions(self) -> list[str]:

        return [

            "Crea una formula per calcolare lo straordinario notturno con maggiorazione 30%",

            "Genera una formula per calcolare il TFR proporzionale ai mesi lavorati",

            "Crea una formula per calcolare i contributi INPS su base oraria",

            "Genera una formula per calcolare le ferie maturate nell'anno corrente",

        ]



    def get_chat_placeholder(self, mode: str = "retrieval") -> str:

        if mode == "generazione" and self.supports_generation():

            return (

                "Descrivi la formula da proporre... "

                "(bozza AI separata dal catalogo ufficiale)"

            )

        return (

            "Cerca una formula... (es: dammi la formula per lo straordinario oltre 8 ore)"

        )

